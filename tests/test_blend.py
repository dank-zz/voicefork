"""Voice blending on fake checkpoints. Needs torch (skipped otherwise)."""
import pytest

torch = pytest.importorskip("torch")

from voicefork.ai import assets, blend  # noqa: E402


def fake(path, value, version="v2", sr=40000, spk=109, shape=(4, 4)):
    cpt = {
        "weight": {"dec.w": torch.full(shape, float(value), dtype=torch.float16),
                   "emb_g.weight": torch.full((spk, 3), float(value), dtype=torch.float16)},
        "config": [1, 2, 3, spk, 5, sr], "f0": 1, "version": version, "sr": f"{sr // 1000}k", "info": "x",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(cpt, str(path))
    return path


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("VOICEFORK_HOME", str(tmp_path / "vc"))


def test_blend_mixes_weights_and_keeps_one_speaker(tmp_path):
    a = fake(tmp_path / "A" / "a.pth", 0.0)
    b = fake(tmp_path / "B" / "b.pth", 1.0, spk=1)
    out = blend.blend(a, b, 0.25)
    assert torch.allclose(out["weight"]["dec.w"].float(), torch.full((4, 4), 0.25), atol=1e-3)
    assert out["weight"]["dec.w"].dtype == torch.float16
    assert out["weight"]["emb_g.weight"].shape == (1, 3) and out["config"][-3] == 1
    assert "75% A + 25% B" in out["info"]


def test_saved_blend_is_a_loadable_voice(tmp_path):
    a = fake(tmp_path / "A" / "a.pth", 0.0)
    b = fake(tmp_path / "B" / "b.pth", 1.0)
    path = blend.save_as_voice(blend.blend(a, b, 0.5), "Blend - test")
    assert "Blend - test" in assets.list_voices()
    torch.load(str(path), weights_only=True)          # the app's safe loader accepts it
    with pytest.raises(FileExistsError):
        blend.save_as_voice(blend.blend(a, b, 0.5), "Blend - test")


@pytest.mark.parametrize("kw,reason", [({"version": "v1"}, "versions"), ({"sr": 48000}, "sample rates"),
                                       ({"shape": (4, 5)}, "different size")])
def test_incompatible_voices_are_refused(tmp_path, kw, reason):
    a = fake(tmp_path / "A" / "a.pth", 0.0)
    b = fake(tmp_path / "B" / "b.pth", 1.0, **kw)
    with pytest.raises(ValueError, match=reason):
        blend.blend(a, b, 0.5)
