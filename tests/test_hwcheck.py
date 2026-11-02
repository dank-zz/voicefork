"""Mode selection for the one-time speed check (measurements faked)."""
from voicefork.ai.hwcheck import CPU_ORDER, GPU_ORDER, MODES, pick


def run(order, loads):
    calls = []

    def measure(mode):
        calls.append(mode)
        return loads[mode]
    return pick(order, measure), calls


def test_fast_gpu_keeps_balanced_and_stops_measuring():
    (mode, load, ok, _), calls = run(GPU_ORDER, {"Balanced": 0.3, "Fast": 0.2, "Laptop": 0.1})
    assert (mode, ok) == ("Balanced", True) and calls == ["Balanced"]


def test_weaker_gpu_falls_back_to_fast():
    (mode, _, ok, _), calls = run(GPU_ORDER, {"Balanced": 0.8, "Fast": 0.65, "Laptop": 0.4})
    assert (mode, ok) == ("Fast", True) and calls == ["Balanced", "Fast"]


def test_cpu_starts_with_laptop_mode():
    (mode, _, ok, _), _ = run(CPU_ORDER, {"Laptop": 0.6, "Fast": 2.0})
    assert (mode, ok) == ("Laptop", True)


def test_too_slow_pc_is_flagged_with_the_fastest_mode():
    (mode, load, ok, measured), _ = run(CPU_ORDER, {"Laptop": 1.4, "Fast": 2.5})
    assert (mode, ok) == ("Laptop", False) and load == 1.4 and set(measured) == {"Laptop", "Fast"}


def test_every_mode_in_the_orders_exists():
    assert {m for m, _ in GPU_ORDER + CPU_ORDER} <= set(MODES)
