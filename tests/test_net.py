"""Offline mode really blocks connections (and DNS), but leaves this PC itself reachable."""
import socket
import threading
import urllib.error
import urllib.request

import pytest

from voicefork import net, updates


@pytest.fixture(autouse=True)
def online_after(monkeypatch):
    for k in net.LIB_ENV + (net.ENV,):
        monkeypatch.delenv(k, raising=False)
    yield
    net.set_offline(False)


def local_server():
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    threading.Thread(target=lambda: srv.accept()[0].close(), daemon=True).start()
    return srv


def test_blocks_outgoing_connections_and_dns():
    net.set_offline(True)
    with pytest.raises(net.OfflineError):
        socket.create_connection(("example.com", 443), timeout=2)
    with pytest.raises(net.OfflineError):
        socket.getaddrinfo("huggingface.co", 443)
    s = socket.socket()
    with pytest.raises(net.OfflineError):
        s.connect(("93.184.216.34", 80))          # a public IP, no DNS needed
    s.close()


def test_urllib_fails_before_sending_anything():
    net.set_offline(True)
    with pytest.raises(urllib.error.URLError) as e:
        urllib.request.urlopen("https://api.github.com/", timeout=2)
    assert isinstance(e.value.reason, net.OfflineError)


def test_proxies_are_switched_off_and_restored(monkeypatch):
    import os
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9")    # a proxy on this PC would leak
    net.set_offline(True)
    assert "HTTPS_PROXY" not in os.environ and os.environ["NO_PROXY"] == "*"
    assert urllib.request.getproxies() == {}
    net.set_offline(False)
    assert os.environ["HTTPS_PROXY"] == "http://127.0.0.1:9"
    assert urllib.request.getproxies() == net._orig_getproxies()


def test_this_pc_still_works():
    net.set_offline(True)
    srv = local_server()
    c = socket.create_connection(srv.getsockname(), timeout=2)
    c.close()
    srv.close()


def test_turning_it_off_restores_everything():
    original = socket.socket.connect
    net.set_offline(True)
    assert socket.socket.connect is not original
    net.set_offline(False)
    assert "connect" not in vars(socket.socket) and socket.socket.connect is original
    assert socket.getaddrinfo is net._orig["getaddrinfo"]


def test_sets_library_offline_flags_for_child_processes():
    import os
    net.set_offline(True)
    assert all(os.environ.get(k) == "1" for k in net.LIB_ENV)
    net.set_offline(False)
    assert not any(k in os.environ for k in net.LIB_ENV)


def test_no_update_check_and_clear_errors_when_offline():
    net.set_offline(True)
    assert updates.disabled() and updates.check() is None
    with pytest.raises(net.OfflineError) as e:
        net.require_online("Searching voices")
    assert "Searching voices" in str(e.value) and net.is_offline_error(str(e.value))


def test_env_variable_turns_it_on(monkeypatch):
    monkeypatch.setenv(net.ENV, "1")
    assert net.from_env()
    monkeypatch.setenv(net.ENV, "0")
    assert not net.from_env()
