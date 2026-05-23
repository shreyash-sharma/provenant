import socket

import click
import pytest

from provenant.cli.commands.serve_cmd import _resolve_port


def _bound_port() -> tuple[socket.socket, int]:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    return sock, sock.getsockname()[1]


def test_resolve_port_returns_preferred_when_free() -> None:
    sock, port = _bound_port()
    sock.close()

    assert _resolve_port(label="API", host="127.0.0.1", preferred=port, explicit=False) == port


def test_resolve_port_auto_falls_back_for_default_port() -> None:
    sock, port = _bound_port()
    try:
        selected = _resolve_port(label="API", host="127.0.0.1", preferred=port, explicit=False)
    finally:
        sock.close()

    assert selected > port


def test_resolve_port_fails_for_explicit_busy_port() -> None:
    sock, port = _bound_port()
    try:
        with pytest.raises(click.ClickException, match="already in use"):
            _resolve_port(label="API", host="127.0.0.1", preferred=port, explicit=True)
    finally:
        sock.close()
