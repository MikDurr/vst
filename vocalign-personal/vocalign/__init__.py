"""vocalign — align a doubled vocal take onto a guide take.

A personal VocAlign: matches the timing of a dub take to a guide take, and
optionally pulls its pitch toward the guide too. Two takes in, one aligned
44.1 kHz WAV out, ready to drop back into a DAW (and to run through Melodyne
or Flex Pitch afterwards if you want further pitch work).

This is a *production* tool, deliberately separate from the vocal training
studio it was prototyped in — different job, different headspace. The three
generic DSP modules it needs (audio.py, pitch.py, notes.py) were copied in
rather than imported, so this project stands on its own.
"""

from .vocalign import RENDERERS, AlignResult, align_takes

__all__ = ["align_takes", "AlignResult", "RENDERERS"]
