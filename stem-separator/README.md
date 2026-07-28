# stemsep

Splits a mix into stems, with a UI built for the thing you actually do after a
separation: solo the stems against each other and listen for what leaked.

Vocals / drums / bass / other via Demucs, or vocals + instrumental with no model
at all. Stereo and sample rate are preserved throughout — these are stems meant
to go straight back into a session.

This is the separator pulled out of `vocal-pitch-analyzer`, where it existed
only as a `--isolate-vocals` flag that handed a mono vocal to a pitch tracker.

## Running it

```bash
./run.sh
```

Engine on :8020, UI on :5190 — deliberately clear of the vocal training studio
(8000/5173) and vocalign (8010/5180), so all three can run at once.

First time:

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

Use Python 3.9 (`/usr/bin/python3` on this machine). It's the newest version
with PyTorch wheels for this Mac; 3.14 has no numba wheels, so librosa won't
install there either.

`requirements.txt` includes Demucs and PyTorch, which are ~2 GB. Skipping them
is supported: `/api/health` reports `demucs: false`, the UI greys out the model
controls and explains why, and the Quick engine still works.

## The two engines

**Demucs** — the real one. Four stems, a proper model. On Apple silicon it
picks MPS automatically and runs several times faster than CPU: about 6 seconds
for a 30-second clip on this machine. The first run downloads model weights
(~80 MB), which the progress bar reports as its own phase.

The Quality control is Demucs' shift-trick averaging. Each step roughly doubles
the time for a small gain — worth it on a final bounce, not while auditioning.
Note that `htdemucs_ft` and `mdx_extra` are *bags* of four models, so they cost
about 4x on their own before Quality multiplies anything.

**Quick** — no model, no torch, no download. A REPET-SIM repetition filter:
the accompaniment repeats, the lead vocal doesn't, so a median filter over
self-similar STFT frames estimates the background and the vocal is the
residual. About 28 seconds for a 3:20 track.

It is not close to Demucs and isn't meant to be. Expect burble on the vocal and
vocal bleed in the instrumental — fine as a guide track, not a release stem.
Its two outputs sum back to the original exactly, since the masks are
complementary.

## CLI

```bash
.venv/bin/python -m stemsep track.wav -o stems/
```

`--quick` for the no-model engine, `--two-stems` for vocals + instrumental,
`-m htdemucs_ft` to change model, `--shifts N` for averaging, `-d cpu` to
override device selection.

## Layout

| Path | What's in it |
| --- | --- |
| `stemsep/separate.py` | Demucs, driven as a subprocess |
| `stemsep/quick.py` | the REPET-SIM engine |
| `stemsep/jobs.py` | in-memory job registry + worker threads |
| `stemsep/cli.py` | command line entry point |
| `api/` | FastAPI wrapper — submit, poll, fetch stems |
| `web/` | SvelteKit UI |

## Notes on two decisions

**Demucs runs as a subprocess, not a library.** Importing it pulls torch into
the API process, which then holds a couple of GB resident for the whole session
whether or not anyone is separating anything — and a torch that trips over an
MPS edge case would take the API down with it. A subprocess gives the memory
back after every job, makes cancellation a kill, and puts progress on a pipe.

**Separation is a job, not a request.** A Demucs run is minutes long on CPU.
Holding a request open that long times out browsers and proxies and shows the
user nothing while it happens. The registry is in-memory and single-process on
purpose: this is a local tool for one person, and a real queue would mean
running Redis to coordinate someone with themselves. Restarting the API loses
running jobs, which is fine.

## If the page hangs on loading

Almost certainly a suspended Vite. `run.sh` uses `set -m` so cleanup can kill
whole process groups, which also means neither server is in the terminal's
foreground process group. Vite binds stdin in raw mode for its keyboard
shortcuts when it sees a TTY, and a background process group that reads the
controlling terminal gets SIGTTIN — whose default action is to suspend the
process. It comes up, gets stopped, and then holds :5190 open without ever
answering, so the browser spins forever against a perfectly healthy engine.

Both servers therefore take stdin from `/dev/null`, which is why the `<`
redirects in `run.sh` are not cosmetic.

To check for it:

```bash
ps -eo pid,stat,args | grep -E 'vite|uvicorn' | grep -v grep
```

A `T` in the STAT column means stopped. Note that a stopped process ignores
SIGTERM until it is resumed, so `pkill` appears to do nothing — use
`pkill -CONT -f vite` first, or `pkill -9`.

## Quality note

`stemsep/quick.py` analyses its mask on a coarser time grid than it applies it
on — `nn_filter` grows with the square of the frame count and was 72 of the
115 seconds a 3:20 track used to take. Measured against a full-resolution run,
the resulting vocal differs by about 12 dB down on the signal: audible if you
A/B closely, immaterial for what this engine is for. The frequency axis is
untouched. Set `_ANALYSIS_HOP = _RENDER_HOP` in that file to opt out.
