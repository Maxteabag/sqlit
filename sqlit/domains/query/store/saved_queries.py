"""User-managed SQL files saved per connection."""

from __future__ import annotations

import hashlib
import os
import re
import secrets
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from sqlit.shared.core.store import CONFIG_DIR

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]")
_MAX_QUERY_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True)
class FileFingerprint:
    """Identity of file contents when a query was loaded or saved."""

    digest: str
    size: int
    mtime_ns: int


@dataclass(frozen=True)
class SavedQueryEntry:
    """One readable SQL file in a connection's saved-query library."""

    path: Path
    relative_path: str
    query: str
    fingerprint: FileFingerprint

    @property
    def display_name(self) -> str:
        return self.relative_path


class SavedQueryConflictError(RuntimeError):
    """Raised when a file changed after it was loaded."""


class SavedQueryNameError(ValueError):
    """Raised for names that would escape the connection directory."""


def _connection_dir_name(connection_name: str) -> str:
    safe = _SAFE_NAME.sub("_", connection_name)[:40] or "_"
    short = hashlib.sha256(connection_name.encode("utf-8")).hexdigest()[:8]
    return f"{safe}_{short}"


def _fingerprint(path: Path, data: bytes | None = None) -> FileFingerprint:
    stat = path.stat()
    if stat.st_size > _MAX_QUERY_BYTES:
        raise OSError(f"Query file is larger than {_MAX_QUERY_BYTES // (1024 * 1024)} MiB")
    if data is None:
        digest = hashlib.sha256()
        size = 0
        with path.open("rb") as handle:
            while chunk := handle.read(64 * 1024):
                size += len(chunk)
                if size > _MAX_QUERY_BYTES:
                    raise OSError(
                        f"Query file is larger than {_MAX_QUERY_BYTES // (1024 * 1024)} MiB"
                    )
                digest.update(chunk)
        digest_value = digest.hexdigest()
    else:
        if len(data) > _MAX_QUERY_BYTES:
            raise OSError(
                f"Query file is larger than {_MAX_QUERY_BYTES // (1024 * 1024)} MiB"
            )
        size = len(data)
        digest_value = hashlib.sha256(data).hexdigest()
    return FileFingerprint(
        digest=digest_value,
        size=size,
        mtime_ns=stat.st_mtime_ns,
    )


def _normalize_relative_name(name: str) -> PurePosixPath:
    raw = name.strip().replace("\\", "/")
    if not raw:
        raise SavedQueryNameError("Enter a query name")
    relative = PurePosixPath(raw)
    if (
        not relative.parts
        or relative.is_absolute()
        or any(part in {"", ".", ".."} for part in relative.parts)
        or any(part.startswith(".") for part in relative.parts)
    ):
        raise SavedQueryNameError("Use a relative name inside the query library")
    if relative.suffix.lower() != ".sql":
        relative = relative.with_suffix(".sql")
    return relative


