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


def test_from_dict_folder_path_normalized() -> None:
    data = {
        "name": "foldered",
        "db_type": "sqlite",
        "folder_path": "  Potato / Ninja  / ",
        "options": {},
    }

    config = ConnectionConfig.from_dict(data)

    assert config.folder_path == "Potato/Ninja"


def test_from_dict_endpoint_password_command() -> None:
    data = {
        "name": "pc-test",
        "db_type": "postgresql",
        "endpoint": {
            "kind": "tcp",
            "host": "localhost",
            "port": "5432",
            "database": "db",
            "username": "user",
            "password": None,
            "password_command": "op read op://vault/item/password",
        },
    }
    config = ConnectionConfig.from_dict(data)
    assert config.tcp_endpoint is not None
    assert config.tcp_endpoint.password_command == "op read op://vault/item/password"


def test_from_dict_tunnel_password_command() -> None:
    data = {
        "name": "pc-test",
        "db_type": "postgresql",
        "endpoint": {"kind": "tcp", "host": "localhost", "port": "5432", "database": "db", "username": "user"},
        "tunnel": {
            "enabled": True,
            "host": "bastion",
            "port": "22",
            "username": "sshuser",
            "auth_type": "password",
            "password": None,
            "password_command": "bw get password ssh-bastion",
        },
    }
    config = ConnectionConfig.from_dict(data)
    assert config.tunnel is not None
    assert config.tunnel.password_command == "bw get password ssh-bastion"


def test_from_dict_legacy_ssh_password_command() -> None:
    data = {
        "name": "legacy-pc",
        "db_type": "postgresql",
        "server": "localhost",
        "port": "5432",
        "database": "db",
        "username": "user",
        "password_command": "echo dbpass",
        "ssh_enabled": True,
        "ssh_host": "bastion",
        "ssh_password_command": "echo sshpass",
    }
    config = ConnectionConfig.from_dict(data)
    assert config.tcp_endpoint is not None
    assert config.tcp_endpoint.password_command == "echo dbpass"
    assert config.tunnel is not None
    assert config.tunnel.password_command == "echo sshpass"


def test_to_dict_includes_password_command() -> None:
    config = ConnectionConfig.from_dict({
        "name": "t",
        "db_type": "postgresql",
        "endpoint": {
            "kind": "tcp",
            "host": "h",
            "port": "5432",
            "database": "d",
            "username": "u",
            "password_command": "echo pw",
        },
    })
    d = config.to_dict()
    assert d["endpoint"]["password_command"] == "echo pw"


def test_to_dict_omits_password_command_when_none() -> None:
    config = ConnectionConfig.from_dict({
        "name": "t",
        "db_type": "postgresql",
        "endpoint": {"kind": "tcp", "host": "h", "port": "5432", "database": "d", "username": "u"},
    })
    d = config.to_dict()
    assert "password_command" not in d["endpoint"]


def test_round_trip_password_command() -> None:
    original = {
        "name": "rt",
        "db_type": "postgresql",
        "endpoint": {
            "kind": "tcp",
            "host": "h",
            "port": "5432",
            "database": "d",
            "username": "u",
            "password": None,
            "password_command": "vault kv get -field=pw secret/db",
        },
        "tunnel": {
            "enabled": True,
            "host": "bastion",
            "port": "22",
            "username": "ssh",
            "auth_type": "password",
            "password": None,
            "password_command": "echo sshpw",
        },
    }
    config = ConnectionConfig.from_dict(original)
    d = config.to_dict()
    config2 = ConnectionConfig.from_dict(d)
    assert config2.tcp_endpoint is not None
    assert config2.tcp_endpoint.password_command == "vault kv get -field=pw secret/db"
    assert config2.tunnel is not None
    assert config2.tunnel.password_command == "echo sshpw"


def test_to_dict_include_passwords_false_keeps_password_command() -> None:
    config = ConnectionConfig.from_dict({
        "name": "t",
        "db_type": "postgresql",
        "endpoint": {
            "kind": "tcp",
            "host": "h",
            "port": "5432",
            "database": "d",
            "username": "u",
            "password": "secret",
            "password_command": "echo pw",
        },
    })
    d = config.to_dict(include_passwords=False)
    assert d["endpoint"]["password"] is None
    assert d["endpoint"]["password_command"] == "echo pw"
