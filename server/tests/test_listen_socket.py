import http.client
import socket
import sys
import threading

import pytest
from waitress import create_server

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


def test_stop_ends_the_loop_while_a_keep_alive_connection_is_open():
    """The app window keeps a connection open; closing only the listener left the service in STOP_PENDING."""

    def app(environ, start_response):
        start_response("200 OK", [("Content-Type", "text/plain"), ("Content-Length", "2")])
        return [b"ok"]

    server = create_server(app, sockets=[run_waitress.listen_socket("127.0.0.1", 0)], threads=2)
    loop = threading.Thread(target=server.run, daemon=True)
    loop.start()
    client = http.client.HTTPConnection("127.0.0.1", server.effective_port, timeout=5)
    try:
        client.request("GET", "/")
        assert client.getresponse().read() == b"ok"  # HTTP/1.1: the connection stays open
        run_waitress.stop(server)
        loop.join(timeout=5)
        assert not loop.is_alive()
    finally:
        client.close()
        server.task_dispatcher.shutdown(timeout=1)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows file sharing: an open file cannot be moved")
def test_restore_and_reset_refuse_a_database_another_process_holds(tmp_path):
    from django.core.management.base import CommandError

    from apps.backup.management.commands.restore_full import Command

    db = tmp_path / "hotel.db"
    db.write_bytes(b"")
    with open(db, "rb"), pytest.raises(CommandError, match="مستعملة"):
        Command._refuse_if_in_use(db)
    Command._refuse_if_in_use(db)  # closed again: free, and the file is where it was
    assert db.exists() and not (tmp_path / "hotel.db.move-check").exists()
