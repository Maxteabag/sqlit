from __future__ import annotations

from sqlit.domains.connections.domain.config import ConnectionConfig, FileEndpoint, TcpEndpoint


def test_from_dict_legacy_tcp_with_ssh() -> None:
    data = {
        "name": "legacy-tcp",
        "db_type": "postgresql",
        "server": "localhost",
        "port": "5432",
        "database": "postgres",
        "username": "user",
        "password": None,
        "ssh_enabled": True,
        "ssh_host": "bastion.example.com",
        "ssh_port": "2222",
        "ssh_username": "sshuser",
        "ssh_auth_type": "password",
        "ssh_password": "secret",
        "ssh_key_path": "",
        "auth_type": "sql",
        "trusted_connection": False,
        "options": {},
    }

    config = ConnectionConfig.from_dict(data)

    assert isinstance(config.endpoint, TcpEndpoint)
    assert config.tcp_endpoint is not None
    assert config.tcp_endpoint.host == "localhost"
    assert config.tcp_endpoint.port == "5432"
    assert config.tcp_endpoint.database == "postgres"
    assert config.tcp_endpoint.username == "user"
    assert config.tunnel is not None
    assert config.tunnel.enabled is True
    assert config.tunnel.host == "bastion.example.com"
    assert config.tunnel.port == "2222"
    assert config.tunnel.username == "sshuser"
    assert config.tunnel.auth_type == "password"
    assert config.options.get("auth_type") == "sql"
    assert config.options.get("trusted_connection") is False


def test_from_dict_legacy_file_path() -> None:
    data = {
        "name": "legacy-sqlite",
        "db_type": "sqlite",
        "file_path": "/tmp/test.db",
        "options": {},
    }

    config = ConnectionConfig.from_dict(data)

    assert isinstance(config.endpoint, FileEndpoint)
    assert config.file_endpoint is not None
    assert config.file_endpoint.path == "/tmp/test.db"


def test_from_dict_favorite_flag() -> None:
    data = {
        "name": "fav-conn",
        "db_type": "sqlite",
        "favorite": True,
        "options": {},
    }

    config = ConnectionConfig.from_dict(data)

    assert config.favorite is True


def test_from_dict_folder_path_normalized() -> None:
    data = {
        "name": "foldered",
        "db_type": "sqlite",
        "folder_path": "  Potato / Ninja  / ",
        "options": {},
    }

    config = ConnectionConfig.from_dict(data)

    assert config.folder_path == "Potato/Ninja"
