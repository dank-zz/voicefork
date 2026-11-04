"""Training orchestration without a GPU: filelist/config writing and the subprocess runner."""
import sys

import pytest

from voicefork.ai import training as tr
from voicefork.ai.training import SENTENCES, prompts


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("VOICEFORK_HOME", str(tmp_path / "vc"))


def test_prompts_mix_sentences_and_free_talk():
    p = prompts()
    assert p[0] == SENTENCES[0] and len(p) > len(SENTENCES)
    assert any(x.startswith("Talk freely") for x in p)


def test_filelist_and_config(tmp_path):
    job = tr.TrainJob("My Voice!", "Quick")
    for sub, ext in (("0_gt_wavs", ".wav"), ("3_feature768", ".npy"), ("2a_f0", ".wav.npy"), ("2b-f0nsf", ".wav.npy")):
        d = job.exp_dir / sub
        d.mkdir(parents=True)
        for n in ("0_0", "0_1", "0_2"):
            (d / f"{n}{ext}").write_bytes(b"")
    (job.exp_dir / "0_gt_wavs" / "only_here.wav").write_bytes(b"")   # incomplete piece: skipped
    assert job._write_filelist_and_config() == 3
    lines = (job.exp_dir / "filelist.txt").read_text().splitlines()
    assert len(lines) == 3 + 2                                          # + two silence (mute) lines
    assert all(line.endswith("|0") and line.count("|") == 4 for line in lines)
    assert (job.exp_dir / "config.json").is_file()
    assert job.exp.startswith("vf_My_Voice_")


def test_runner_streams_lines_and_reports_failures(tmp_path):
    ok = tmp_path / "ok.py"
    ok.write_text("print('====> Epoch: 7 1.2s', flush=True)\n")
    bad = tmp_path / "bad.py"
    bad.write_text("import sys\nprint('boom')\nsys.exit(3)\n")
    job = tr.TrainJob("v", "Quick")
    seen = []
    job._run(str(ok), on_line=seen.append)
    assert seen == ["====> Epoch: 7 1.2s"]
    with pytest.raises(RuntimeError, match="exit 3"):
        job._run(str(bad))


def test_cancel_stops_before_next_step(tmp_path):
    job = tr.TrainJob("v", "Quick")
    job.cancel()
    with pytest.raises(tr.Cancelled):
        job._run(sys.executable)