class SavedQueryStore:
    """File-backed saved queries, separated from disposable query history."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self._base_dir = base_dir if base_dir is not None else CONFIG_DIR / "saved-queries"

    @property
    def base_dir(self) -> Path:
        return self._base_dir

    def connection_dir(self, connection_name: str) -> Path:
        """Return the lazy directory path without creating it."""
        return self._base_dir / _connection_dir_name(connection_name)

    def _path_for_name(self, connection_name: str, name: str) -> tuple[Path, str]:
        relative = _normalize_relative_name(name)
        path = self.connection_dir(connection_name).joinpath(*relative.parts)
        return path, relative.as_posix()

    def _read_entry(self, root: Path, path: Path) -> SavedQueryEntry:
        if self._secure_dir_fd_available():
            relative_path = path.relative_to(root).as_posix()
            directory_fd, filename = self._open_secure_parent(
                root, relative_path, create=False
            )
            try:
                try:
                    file_fd = os.open(
                        filename,
                        os.O_RDONLY | os.O_NOFOLLOW,
                        dir_fd=directory_fd,
                    )
                except OSError as exc:
                    raise SavedQueryNameError(
                        "Symlinks inside a query library are not supported"
                    ) from exc
                try:
                    file_stat = os.fstat(file_fd)
                    if file_stat.st_size > _MAX_QUERY_BYTES:
                        raise OSError(
                            "Query file is larger than "
                            f"{_MAX_QUERY_BYTES // (1024 * 1024)} MiB"
                        )
                    payload = bytearray()
                    while chunk := os.read(file_fd, 64 * 1024):
                        payload.extend(chunk)
                        if len(payload) > _MAX_QUERY_BYTES:
                            raise OSError(
                                "Query file is larger than "
                                f"{_MAX_QUERY_BYTES // (1024 * 1024)} MiB"
                            )
                finally:
                    os.close(file_fd)
            finally:
                os.close(directory_fd)
            data = bytes(payload)
            return SavedQueryEntry(
                path=path,
                relative_path=relative_path,
                query=data.decode("utf-8-sig"),
                fingerprint=FileFingerprint(
                    digest=hashlib.sha256(data).hexdigest(),
                    size=len(data),
                    mtime_ns=file_stat.st_mtime_ns,
                ),
            )

        self._reject_nested_symlink(root, path)
        data = path.read_bytes()
        if len(data) > _MAX_QUERY_BYTES:
            raise OSError(f"Query file is larger than {_MAX_QUERY_BYTES // (1024 * 1024)} MiB")
        query = data.decode("utf-8-sig")
        return SavedQueryEntry(
            path=path,
            relative_path=path.relative_to(root).as_posix(),
            query=query,
            fingerprint=_fingerprint(path, data),
        )

    @staticmethod
    def _reject_nested_symlink(root: Path, path: Path) -> None:
        """Allow a linked library root, but never links inside that library."""
        relative = path.relative_to(root)
        current = root
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                raise SavedQueryNameError("Symlinks inside a query library are not supported; link the connection's whole saved-query directory instead")

    def list_for_connection(self, connection_name: str) -> list[SavedQueryEntry]:
        root = self.connection_dir(connection_name)
        if not root.is_dir():
            return []
        entries: list[SavedQueryEntry] = []
        try:
            paths = sorted(
                root.rglob("*"), key=lambda item: item.as_posix().lower()
            )
        except OSError:
            return []
        for path in paths:
            if not path.is_file() or path.suffix.lower() != ".sql":
                continue
            relative_parts = path.relative_to(root).parts
            if any(part.startswith(".") for part in relative_parts):
                continue
            try:
                entries.append(self._read_entry(root, path))
            except (OSError, UnicodeError, SavedQueryNameError):
                continue
        return entries

    def load(self, connection_name: str, relative_path: str) -> SavedQueryEntry:
        path, _ = self._path_for_name(connection_name, relative_path)
        return self._read_entry(self.connection_dir(connection_name), path)

    def current_fingerprint(self, connection_name: str, relative_path: str) -> FileFingerprint | None:
        path, _ = self._path_for_name(connection_name, relative_path)
        try:
            return _fingerprint(path)
        except OSError:
            return None

    @staticmethod
    def _secure_dir_fd_available() -> bool:
        return (
            os.name != "nt"
            and hasattr(os, "O_DIRECTORY")
            and hasattr(os, "O_NOFOLLOW")
            and os.open in os.supports_dir_fd
            and os.mkdir in os.supports_dir_fd
            and os.rename in os.supports_dir_fd
        )

    def _open_secure_parent(
        self, root: Path, relative_path: str, *, create: bool = True
    ) -> tuple[int, str]:
        """Open and pin every directory below an intentionally trusted root."""
        if create:
            root.parent.mkdir(parents=True, exist_ok=True)
            root.mkdir(parents=True, exist_ok=True)
        flags = os.O_RDONLY | os.O_DIRECTORY
        directory_fd = os.open(root, flags)
        parts = PurePosixPath(relative_path).parts
        try:
            for part in parts[:-1]:
                try:
                    child_fd = os.open(
                        part,
                        flags | os.O_NOFOLLOW,
                        dir_fd=directory_fd,
                    )
                except FileNotFoundError:
                    if not create:
                        raise
                    os.mkdir(part, mode=0o700, dir_fd=directory_fd)
                    child_fd = os.open(
                        part,
                        flags | os.O_NOFOLLOW,
                        dir_fd=directory_fd,
                    )
                except OSError as exc:
                    raise SavedQueryNameError(
                        "Symlinks inside a query library are not supported"
                    ) from exc
                os.close(directory_fd)
                directory_fd = child_fd
            return directory_fd, parts[-1]
        except Exception:
            os.close(directory_fd)
            raise

    @staticmethod
    def _fingerprint_at(directory_fd: int, filename: str) -> FileFingerprint | None:
        try:
            file_fd = os.open(
                filename,
                os.O_RDONLY | os.O_NOFOLLOW,
                dir_fd=directory_fd,
            )
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise SavedQueryNameError(
                "Symlinks inside a query library are not supported"
            ) from exc
        try:
            file_stat = os.fstat(file_fd)
            if file_stat.st_size > _MAX_QUERY_BYTES:
                raise OSError(
                    f"Query file is larger than {_MAX_QUERY_BYTES // (1024 * 1024)} MiB"
                )
            digest = hashlib.sha256()
            size = 0
            while chunk := os.read(file_fd, 64 * 1024):
                size += len(chunk)
                if size > _MAX_QUERY_BYTES:
                    raise OSError(
                        f"Query file is larger than {_MAX_QUERY_BYTES // (1024 * 1024)} MiB"
                    )
                digest.update(chunk)
            return FileFingerprint(
                digest=digest.hexdigest(),
                size=size,
                mtime_ns=file_stat.st_mtime_ns,
            )
        finally:
            os.close(file_fd)

    def _save_with_secure_dir_fd(
        self,
        connection_name: str,
        relative_path: str,
        payload: bytes,
        *,
        expected: FileFingerprint | None,
        overwrite: bool,
    ) -> None:
        root = self.connection_dir(connection_name)
        directory_fd, filename = self._open_secure_parent(root, relative_path)
        temporary_name = f".sqlit-save-{secrets.token_hex(8)}.sql"
        temporary_fd: int | None = None
        try:
            initial = self._fingerprint_at(directory_fd, filename)
            if expected is not None and initial != expected:
                raise SavedQueryConflictError(f"{relative_path} changed on disk")
            if initial is not None and expected is None and not overwrite:
                raise FileExistsError(relative_path)

            temporary_fd = os.open(
                temporary_name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=directory_fd,
            )
            with os.fdopen(temporary_fd, "wb", closefd=False) as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.close(temporary_fd)
            temporary_fd = None

            if self._fingerprint_at(directory_fd, filename) != initial:
                raise SavedQueryConflictError(f"{relative_path} changed on disk")
            os.rename(
                temporary_name,
                filename,
                src_dir_fd=directory_fd,
                dst_dir_fd=directory_fd,
            )
        finally:
            if temporary_fd is not None:
                os.close(temporary_fd)
            try:
                os.unlink(temporary_name, dir_fd=directory_fd)
            except FileNotFoundError:
                pass
            os.close(directory_fd)

    def save(
        self,
        connection_name: str,
        name: str,
        query: str,
        *,
        expected: FileFingerprint | None = None,
        overwrite: bool = False,
    ) -> SavedQueryEntry:
        path, relative_path = self._path_for_name(connection_name, name)
        payload = query.encode("utf-8")
        if len(payload) > _MAX_QUERY_BYTES:
            raise OSError(f"Query is larger than {_MAX_QUERY_BYTES // (1024 * 1024)} MiB")
        if self._secure_dir_fd_available():
            self._save_with_secure_dir_fd(
                connection_name,
                relative_path,
                payload,
                expected=expected,
                overwrite=overwrite,
            )
            return self._read_entry(self.connection_dir(connection_name), path)
        self._reject_nested_symlink(self.connection_dir(connection_name), path)
        initial = _fingerprint(path) if path.exists() else None
        if expected is not None and initial != expected:
            raise SavedQueryConflictError(f"{relative_path} changed on disk")
        if initial is not None and expected is None and not overwrite:
            raise FileExistsError(relative_path)

        destination = path
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(destination.parent, 0o700)
        except OSError:
            pass

        fd, temporary = tempfile.mkstemp(
            dir=destination.parent,
            prefix=".sqlit-save-",
            suffix=".sql",
        )
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.chmod(temporary, 0o600)
            except OSError:
                pass
            # Revalidate after the potentially slow write/fsync window so a
            # concurrent creation or editor change is not silently replaced.
            self._reject_nested_symlink(self.connection_dir(connection_name), path)
            latest = _fingerprint(path) if path.exists() else None
            if latest != initial:
                raise SavedQueryConflictError(f"{relative_path} changed on disk")
            os.replace(temporary, destination)
        except Exception:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise

        return self._read_entry(self.connection_dir(connection_name), path)

    def rename_connection(self, old_name: str, new_name: str) -> bool:
        """Move the lazy library when a saved connection is renamed."""
        old_dir = self.connection_dir(old_name)
        new_dir = self.connection_dir(new_name)
        if not old_dir.exists() or old_dir == new_dir:
            return True
        if new_dir.exists():
            return False
        try:
            new_dir.parent.mkdir(parents=True, exist_ok=True)
            old_dir.rename(new_dir)
        except OSError:
            return False
        return True
