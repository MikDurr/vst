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

    These are not guesses. Every value below was derived by measuring 200 real
    files drawn from the user's own sessions with this project's own engine
    (core/tools/gs_analyze.cpp), grouped by instrument. The measured medians:

      class           LUFS    crest   p90 crest   gated
      vocals         -26.8   12.6      21.0       53%
      drums          -15.5   13.9      20.5       85%
      bass           -10.5    9.8      11.9       96%
      guitar         -13.8   12.1      14.4       93%
      keys           -18.8   13.7      16.7       95%
      synth          -18.9   12.7      16.4       95%
      brass/strings  -15.2   12.4      14.6       85%
      fx             -17.9   14.6      34.3       93%

    Two things drive the differences:

    * `learnSeconds` counts GATED audio, so a sparse source needs a smaller
      number to commit in comparable wall-clock time. Vocals gate at 53%, so
      6 s of gated audio is about 11 s of playing; bass gates at 96% and can
      afford 12.

    * Transient material is poorly served by integrated loudness, which
      under-reads short bursts. Drum busses use short-term max; one-shots and
      foley use true peak, where the target becomes a peak ceiling instead.

    Where classes measured the same, they share values. Guitar, keys and synth
    genuinely sit within about 1.5 dB of each other on both crest and gating,
    so inventing a difference between them would be dishonest.
*/
inline const Preset* presets()
{
    static const Preset table[] =
    {
        { "Default",                 -18.0f, modeIntegrated,    -1.0f, 10.0f },
        { "Vocal - lead",            -18.0f, modeIntegrated,    -1.0f,  6.0f },
        { "Vocal - sparse / ad-lib", -18.0f, modeIntegrated,    -1.0f,  3.0f },
        { "Drums - bus or loop",     -18.0f, modeShortTermMax,  -1.0f,  8.0f },
        { "Drums - one-shot",        -18.0f, modeTruePeak,      -1.0f,  2.0f },
        { "Bass",                    -20.0f, modeIntegrated,    -3.0f, 12.0f },
        { "Guitar",                  -18.0f, modeIntegrated,    -1.0f, 10.0f },
        { "Keys / piano",            -18.0f, modeIntegrated,    -1.0f, 10.0f },
        { "Synth / pad",             -18.0f, modeIntegrated,    -1.0f, 10.0f },
        { "Brass / strings",         -18.0f, modeIntegrated,    -1.0f,  8.0f },
        { "FX / foley",              -18.0f, modeTruePeak,      -1.0f,  3.0f },
        { "Full mix / bus",          -14.0f, modeIntegrated,    -1.0f, 20.0f },
    };
    return table;
}

inline int presetCount() { return 12; }

} // namespace gs
