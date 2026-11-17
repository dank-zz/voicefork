"""CUDA-graph fallback logic. Skipped unless torch is installed; none of these
need a GPU. They check that a capture/replay failure or low VRAM makes the
engine fall back to plain eager execution instead of crashing (the
captures_underway.empty() INTERNAL ASSERT crash reported against v0.1.3.x)."""
import pytest

torch = pytest.importorskip("torch")

from voicefork.ai.rvc_lib import cuda_graph as cg  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_state(monkeypatch):
    """Each test starts with graphs enabled and no session-wide disable."""
    cg._session_disabled = False
    monkeypatch.delenv(cg.ENV_NAME, raising=False)
    monkeypatch.delenv(cg.MIN_FREE_MB_ENV, raising=False)
    yield
    cg._session_disabled = False


def test_disable_is_sticky_and_idempotent():
    assert cg.cuda_graphs_session_disabled() is False
    cg.disable_cuda_graph("test")
    assert cg.cuda_graphs_session_disabled() is True
    cg.disable_cuda_graph("again")  # no error, stays disabled
    assert cg.cuda_graphs_session_disabled() is True


def test_cpu_device_is_never_graph_enabled():
    assert cg.cuda_graph_enabled(torch.device("cpu")) is False


def test_disabled_session_reports_not_enabled(monkeypatch):
    # even with the env flag on and CUDA available, a session disable wins
    monkeypatch.setenv(cg.ENV_NAME, "1")
    monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
    cg.disable_cuda_graph("test")
    assert cg.cuda_graph_enabled(torch.device("cuda")) is False


def test_run_cuda_graph_runs_eager_on_cpu():
    calls = []

    def fn(x):
        calls.append(1)
        return x * 2

    owner = object.__new__(type("Owner", (), {}))
    x = torch.arange(4, dtype=torch.float32)
    out = cg.run_cuda_graph(owner, "ns", fn, x)
    assert torch.equal(out, x * 2)
    assert calls == [1]
    # no cache object should have been created for an eager path
    assert getattr(owner, "_rvc_cuda_graph_cache", None) is None


def test_run_cuda_graph_eager_when_session_disabled(monkeypatch):
    monkeypatch.setenv(cg.ENV_NAME, "1")
    cg.disable_cuda_graph("test")

    def fn(x):
        return x + 1

    owner = object.__new__(type("Owner", (), {}))
    x = torch.zeros(3)
    out = cg.run_cuda_graph(owner, "ns", fn, x)
    assert torch.equal(out, x + 1)


def test_graphs_disabled_context_is_per_thread():
    assert getattr(cg._tls, "off", False) is False
    with cg.graphs_disabled():
        assert cg._tls.off is True
    assert getattr(cg._tls, "off", False) is False


@pytest.mark.parametrize("text, expected", [
    ("captures_underway.empty() INTERNAL ASSERT FAILED", True),
    ("Error in CUDACachingAllocator.cpp:3089", True),
    ("CUDA graph capture failed mid stream", True),
    ("some unrelated RuntimeError", False),
    ("out of memory", False),
])
def test_is_capture_state_error(text, expected):
    assert cg._is_capture_state_error(RuntimeError(text)) is expected


def test_enough_free_vram_uses_threshold(monkeypatch):
    monkeypatch.setattr(cg, "_free_mb", lambda device: 500.0)
    monkeypatch.setenv(cg.MIN_FREE_MB_ENV, "1024")
    assert cg._enough_free_vram(torch.device("cpu")) is False
    monkeypatch.setenv(cg.MIN_FREE_MB_ENV, "256")
    assert cg._enough_free_vram(torch.device("cpu")) is True


def test_enough_free_vram_bad_env_falls_back_to_default(monkeypatch):
    monkeypatch.setattr(cg, "_free_mb", lambda device: cg.DEFAULT_MIN_FREE_MB + 1)
    monkeypatch.setenv(cg.MIN_FREE_MB_ENV, "not-a-number")
    assert cg._enough_free_vram(torch.device("cpu")) is True


def test_graph_cache_replay_failure_disables_and_falls_back():
    """A replay that raises must disable graphs and return the eager result."""
    cache = cg._GraphCache()

    class BoomEntry:
        def replay(self, inputs):
            raise RuntimeError("captures_underway.empty() INTERNAL ASSERT FAILED")

    signature = ("ns",) + (cg._tensor_signature(torch.zeros(2)),)
    cache.entries[signature] = BoomEntry()

    def fn(x):
        return x + 5

    x = torch.zeros(2)
    # force the enabled path so run() reaches replay
    cg._session_disabled = False
    out = cache.run(("ns",), fn, (x,))
    assert torch.equal(out, x + 5)
    assert cg.cuda_graphs_session_disabled() is True
    assert cache.fallback_count == 1
