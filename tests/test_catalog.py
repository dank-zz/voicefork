"""Voice installer tests - no network: Hugging Face calls are stubbed."""
import sys
import types
import zipfile

import pytest

from voicefork.ai import assets, catalog


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("VOICECHANGER_HOME", str(tmp_path / "vc"))
    # make _check skip the torch verification (torch may be absent here)
    monkeypatch.setitem(sys.modules, "torch", None)
    return tmp_path


def test_match_index_prefers_named_added_index():
    idx = ["a/trained_x.index", "a/added_IVF1_Flat_x_v2.index", "b/added_y.index"]
    assert catalog._match_index("a/x.pth", idx) == "a/added_IVF1_Flat_x_v2.index"


def test_match_index_ambiguous_folder_gives_none():
    idx = ["models/added_one.index", "models/added_two.index"]
    assert catalog._match_index("models/three.pth", idx) is None


def test_repo_voices_skips_checkpoints(monkeypatch):
    sib = lambda f, s=1000: types.SimpleNamespace(rfilename=f, size=s)  # noqa: E731
    info = types.SimpleNamespace(siblings=[
        sib("Alice/Alice.pth"), sib("Alice/added_IVF9_Alice_v2.index"),
        sib("Alice/G_2333.pth"), sib("Alice/D_2333.pth"), sib("Bob.zip"), sib("README.md"),
    ])
    hub = types.ModuleType("huggingface_hub")
    hub.HfApi = lambda: types.SimpleNamespace(model_info=lambda *a, **k: info)
    monkeypatch.setitem(sys.modules, "huggingface_hub", hub)
    files = catalog.repo_voices("someone/voices")
    assert [f.path for f in files] == ["Alice/Alice.pth", "Bob.zip"]
    assert files[0].index == "Alice/added_IVF9_Alice_v2.index"
    assert files[0].default_name == "Alice"


def test_zip_install_cannot_escape_voice_folder(tmp_path):
    z = tmp_path / "v.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("../../evil.pth", b"x")
        f.writestr("deep/dir/added_v.index", b"i")
        f.writestr("readme.txt", b"no")
        f.writestr("G_100.pth", b"checkpoint")
    dest = catalog.install_from_file(z, "Zip Voice")
    assert sorted(p.name for p in dest.iterdir()) == ["added_v.index", "evil.pth"]
    assert dest.parent == assets.voices_dir()
    assert not (tmp_path / "evil.pth").exists()


def test_pth_install_picks_up_neighbour_index(tmp_path):
    d = tmp_path / "dl"
    d.mkdir()
    (d / "Nova.pth").write_bytes(b"x")
    (d / "added_IVF5_Nova_v2.index").write_bytes(b"i")
    dest = catalog.install_from_file(d / "Nova.pth", "Nova")
    assert {p.name for p in dest.iterdir()} == {"Nova.pth", "added_IVF5_Nova_v2.index"}
    assert "Nova" in assets.list_voices()


def test_name_collision_and_bad_names(tmp_path):
    p = tmp_path / "a.pth"
    p.write_bytes(b"x")
    catalog.install_from_file(p, 'My:Voice?')
    assert "MyVoice" in assets.list_voices()
    with pytest.raises(FileExistsError):
        catalog.install_from_file(p, "MyVoice")
