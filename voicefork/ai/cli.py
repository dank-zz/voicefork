"""`voicefork ai ...` commands. Imported lazily so the effects-only app never needs torch."""
from __future__ import annotations

import sys

from ..presets import PRESETS
from . import assets


def cmd_setup(_args) -> None:
    assets.download()


def cmd_voices(_args) -> None:
    names = assets.list_voices()
    if not names:
        print(f"No voices yet. Create {assets.voices_dir() / '<name>'} containing a .pth (+ added_*.index).")
    for i, n in enumerate(names, 1):
        print(f"{i:>2}. {n}")


def cmd_get_voice(args) -> None:
    keys = list(assets.STARTER) if args.speaker == ["all"] else args.speaker
    if not keys:
        print("Starter voices (VCTK corpus, consented speakers, Apache-2.0):")
        for k, (_, name, _) in assets.STARTER.items():
            mark = "installed" if assets.starter_installed(k) else ""
            print(f"  {k:6} {name:32} {mark}")
        print(f"\nListen first: https://huggingface.co/{assets.STARTER_REPO}  (speaker folders have a .flac)")
        print("Then: python -m voicefork get-voice p274 all_f    (or: get-voice all)")
        return
    for k in keys:
        if assets.starter_installed(k) and not args.force:
            print(f"{k}: already installed")
            continue
        print(f"{k}: downloading ...", flush=True)
        print(f"  -> {assets.get_starter_voice(k, with_index=True if args.with_index else None)}")


def cmd_bench(args) -> None:
    """Time the AI pipeline without audio devices, stage by stage."""
    import platform
    import time

    import numpy as np
    import torch

    from . import _compat
    from .engine import AIVoiceEngine, StreamSettings
    from .rvc import RVCVoice, SharedModels, VoiceSettings

    print(f"python {platform.python_version()}  torch {torch.__version__}  CUDA build: {torch.version.cuda}")
    print(f"cuda available: {torch.cuda.is_available()}"
          + (f"  GPU: {torch.cuda.get_device_name(0)}" if torch.cuda.is_available() else "  <-- running on CPU!"))
    if _compat.TORCHVISION_BROKEN:
        print("(torchvision is broken and being ignored - harmless)")
    device, half = _pick_device(args.device)
    shared = SharedModels(device, half)
    voice_name = args.voice or (assets.list_voices() or [None])[0]
    if voice_name is None:
        sys.exit("no voices installed")
    pth, idx = assets.find_voice(voice_name)

    for f0 in ("rmvpe", "fcpe"):
        for block in (0.12, 0.2):
            vs = VoiceSettings(f0_method=f0, index_rate=args.index_rate)
            voice = RVCVoice(pth, shared, vs, idx if args.index_rate > 0 else None)
            voice.sync_timing = True
            eng = AIVoiceEngine(voice, 0, 0, StreamSettings(block_time=block, gate_db=-120))
            t = np.arange(eng.block_frame) / eng.sr
            sig = (0.2 * np.sin(2 * np.pi * 160 * t) * (1 + 0.5 * np.sin(2 * np.pi * 3 * t))).astype(np.float32)
            out = np.zeros((eng.block_frame, 1), np.float32)
            for _ in range(5):  # warm-up / CUDA graph capture
                eng._process(sig, out)
            totals, stages = [], []
            for _ in range(20):
                if device.type == "cuda":
                    torch.cuda.synchronize()
                t0 = time.perf_counter()
                eng._process(sig, out)
                if device.type == "cuda":
                    torch.cuda.synchronize()
                totals.append(time.perf_counter() - t0)
                stages.append(voice.last_timings)
            tot = np.median(totals) * 1000
            h, i, p, v = (np.median([s[k] for s in stages]) * 1000 for k in range(4))
            print(f"{f0:5} block {block * 1000:3.0f} ms: {tot:6.1f} ms/block ({tot / (block * 10):3.0f}% load)"
                  f"  [hubert {h:.1f} | index {i:.1f} | pitch {p:.1f} | voice {v:.1f} | other {tot - h - i - p - v:.1f}]")


def _pick_device(choice: str):
    import torch
    if choice == "auto":
        choice = "cuda" if torch.cuda.is_available() else "cpu"
    if choice == "cuda" and not torch.cuda.is_available():
        sys.exit("CUDA not available. Install the CUDA build of PyTorch (see README) or use --device cpu.")
    dev = torch.device("cuda:0" if choice == "cuda" else choice)
    return dev, dev.type == "cuda"  # fp16 on NVIDIA: ~2x faster, no audible difference


