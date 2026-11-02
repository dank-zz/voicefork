"""Repair the AI install and fetch the starter voices.  Run:  python fix_ai.py
Close VS Code terminals / other Python windows first so no files are locked.

1. Checks torch is a CUDA build (installs one if not).
2. Makes torchvision match torch, or removes it (the voice changer doesn't need it).
3. Checks the HuBERT import the app uses.
4. Downloads the female starter voices that aren't installed yet.
"""
import importlib.metadata as md
import subprocess
import sys

PY = sys.executable
CUDA_INDEX = "https://download.pytorch.org/whl/cu128"
FEMALE = ["p231", "p238", "p249", "p262", "p280", "p323", "p340"]
TV_CHECK = "import torchvision; from torchvision import io; from torchvision.transforms import InterpolationMode"


def pip(*args):
    print(">", "pip", " ".join(args), flush=True)
    return subprocess.call([PY, "-m", "pip", *args])


def version(pkg):
    try:
        return md.version(pkg)
    except md.PackageNotFoundError:
        return None


def probe(code):
    """Run code in a fresh interpreter (this one has stale imports)."""
    r = subprocess.run([PY, "-c", code], capture_output=True, text=True)
    return r.returncode == 0, (r.stdout + r.stderr).strip()


def done(ok_msg=None, fail_out=None):
    if fail_out is not None:
        print(fail_out[-2000:])
        input("\nIf it still fails, open an issue on GitHub with this output. Press Enter to close.")
        sys.exit(1)
    print(ok_msg)
    input("Press Enter to close.")
    sys.exit(0)


print(f"Python: {PY}")
print(f"torch {version('torch')}  torchvision {version('torchvision')}  "
      f"torchaudio {version('torchaudio')}  transformers {version('transformers')}\n")

# 1. CUDA torch
ok, out = probe("import torch; print(torch.version.cuda); assert torch.cuda.is_available()")
if ok:
    print(f"torch CUDA OK ({out.splitlines()[0]})")
else:
    print("torch is not a working CUDA build -> installing torch 2.7.1 + CUDA 12.8 (~2.5 GB)")
    pip("install", "--force-reinstall", "torch==2.7.1", "torchaudio==2.7.1", "--index-url", CUDA_INDEX)

# 2. torchvision: matching build, else remove completely
ok, out = probe(TV_CHECK)
if version("torchvision") and not ok:
    torch_v = version("torch").split("+")[0]
    print(f"\ntorchvision is broken -> reinstalling the build made for torch {torch_v}")
    pip("uninstall", "-y", "torchvision")
    pip("install", "--no-cache-dir", f"torch=={torch_v}", "torchvision", "--index-url", CUDA_INDEX)
    ok, out = probe(TV_CHECK)
    if not ok:
        print("still broken -> removing torchvision (not needed)")
        pip("uninstall", "-y", "torchvision")
print(f"torchvision: {'OK' if probe(TV_CHECK)[0] else 'not usable (the app will ignore it)'}")

# 3. the import the app actually does (through its torchvision guard)
ok, out = probe("import warnings; warnings.simplefilter('ignore'); import voicefork.ai._compat; "
                "import transformers.models.hubert.modeling_hubert; print('ok')")
print(f"HuBERT import: {'OK' if ok else 'FAILED'}")
if not ok:
    done(fail_out=out)

# 4. voices
print("\nDownloading female starter voices ...")
from voicefork.ai import assets  # noqa: E402

for spk in FEMALE:
    if assets.starter_installed(spk):
        print(f"  {spk}: already installed")
        continue
    print(f"  {spk}: downloading (~200 MB) ...", flush=True)
    try:
        print(f"    -> {assets.get_starter_voice(spk)}")
    except Exception as e:  # noqa: BLE001
        print(f"    failed: {e}")

done("\nAll done. Start the app with:  python -m voicefork gui")
