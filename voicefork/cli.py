"""Command line front end.

  python -m voicefork devices                 list audio devices
  python -m voicefork presets                 list voices
  python -m voicefork run [--preset deep]     go live (mic -> VB-CABLE)
  python -m voicefork render in.wav out.wav --preset robot
"""
from __future__ import annotations

import argparse
import sys

import numpy as np

from .presets import PRESETS, build_chain


def cmd_presets(_args) -> None:
    for i, (name, (desc, _)) in enumerate(PRESETS.items(), 1):
        print(f"{i:>2}. {name:<10} {desc}")


def cmd_devices(_args) -> None:
    from .devices import list_devices
    list_devices()


def _meter(v: float, width: int = 20) -> str:
    db = 20 * np.log10(max(v, 1e-6))
    filled = int(np.clip((db + 60) / 60, 0, 1) * width)
    return "#" * filled + "-" * (width - filled)


def cmd_run(args) -> None:
    from .devices import find_device
    from .engine import VoiceEngine
    import sounddevice as sd

    inp = find_device(args.input, "input")
    out = find_device(args.output, "output")
    eng = VoiceEngine(inp, out, samplerate=args.samplerate, blocksize=args.blocksize,
                      preset=args.preset, gate_db=args.gate_db, gain_db=args.gain_db)
    try:
        eng.start()
    except sd.PortAudioError as e:
        sys.exit(f"Could not open audio devices: {e}\n"
                 "Tip: try a larger --blocksize, a different --samplerate, or pick devices from "
                 "the same host API (see: python -m voicefork devices).")

    names = list(PRESETS)
    print(f"Mic:    [{inp}] {sd.query_devices(inp)['name']}")
    print(f"Output: [{out}] {sd.query_devices(out)['name']}")
    print(f"Latency ~{eng.latency_ms:.0f} ms (+ effect delay), block {args.blocksize} @ {args.samplerate} Hz\n")
    cmd_presets(None)
    print("\nType a number/name to switch voice, 'm' = mute, Enter = status, 'q' = quit.")
    print("In Discord/OBS select 'CABLE Output' as your microphone.\n")
    try:
        while True:
            cmd = input(f"[{eng.preset}{' MUTED' if eng.muted else ''}]> ").strip().lower()
            if cmd in ("q", "quit", "exit"):
                break
            if cmd == "m":
                print("muted" if eng.toggle_mute() else "unmuted")
            elif cmd.isdigit() and 1 <= int(cmd) <= len(names):
                eng.set_preset(names[int(cmd) - 1])
            elif cmd in PRESETS:
                eng.set_preset(cmd)
            elif cmd == "":
                print(f"in  {_meter(eng.peak_in)}  out {_meter(eng.peak_out)}  "
                      f"cpu {eng.cpu_load * 100:4.1f}%  dropouts {eng.xruns}")
            else:
                print("unknown command")
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        eng.stop()


def render(x: np.ndarray, sr: int, preset: str, blocksize: int = 256, gate_db: float = -50.0) -> np.ndarray:
    """Run a preset over a mono float32 signal exactly like the live engine would."""
    chain = build_chain(preset, sr, gate_db)
    out = np.empty_like(x)
    for i in range(0, len(x), blocksize):
        out[i:i + blocksize] = chain.process(x[i:i + blocksize])
    return np.clip(out, -1, 1)


def cmd_render(args) -> None:
    from scipy.io import wavfile
    sr, data = wavfile.read(args.infile)
    if data.dtype.kind in "iu":
        data = data.astype(np.float32) / np.iinfo(data.dtype).max
    data = data.astype(np.float32)
    if data.ndim > 1:
        data = data.mean(axis=1)
    y = render(data, sr, args.preset, gate_db=args.gate_db)
    wavfile.write(args.outfile, sr, (y * 32767).astype(np.int16))
    print(f"wrote {args.outfile} ({args.preset}, {len(y) / sr:.1f}s)")


def main(argv=None) -> None:
    from . import net
    if net.from_env():
        net.set_offline(True)
    p = argparse.ArgumentParser(prog="voicefork", description="Open-source real-time voice changer")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("devices", help="list audio devices").set_defaults(func=cmd_devices)
    sub.add_parser("presets", help="list voices").set_defaults(func=cmd_presets)

    r = sub.add_parser("run", help="go live: mic -> effects -> virtual cable")
    r.add_argument("--input", help="mic device number or name (default: system mic)")
    r.add_argument("--output", help="output device number or name (default: VB-CABLE)")
    r.add_argument("--preset", default="clean", choices=list(PRESETS))
    r.add_argument("--samplerate", type=int, default=48000)
    r.add_argument("--blocksize", type=int, default=256, help="lower = less latency, more risk of crackle")
    r.add_argument("--gate-db", type=float, default=-50.0, help="noise gate threshold; -120 disables")
    r.add_argument("--gain-db", type=float, default=0.0, help="mic boost before effects")
    r.set_defaults(func=cmd_run)

    f = sub.add_parser("render", help="apply a preset to a .wav file (test voices without going live)")
    f.add_argument("infile")
    f.add_argument("outfile")
    f.add_argument("--preset", default="robot", choices=list(PRESETS))
    f.add_argument("--gate-db", type=float, default=-120.0)
    f.set_defaults(func=cmd_render)

    def cmd_gui(_args):
        from .gui import main as gui_main
        gui_main()
    sub.add_parser("gui", help="open the desktop app").set_defaults(func=cmd_gui)

    def cmd_shortcut(_args):
        from .shortcut import create
        print(create())
    sub.add_parser("shortcut", help="add Voicefork to the desktop and Start menu (Windows)").set_defaults(func=cmd_shortcut)

    from .ai.cli import register as register_ai
    register_ai(sub)

    args = p.parse_args(argv)
    args.func(args)
