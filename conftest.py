"""Deterministic, network-free defaults for all repository unit tests."""

from __future__ import annotations

import ipaddress
import os
import socket

import pytest

# Set safe values before test modules import app.main. Environment values take
# precedence over ignored dotenv files without reading or exposing their content.
os.environ["CVPX_DISABLE_DOTENV"] = "1"
os.environ["APP_MODE"] = "localhost"
os.environ["REPOSITORY_MODE"] = "memory"
os.environ["ENABLE_EXPERIMENTAL_VIDEO"] = "false"
os.environ["APP_HOST"] = "127.0.0.1"
os.environ["FRONTEND_ORIGINS"] = "http://localhost:3000"
os.environ.pop("SUPABASE_URL", None)
os.environ.pop("SUPABASE_SERVICE_ROLE_KEY", None)


def _is_loopback_address(address: object) -> bool:
    if not isinstance(address, tuple) or not address:
        return False
    host = address[0]
    if not isinstance(host, str):
        return False
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


@pytest.fixture(autouse=True)
def forbid_external_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reject external TCP connections while allowing loopback clients."""

    original_connect = socket.socket.connect
    original_create_connection = socket.create_connection

    def guarded_connect(sock: socket.socket, address: object) -> object:
        if not _is_loopback_address(address):
            raise AssertionError("External network access is forbidden in unit tests.")
        return original_connect(sock, address)  # type: ignore[arg-type]

    def guarded_create_connection(address: object, *args: object, **kwargs: object):
        if not _is_loopback_address(address):
            raise AssertionError("External network access is forbidden in unit tests.")
        return original_create_connection(address, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket, "create_connection", guarded_create_connection)
