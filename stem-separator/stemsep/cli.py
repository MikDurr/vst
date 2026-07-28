"""Command line entry point: `python -m stemsep track.wav -o stems/`.

The UI is the main way in, but batch work (a folder of takes, a shell loop)
wants a CLI, and it's also the quickest way to check whether the engine itself
is working when the web app misbehaves.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .quick import QuickError, separate_quick
from .separate import DEFAULT_MODEL, MODELS, SeparationError, best_device, separate


def _bar(frac: float, msg: str) -> None:
    width = 28
    filled = int(frac * width)
    sys.stderr.write(f"\r  [{'█' * filled}{'·' * (width - filled)}] {frac * 100:3.0f}%  {msg[:40]:<40}")
    sys.stderr.flush()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="stemsep",
        description="Split a mix into stems.",
    )
    p.add_argument("input", type=Path, help="audio or video file")
    p.add_argument("-o", "--out", type=Path, default=Path("stems"),
                   help="output directory (default: ./stems)")
    p.add_argument("-m", "--model", default=DEFAULT_MODEL, choices=list(MODELS),
                   help=f"Demucs model (default: {DEFAULT_MODEL})")
    p.add_argument("--two-stems", action="store_true",
                   help="vocals + instrumental only, instead of all four")
    p.add_argument("--shifts", type=int, default=0, metavar="N",
                   help="shift-trick averaging passes; slower, slightly cleaner")
    p.add_argument("-d", "--device", default=None,
                   help="cpu / mps / cuda (default: fastest available)")
    p.add_argument("--quick", action="store_true",
                   help="use the no-model REPET-SIM engine (fast, rough)")
    args = p.parse_args(argv)

    out = args.out.expanduser()
    try:
        if args.quick:
            res = separate_quick(args.input, out, progress=_bar)
            paths = [res.vocals, res.accompaniment]
            detail = f"quick engine, {res.sr} Hz"
        else:
            r = separate(
                args.input, out,
                model=args.model,
                two_stems="vocals" if args.two_stems else None,
                shifts=args.shifts,
                device=args.device,
                progress=_bar,
            )
            paths = [s.path for s in r.stems]
            detail = f"{r.model} on {r.device}"
    except (SeparationError, QuickError) as e:
        sys.stderr.write(f"\n{e}\n")
        return 1

    sys.stderr.write("\n")
    print(f"{len(paths)} stems ({detail}):")
    for path in paths:
        print(f"  {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
