// Measures raw audio on stdin with the same engine the plugin uses.
//
// The plan always said core/ was shaped so a CLI could reuse it unchanged;
// this is that CLI. It exists so the plugin's defaults and presets can be
// derived from real material instead of guessed, and so the meter can be
// cross-checked against an independent implementation on real files rather
// than only on synthetic tones.
//
//   ffmpeg -v quiet -i in.wav -f f32le -ac 2 -ar 48000 - | gs_analyze 48000 2
//
// Prints one tab-separated line: lufs_i  rms_db  true_peak_db  short_term_max
//                                gated_s  total_s

#include "../LoudnessMeter.h"
#include "../TruePeakMeter.h"

#include <cstdio>
#include <cstdlib>
#include <vector>

int main (int argc, char** argv)
{
    const double sampleRate = argc > 1 ? std::atof (argv[1]) : 48000.0;
    const int channels = argc > 2 ? std::atoi (argv[2]) : 2;

    if (sampleRate <= 0.0 || channels <= 0 || channels > 8)
    {
        std::fprintf (stderr, "usage: gs_analyze <sampleRate> <channels>  (raw f32le on stdin)\n");
        return 2;
    }

    gs::LoudnessMeter meter;
    gs::TruePeakMeter peak;
    meter.prepare (sampleRate, channels);
    peak.prepare (sampleRate, channels);

    constexpr int frames = 4096;
    std::vector<float> interleaved ((size_t) frames * (size_t) channels);
    std::vector<std::vector<float>> planar ((size_t) channels, std::vector<float> ((size_t) frames));
    std::vector<const float*> pointers ((size_t) channels);

    long long totalFrames = 0;

    while (true)
    {
        const auto got = std::fread (interleaved.data(), sizeof (float),
                                     interleaved.size(), stdin);
        const auto n = (int) (got / (size_t) channels);

        if (n <= 0)
            break;

        for (int ch = 0; ch < channels; ++ch)
        {
            for (int i = 0; i < n; ++i)
                planar[(size_t) ch][(size_t) i] = interleaved[(size_t) (i * channels + ch)];

            pointers[(size_t) ch] = planar[(size_t) ch].data();
        }

        meter.process (pointers.data(), n);
        peak.process (pointers.data(), n);
        totalFrames += n;
    }

    if (totalFrames == 0)
    {
        std::fprintf (stderr, "gs_analyze: no audio on stdin\n");
        return 1;
    }

    std::printf ("%.3f\t%.3f\t%.3f\t%.3f\t%.3f\t%.3f\n",
                 meter.integratedLufs(),
                 meter.rmsDb(),
                 peak.truePeakDb(),
                 meter.shortTermMaxLufs(),
                 meter.gatedSeconds(),
                 (double) totalFrames / sampleRate);
    return 0;
}
