import socket

import pytest

from service import run_waitress


def test_a_second_server_cannot_bind_the_port_beside_the_first():
    first = run_waitress.listen_socket("127.0.0.1", 0)
    try:
        first.listen(5)
        port = first.getsockname()[1]
        # On Windows Waitress's SO_REUSEADDR allowed this second bind, splitting requests between two servers.
        with pytest.raises(OSError):
            run_waitress.listen_socket("127.0.0.1", port)
    finally:
        first.close()


def test_the_socket_is_bound_but_not_yet_listening():
    sock = run_waitress.listen_socket("127.0.0.1", 0)
    try:
        assert sock.family == socket.AF_INET and sock.getsockname()[1] > 0
    finally:
        sock.close()
