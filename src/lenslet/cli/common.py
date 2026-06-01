from __future__ import annotations

import socket


def _port_is_available(host: str, port: int) -> bool:
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return False
    for family, socktype, proto, _, sockaddr in infos:
        try:
            with socket.socket(family, socktype, proto) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind(sockaddr)
                return True
        except OSError:
            continue
    return False


def _find_available_port(host: str, start_port: int = 7070, max_tries: int = 50) -> int:
    for offset in range(max_tries):
        port = start_port + offset
        if _port_is_available(host, port):
            return port
    raise RuntimeError(
        f"No available port found from {start_port} to {start_port + max_tries - 1}."
    )
