from service import port

NETSTAT = """
Active Connections

  Proto  Local Address          Foreign Address        State           PID
  TCP    0.0.0.0:135            0.0.0.0:0              LISTENING       1188
  TCP    127.0.0.1:8471         0.0.0.0:0              LISTENING       23456
  TCP    127.0.0.1:8472         0.0.0.0:0              LISTENING       23457
  TCP    127.0.0.1:8471         127.0.0.1:52001        ESTABLISHED     23456
"""


def test_parse_netstat_finds_the_listener_pid_only():
    assert port.parse_netstat(NETSTAT, 8471) == 23456
    assert port.parse_netstat(NETSTAT, 8472) == 23457
    assert port.parse_netstat(NETSTAT, 8473) is None
    assert port.parse_netstat("", 8471) is None


def test_parse_tasklist_image_name():
    assert port.parse_tasklist('"python.exe","23456","Console","1","61,204 K"\n') == "python.exe"
    assert port.parse_tasklist("INFO: No tasks are running which match the specified criteria.\n") is None


def test_free_port_keeps_our_own_exe_and_ends_a_foreign_listener(monkeypatch):
    calls = []
    monkeypatch.setattr(port, "listener", lambda p: (23456, "python.exe"))
    monkeypatch.setattr(port, "_run", lambda args: calls.append(args) or "")
    assert port.free_port(8471) == "ended python.exe (PID 23456) which held port 8471"
    assert calls == [["taskkill", "/PID", "23456", "/F"]]

    calls.clear()
    monkeypatch.setattr(port, "listener", lambda p: (99, "skytowers-server.exe"))
    assert "left alone" in port.free_port(8471) and calls == []

    monkeypatch.setattr(port, "listener", lambda p: None)
    assert port.free_port(8471) == "port 8471 is free"
