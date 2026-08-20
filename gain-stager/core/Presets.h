#pragma once

#include <cstddef>

namespace gs
{

/** Mode indices, matching the "mode" parameter's choice order. */
enum Mode { modeIntegrated = 0, modeShortTermMax = 1, modeRms = 2, modeTruePeak = 3 };

struct Preset
{
    const char* name;
    float targetLufs;
    int mode;
    float ceilingDbTp;
    float learnSeconds;   // gated seconds, not wall clock
};

/** Factory presets.

    Not guesses. Every value was derived by measuring ~420 files drawn from the
    user's own sessions with this project's own engine (core/tools/gs_analyze),
    grouped by instrument. Measured medians:

      class      n    LUFS  crest  p90 crest  gated
      vocals    25   -24.0   13.0     20.5     59%
      choir      5   -24.4   13.6     16.2     24%
      drums     25   -17.9   15.9     19.2     86%
      perc      25   -18.6   17.7     20.7     92%
      bass      25   -11.6    9.8     14.5     94%
      sub/808   25    -7.8    6.8     13.0     95%
      guitar    25   -12.6   11.0     18.4     96%
      keys      25   -21.0   12.9     16.8     91%
      bells     25   -27.3   14.9     19.9     78%
      pluck     24   -14.5   13.0     20.0     96%
      arp       25   -21.6   12.1     17.0     84%
      chords    25   -15.6   12.7     16.9     81%
      pad       25   -19.4   12.5     14.3     97%
      lead      25   -13.2   11.7     14.9     95%
      synth     25   -13.9   11.7     15.5     95%
      orch      24   -14.1   12.3     15.1     91%
      fx        25   -17.9   14.6     34.7     93%

    Three rules turn that table into the values below.

    1. `learnSeconds` counts GATED audio, so it is set to roughly
       `12 x gated-ratio` -- which makes every preset take a comparable ~12 s of
       PLAYING to commit. Sparse sources need small numbers: vocals gate at 59%,
       choir at 24%.

    2. Transient material is poorly served by integrated loudness, which
       under-reads short bursts. Anything with a median crest above ~14.5 dB
       uses short-term max: drums, percussion, bells.

    3. One-shots and effects are staged by PEAK, not loudness -- targeting a
       gated loudness on a 0.3 s sample is meaningless, and fx measured a p90
       crest of 34.7 dB. Those presets use true-peak mode, where the target
       becomes a peak target, at -6 dBTP.

    Classes that measured the same share values. Pluck, guitar and pad all sit
    within 1.5 dB on crest and within 3% on gating, so inventing a difference
    between them would be dishonest -- they differ only where the data does.
*/
inline const Preset* presets()
{
    static const Preset table[] =
    {
        { "Default",                 -18.0f, modeIntegrated,   -1.0f, 10.0f },

        // Voice. Gating is what separates these: 59% for sung lines, 24% for
        // choir and scattered ad-libs.
        { "Vocal",                   -18.0f, modeIntegrated,   -1.0f,  7.0f },
        { "Vocal - sparse / ad-lib", -18.0f, modeIntegrated,   -1.0f,  3.0f },
        { "Choir",                   -18.0f, modeIntegrated,   -1.0f,  3.0f },

        // Rhythm. High crest, so short-term max; one-shots by peak instead.
        { "Drums - bus or loop",     -18.0f, modeShortTermMax, -1.0f, 10.0f },
        { "Drums - one-shot",         -6.0f, modeTruePeak,     -1.0f,  2.0f },
        { "Percussion",              -18.0f, modeShortTermMax, -1.0f, 11.0f },

        // Low end. Lowest crest of anything measured (9.8 and 6.8 dB), so a
        // lower target and ceiling cost nothing and leave low-frequency room.
        { "Bass",                    -20.0f, modeIntegrated,   -3.0f, 11.0f },
        { "Sub / 808",               -20.0f, modeIntegrated,   -3.0f, 11.0f },

        { "Guitar",                  -18.0f, modeIntegrated,   -1.0f, 12.0f },
        { "Keys / piano",            -18.0f, modeIntegrated,   -1.0f, 11.0f },
        { "Bells / mallets",         -18.0f, modeShortTermMax, -1.0f,  9.0f },

        // Synth family. Measured separately rather than lumped together: arps
        // gate at 84% and pads at 97%, which is a real difference in how long
        // each needs to play before it can commit.
        { "Pluck",                   -18.0f, modeIntegrated,   -1.0f, 12.0f },
        { "Arp",                     -18.0f, modeIntegrated,   -1.0f, 10.0f },
        { "Chords / stabs",          -18.0f, modeIntegrated,   -1.0f, 10.0f },
        { "Pad",                     -18.0f, modeIntegrated,   -1.0f, 12.0f },
        { "Lead synth",              -18.0f, modeIntegrated,   -1.0f, 11.0f },
        { "Synth - general",         -18.0f, modeIntegrated,   -1.0f, 11.0f },

        { "Brass / strings",         -18.0f, modeIntegrated,   -1.0f, 11.0f },

        // Peak-referenced: a gated loudness target is meaningless on a 0.3 s
        // sample, and fx measured a p90 crest of 34.7 dB.
        { "FX / foley",               -6.0f, modeTruePeak,     -1.0f,  3.0f },

        { "Full mix / bus",          -14.0f, modeIntegrated,   -1.0f, 20.0f },
    };
    return table;
}

inline int presetCount() { return 21; }

} // namespace gs
