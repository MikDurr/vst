# vst

Audio tools for vocal production. Two standalone apps, each a Python engine
with a SvelteKit UI, run locally and independently.

| | What it does |
| --- | --- |
| [stem-separator](stem-separator/) | Splits a mix into vocals / drums / bass / other (Demucs), or vocals + instrumental with no model at all. Solo the stems against each other in the browser before committing. |
| [vocalign-personal](vocalign-personal/) | Time-aligns a dub take onto a guide take, optionally matching pitch too. |

## Running them

```bash
stemsep
vocalign
```

Those are launchers in `~/.local/bin` (already on PATH). They work from any
directory and open the browser once both servers answer; `NO_OPEN=1` suppresses
that. Each app's own `run.sh` does the real work and is equally fine to call
directly.

Ports are deliberately disjoint so everything can run at once — the vocal
training studio on 8000/5173, vocalign on 8010/5180, stemsep on 8020/5190.

First-time setup for either app:

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

Use Python 3.9 (`/usr/bin/python3`). It's the newest version with PyTorch
wheels for this Mac, and 3.14 has no numba wheels so librosa won't build there.

## What's not in the repo

Virtualenvs, `node_modules`, and `third_party/` (JUCE and the ARA SDK, ~100 MB
of vendored source — `vocalign-personal/.gitmodules` records where to fetch
them from).

Audio is excluded broadly, by extension and by directory. Both tools take
commercial recordings as input and write stems and renders beside them, and
audio committed to git history can't be removed by deleting the file later.
