"""Update check: version comparison and GitHub responses, without touching the network."""
import io
import json

from voicefork import updates


def test_parse():
    assert updates.parse("v0.1.10") == (0, 1, 10)
    assert updates.parse("0.2") == (0, 2)
    assert updates.parse("v1.0.0-beta") == (1, 0, 0)
    assert updates.parse("nightly") == ()


def test_is_newer():
    assert updates.is_newer("v0.1.1", "0.1.0")
    assert updates.is_newer("v0.1.10", "0.1.9")      # numbers, not text
    assert updates.is_newer("v0.2", "0.1.9")
    assert not updates.is_newer("v0.1.0", "0.1.0")
    assert not updates.is_newer("v0.1", "0.1.0")
    assert not updates.is_newer("v0.0.9", "0.1.0")
    assert not updates.is_newer("garbage", "0.1.0")


def fake_github(monkeypatch, payload=None, fail=False):
    def urlopen(req, timeout):
        assert req.full_url == updates.API
        assert "Voicefork/" in req.get_header("User-agent")
        if fail:
            raise OSError("offline")
        return io.BytesIO(json.dumps(payload).encode())
    monkeypatch.setattr(updates.urllib.request, "urlopen", urlopen)
    monkeypatch.delenv("VOICEFORK_NO_UPDATE_CHECK", raising=False)


def test_check_finds_newer(monkeypatch):
    fake_github(monkeypatch, {"tag_name": "v99.0.0", "html_url": "https://github.com/x/releases/v99"})
    assert updates.check() == ("v99.0.0", "https://github.com/x/releases/v99", "")


def test_check_same_version(monkeypatch):
    fake_github(monkeypatch, {"tag_name": "v" + updates.__version__, "html_url": "u"})
    assert updates.check() is None


def test_check_offline_is_quiet(monkeypatch):
    fake_github(monkeypatch, fail=True)
    assert updates.check() is None


def test_prerelease_ignored(monkeypatch):
    fake_github(monkeypatch, {"tag_name": "v99.0.0", "prerelease": True})
    assert updates.check() is None


def test_can_be_turned_off(monkeypatch):
    fake_github(monkeypatch, {"tag_name": "v99.0.0"})
    monkeypatch.setenv("VOICEFORK_NO_UPDATE_CHECK", "1")
    assert updates.check() is None


def test_note_from_release_description():
    body = "## What's new\n- lots of stuff\n\n<!-- voicefork: Fixes GTX 1060 support & adds a desktop shortcut. -->\n"
    assert updates.note_from(body) == "Fixes GTX 1060 support & adds a desktop shortcut."


def test_note_is_optional_and_cleaned():
    assert updates.note_from("No note here") == ""
    assert updates.note_from(None) == ""
    assert updates.note_from("<!-- VoiceFork:   two\n lines <b>bold</b> -->") == "two lines bold"
    long = updates.note_from("<!-- voicefork: " + "x" * 500 + " -->")
    assert len(long) == updates.NOTE_MAX and long.endswith("…")


def test_check_returns_note(monkeypatch):
    fake_github(monkeypatch, {"tag_name": "v99.0.0", "html_url": "u",
                              "body": "Notes\n<!-- voicefork: Faster AI voices -->"})
    assert updates.check() == ("v99.0.0", "u", "Faster AI voices")
