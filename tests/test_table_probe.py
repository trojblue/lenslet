from __future__ import annotations

import socket

from lenslet.storage.table_probe import remote_url_has_public_address


def _addrinfo(address: str):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443))]


def test_remote_url_public_address_guard_accepts_public_https_host() -> None:
    assert remote_url_has_public_address(
        "https://images.example.test/path",
        resolver=lambda host, port, type: _addrinfo("93.184.216.34"),
    )


def test_remote_url_public_address_guard_rejects_private_resolution() -> None:
    assert not remote_url_has_public_address(
        "https://images.example.test/path",
        resolver=lambda host, port, type: _addrinfo("10.0.0.7"),
    )


def test_remote_url_public_address_guard_rejects_localhost_literals() -> None:
    assert not remote_url_has_public_address("http://127.0.0.1/image")
    assert not remote_url_has_public_address("http://[::1]/image")


def test_remote_url_public_address_guard_rejects_non_default_ports() -> None:
    assert not remote_url_has_public_address(
        "https://images.example.test:8443/path",
        resolver=lambda host, port, type: _addrinfo("93.184.216.34"),
    )


def test_remote_url_public_address_guard_rejects_credentials() -> None:
    assert not remote_url_has_public_address(
        "https://user:password@images.example.test/path",
        resolver=lambda host, port, type: _addrinfo("93.184.216.34"),
    )
