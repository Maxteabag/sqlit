#!/usr/bin/env python3
"""Publish an existing public report directory to an isolated gh-pages branch.

Defaults to a read-only plan. --publish requires the user's authorization to
publish the report. Existing Pages source configuration is never replaced.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path


def run(*args, cwd=None, input_text=None, check=True):
    return subprocess.run(args, cwd=cwd, input=input_text, text=True, capture_output=True, check=check)


def pages(repo):
    result = run("gh", "api", f"repos/{repo}/pages", check=False)
    if result.returncode:
        if "HTTP 404" in result.stderr:
            return None
        raise RuntimeError(result.stderr)
    return json.loads(result.stdout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, help="GitHub owner/repository")
    parser.add_argument("--source", required=True, type=Path, help="Directory containing report.html and its public assets")
    parser.add_argument("--path", required=True, help="Destination folder inside gh-pages, e.g. performance/pr-331")
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    source = args.source.resolve()
    destination = Path(args.path)
    if destination.is_absolute() or ".." in destination.parts or not destination.parts:
        parser.error("--path must be a safe relative folder")
    if not (source / "report.html").is_file():
        parser.error("--source must contain report.html")
    if any(p.is_symlink() for p in source.rglob("*")):
        parser.error("Report source must not contain symlinks")
    source_root = Path(run("git", "rev-parse", "--show-toplevel", cwd=source).stdout.strip())
    relative_source = source.relative_to(source_root)
    tracked = {source_root / p for p in run("git", "ls-files", "-z", "--", str(relative_source), cwd=source_root).stdout.split("\0") if p}
    if any(p.is_file() and p not in tracked for p in source.rglob("*")) or run("git", "diff", "HEAD", "--", str(relative_source), cwd=source_root).stdout:
        parser.error("Commit the reviewed report and all its assets before publishing")
    repository = json.loads(run("gh", "api", f"repos/{args.repo}").stdout)
    if repository["private"]:
        parser.error("This helper publishes only material from an already-public repository")
    existing = pages(args.repo)
    expected_source = {"branch": "gh-pages", "path": "/"}
    if existing and (existing.get("source") != expected_source or existing.get("build_type") == "workflow"):
        parser.error("An existing Pages configuration is in use; preserve it and use its deployment workflow")
    source_sha = run("git", "rev-parse", "HEAD", cwd=source).stdout.strip()
    if run("gh", "api", f"repos/{args.repo}/git/commits/{source_sha}", check=False).returncode:
        parser.error("Push the report's source commit to this public repository before publishing")
    remote = repository["clone_url"]
    owner, name = args.repo.split("/", 1)
    base_url = existing["html_url"] if existing else f"https://{owner.lower()}.github.io/" + ("" if name.lower() == f"{owner.lower()}.github.io" else f"{name}/")
    plan = {"repo": args.repo, "branch": "gh-pages", "source_sha": source_sha,
            "files": sum(p.is_file() for p in source.rglob("*")),
            "destination": destination.as_posix(), "url": base_url.rstrip("/") + "/" + destination.as_posix() + "/"}
    print(json.dumps(plan), flush=True)
    if not args.publish:
        return
    with tempfile.TemporaryDirectory(prefix="sqlit-pages-") as temp:
        checkout = Path(temp) / "site"
        exists = bool(run("git", "ls-remote", "--heads", remote, "gh-pages").stdout.strip())
        if exists:
            run("git", "clone", "--quiet", "--depth=1", "--single-branch", "--branch=gh-pages", remote, str(checkout))
            if not (checkout / ".nojekyll").exists():
                raise RuntimeError("Existing gh-pages branch is not marked static; refusing to change its build semantics")
        else:
            run("git", "init", "--quiet", "-b", "gh-pages", str(checkout))
            run("git", "remote", "add", "origin", remote, cwd=checkout)
        target = checkout / destination
        if not target.resolve().is_relative_to(checkout.resolve()):
            raise RuntimeError("Destination escapes the publishing checkout")
        shutil.copytree(source, target, dirs_exist_ok=True)
        document = (target / "report.html").read_text()
        document = document.replace('href="../../labs/performance/README.md"',
                                    f'href="https://github.com/{args.repo}/blob/{source_sha}/labs/performance/README.md"')
        (target / "report.html").write_text(document)
        (target / "index.html").write_text(document)
        (target / "publication.json").write_text(json.dumps({**plan, "published_html_sha256": hashlib.sha256(document.encode()).hexdigest()}, indent=2) + "\n")
        (checkout / ".nojekyll").touch()
        if not (checkout / "index.html").exists():
            (checkout / "index.html").write_text('<!doctype html><html lang="en"><meta charset="utf-8"><title>sqlit reports</title>'
                                                f'<p><a href="{destination.as_posix()}/">Open the sqlit performance study</a></p></html>\n')
        run("git", "add", "--all", cwd=checkout)
        changed = run("git", "diff", "--cached", "--quiet", cwd=checkout, check=False).returncode
        if changed:
            run("git", "commit", "-m", f"docs: publish report at {destination.as_posix()}", cwd=checkout)
            run("git", "push", "origin", "HEAD:gh-pages", cwd=checkout)
        current = pages(args.repo)
        if current is None:
            creation = run("gh", "api", f"repos/{args.repo}/pages", "--method", "POST", "--input", "-",
                           input_text=json.dumps({"build_type": "legacy", "source": expected_source}), check=False)
            if creation.returncode:
                # Creation may have taken effect despite an error, or another
                # operation may have enabled Pages. Reconcile before retrying.
                current = pages(args.repo)
                if current is None:
                    raise RuntimeError(creation.stderr or creation.stdout)
            else:
                current = json.loads(creation.stdout)
        if current.get("source") != expected_source or current.get("build_type") == "workflow":
            raise RuntimeError("Pages source changed during publication; it was not overwritten")
        print(json.dumps({"published_branch_commit": run("git", "rev-parse", "HEAD", cwd=checkout).stdout.strip(),
                          "pages_status": current.get("status"), "url": plan["url"]}), flush=True)


if __name__ == "__main__":
    main()
