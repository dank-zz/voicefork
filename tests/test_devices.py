"""Virtual-cable detection and the setup text, with fake device lists (no audio hardware)."""
import pytest

try:
    import sounddevice  # noqa: F401  (needs the PortAudio library)
except (ImportError, OSError):
    pytest.skip("sounddevice/PortAudio not available", allow_module_level=True)

from voicefork.devices import SETUP, has_virtual_cable, is_virtual, setup_info  # noqa: E402


def dev(name, i=0, o=2):
    return {"name": name, "max_input_channels": i, "max_output_channels": o}


def test_is_virtual():
    assert is_virtual("CABLE Input (VB-Audio Virtual Cable)")
    assert is_virtual("BlackHole 2ch")
    assert is_virtual("VoiceMeeter Input (VB-Audio VoiceMeeter VAIO)")
    assert not is_virtual("Speakers (Realtek(R) Audio)")
    assert not is_virtual("Headphones (Yeti X)")
    assert not is_virtual("")


def test_has_virtual_cable_needs_a_playback_side():
    assert not has_virtual_cable([dev("Speakers (Realtek)"), dev("Microphone (Yeti X)", 1, 0)])
    # the recording side alone ("CABLE Output") isn't something we can play into
    assert not has_virtual_cable([dev("Speakers"), dev("CABLE Output (VB-Audio Virtual Cable)", 2, 0)])
    assert has_virtual_cable([dev("Speakers"), dev("CABLE Input (VB-Audio Virtual Cable)")])


def test_setup_info_per_platform():
    assert setup_info("win32")[0] == "VB-CABLE"
    assert setup_info("darwin")[0] == "BlackHole"
    assert setup_info("freebsd") == SETUP["linux"]
    for what, url, steps in SETUP.values():
        assert url.startswith("https://") and steps


def test_changes_lists_plugged_and_unplugged():
    from voicefork.devices import changes
    before = ["Speakers (Realtek)", "CABLE Input", "Headphones (Arctis)"]
    after = ["Speakers (Realtek)", "CABLE Input", "Microphone (Yeti X)", "Headphones (Yeti X)"]
    assert changes(before, after) == (["Microphone (Yeti X)", "Headphones (Yeti X)"], ["Headphones (Arctis)"])
    assert changes(after, after) == ([], [])