def cmd_run(args) -> None:
    if assets.missing():
        sys.exit("Base models missing. Run once:  python -m voicefork ai-setup")
    import sounddevice as sd
    import torch

    from ..devices import find_device
    from .engine import AIVoiceEngine, StreamSettings
    from .rvc import RVCVoice, SharedModels, VoiceSettings

    device, half = _pick_device(args.device)
    if device.type == "cuda":
        torch.backends.cudnn.benchmark = True
        print(f"GPU: {torch.cuda.get_device_name(device)} (fp16)")
    shared = SharedModels(device, half)
    vs = VoiceSettings(pitch=args.pitch, formant=args.formant, index_rate=args.index_rate,
                       f0_method=args.f0)

    def load(name: str) -> RVCVoice:
        pth, idx = assets.find_voice(name)
        print(f"loading voice {pth.parent.name}/{pth.name}" + (f" + {idx.name}" if idx else ""))
        return RVCVoice(pth, shared, vs, idx if args.index_rate > 0 else None)

    voice = load(args.voice)
    st = StreamSettings(block_time=args.block, crossfade_time=args.crossfade,
                        context_time=args.context, gate_db=args.gate_db,
                        rms_mix=args.rms_mix, post_preset=args.post)
    inp = find_device(args.input, "input")
    out = find_device(args.output, "output")
    eng = AIVoiceEngine(voice, inp, out, st)
    print("warming up ...")
    try:
        eng.start()
    except sd.PortAudioError as e:
        sys.exit(f"Could not open audio devices: {e}")

    print(f"Mic:    [{inp}] {sd.query_devices(inp)['name']}")
    print(f"Output: [{out}] {sd.query_devices(out)['name']}  @ {eng.sr} Hz")
    print(f"Delay ~{eng.latency_ms:.0f} ms\n")
    print("Commands:  +/-  pitch by semitone   p <n> set pitch   f <n> formant   i <0-1> index mix")
    print("           v <name|number> switch voice   b bypass (your real voice)   m mute")
    print("           Enter = status   q = quit\n")
    voices = assets.list_voices()
    try:
        while True:
            cmd = input(f"[{eng.voice.name} p{vs.pitch:+g} f{vs.formant:+g}"
                        f"{' BYPASS' if eng.bypass else ''}{' MUTED' if eng.muted else ''}]> ").strip()
            low = cmd.lower()
            try:
                if low in ("q", "quit", "exit"):
                    break
                elif low in ("+", "-"):
                    vs.pitch += 1 if low == "+" else -1
                elif low.startswith("p "):
                    vs.pitch = float(cmd[2:])
                elif low.startswith("f "):
                    vs.formant = max(-5.0, min(5.0, float(cmd[2:])))
                elif low.startswith("i "):
                    vs.index_rate = max(0.0, min(1.0, float(cmd[2:])))
                    if eng.voice.index is None and vs.index_rate > 0:
                        print("this voice has no .index loaded (start with --index-rate > 0)")
                elif low.startswith("v "):
                    arg = cmd[2:].strip()
                    if arg.isdigit() and 1 <= int(arg) <= len(voices):
                        arg = voices[int(arg) - 1]
                    eng.switch_voice(load(arg))
                elif low == "b":
                    eng.bypass = not eng.bypass
                elif low == "m":
                    eng.muted = not eng.muted
                elif low == "":
                    f, i, p, m = (t * 1000 for t in eng.voice.last_timings)
                    print(f"block {eng.infer_ms:5.1f} ms of {args.block * 1000:.0f} ms ({eng.load * 100:.0f}% load)"
                          f"  [hubert {f:.1f} | index {i:.1f} | pitch {p:.1f} | voice {m:.1f}]"
                          f"  dropouts {eng.xruns}" + (f"  ERROR {eng.last_error}" if eng.last_error else ""))
                    if eng.load > 0.8:
                        print("  > close to the limit: raise --block, lower --context, or use --f0 fcpe")
                else:
                    print("unknown command")
            except (ValueError, SystemExit) as e:
                print(e)
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        eng.stop()


def register(sub) -> None:
    s = sub.add_parser("ai-setup", help="download the shared AI base models (once, ~550 MB)")
    s.set_defaults(func=cmd_setup)
    b = sub.add_parser("ai-bench", help="measure AI speed per stage (no audio devices needed)")
    b.add_argument("voice", nargs="?")
    b.add_argument("--index-rate", type=float, default=0.3)
    b.add_argument("--device", default="auto", choices=["auto", "cuda", "cpu"])
    b.set_defaults(func=cmd_bench)
    g = sub.add_parser("get-voice", help="download free starter AI voices (no args = list them)")
    g.add_argument("speaker", nargs="*", help="voice keys, or 'all'")
    g.add_argument("--with-index", action="store_true", help="also fetch the big .index of blend voices")
    g.add_argument("--force", action="store_true")
    g.set_defaults(func=cmd_get_voice)
    v = sub.add_parser("voices", help="list installed AI voices")
    v.set_defaults(func=cmd_voices)

    a = sub.add_parser("ai", help="go live with an AI voice (RVC)")
    a.add_argument("voice", help="voice folder name, folder path, or .pth file")
    a.add_argument("--pitch", type=float, default=0, help="semitones; +12 male->female, -12 female->male")
    a.add_argument("--formant", type=float, default=0.0, help="timbre shift in semitones (-2..2)")
    a.add_argument("--index-rate", type=float, default=0.0,
                   help="0-1; >0 loads the .index for closer timbre (slightly slower, can slur)")
    a.add_argument("--f0", choices=["rmvpe", "fcpe"], default="rmvpe",
                   help="pitch tracker: rmvpe = cleanest, fcpe = fastest")
    a.add_argument("--block", type=float, default=0.12, help="seconds per chunk (delay vs. GPU headroom)")
    a.add_argument("--crossfade", type=float, default=0.05)
    a.add_argument("--context", type=float, default=1.5, help="seconds of past audio for pronunciation")
    a.add_argument("--gate-db", type=float, default=-50.0)
    a.add_argument("--rms-mix", type=float, default=0.0, help="0 = keep your loudness dynamics")
    a.add_argument("--post", default=None, choices=list(PRESETS), help="effects preset applied after the AI voice, e.g. radio")
    a.add_argument("--input", help="mic device number or name")
    a.add_argument("--output", help="output device number or name (default: VB-CABLE)")
    a.add_argument("--device", default="auto", choices=["auto", "cuda", "cpu"])
    a.set_defaults(func=cmd_run)
