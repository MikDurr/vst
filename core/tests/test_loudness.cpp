// Reference tests for the loudness core. No JUCE, no DAW, no audio device.
//
// The anchors are the two calibration statements that define the scale:
//   * BS.1770-4: a 0 dBFS 1 kHz sine on a single channel reads -3.01 LKFS.
//   * EBU Tech 3341 case 1: a 1 kHz sine at -23 dBFS in both channels of a
//     stereo pair reads -23.0 LUFS.
// Everything else here checks a property (linearity, gating, rate invariance)
// rather than a remembered constant.

#include "../LoudnessMeter.h"
#include "../TruePeakMeter.h"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <string>
#include <vector>

namespace
{

int failures = 0;
int checks = 0;

void check (bool ok, const std::string& what, const std::string& detail = {})
{
    ++checks;
    if (ok)
    {
        std::printf ("  ok    %s\n", what.c_str());
    }
    else
    {
        ++failures;
        std::printf ("  FAIL  %s   %s\n", what.c_str(), detail.c_str());
    }
}

void checkClose (double actual, double expected, double tolerance, const std::string& what)
{
    const double delta = std::abs (actual - expected);
    char detail[256];
    std::snprintf (detail, sizeof (detail),
                   "(got %.6f, expected %.6f, delta %.2e, tol %.2e)",
                   actual, expected, delta, tolerance);
    check (delta <= tolerance, what, detail);
}

constexpr double pi = 3.14159265358979323846;

/** Stereo (or mono) sine, `amplitude` is peak. */
std::vector<std::vector<float>> makeSine (double sampleRate, double seconds,
                                          double frequency, double amplitude,
                                          int numChannels)
{
    const auto n = (size_t) std::lround (sampleRate * seconds);
    std::vector<std::vector<float>> out ((size_t) numChannels, std::vector<float> (n, 0.0f));

    for (size_t i = 0; i < n; ++i)
    {
        const auto v = (float) (amplitude * std::sin (2.0 * pi * frequency * (double) i / sampleRate));
        for (int ch = 0; ch < numChannels; ++ch)
            out[(size_t) ch][i] = v;
    }

    return out;
}

std::vector<std::vector<float>> makeSilence (double sampleRate, double seconds, int numChannels)
{
    const auto n = (size_t) std::lround (sampleRate * seconds);
    return std::vector<std::vector<float>> ((size_t) numChannels, std::vector<float> (n, 0.0f));
}

void append (std::vector<std::vector<float>>& dst, const std::vector<std::vector<float>>& src)
{
    for (size_t ch = 0; ch < dst.size(); ++ch)
        dst[ch].insert (dst[ch].end(), src[ch].begin(), src[ch].end());
}

/** Feeds the meter in awkward chunk sizes on purpose, to stress hop boundaries
    that would be hidden by a chunk size that divides the hop evenly. */
void feed (gs::LoudnessMeter& meter, const std::vector<std::vector<float>>& audio,
           int chunkSize = 337)
{
    const auto numChannels = (int) audio.size();
    const auto total = audio[0].size();

    std::vector<const float*> pointers ((size_t) numChannels);

    for (size_t pos = 0; pos < total; pos += (size_t) chunkSize)
    {
        const auto n = (int) std::min ((size_t) chunkSize, total - pos);

        for (int ch = 0; ch < numChannels; ++ch)
            pointers[(size_t) ch] = audio[(size_t) ch].data() + pos;

        meter.process (pointers.data(), n);
    }
}

double measure (const std::vector<std::vector<float>>& audio, double sampleRate)
{
    gs::LoudnessMeter meter;
    meter.prepare (sampleRate, (int) audio.size());
    feed (meter, audio);
    return meter.integratedLufs();
}

//==============================================================================
void testCoefficientsAt48k()
{
    std::printf ("\nK-weighting coefficients vs the BS.1770-4 48 kHz table\n");

    // The published table. If the runtime design does not reproduce these, it
    // is wrong at every other rate too, silently.
    const auto shelf = gs::KFilter::designShelf (48000.0);
    checkClose (shelf.b0,  1.53512485958697, 1e-9, "shelf b0");
    checkClose (shelf.b1, -2.69169618940638, 1e-9, "shelf b1");
    checkClose (shelf.b2,  1.19839281085285, 1e-9, "shelf b2");
    checkClose (shelf.a1, -1.69065929318241, 1e-9, "shelf a1");
    checkClose (shelf.a2,  0.73248077421585, 1e-9, "shelf a2");

    const auto hp = gs::KFilter::designHighpass (48000.0);
    checkClose (hp.b0,  1.0, 1e-12, "highpass b0");
    checkClose (hp.b1, -2.0, 1e-12, "highpass b1");
    checkClose (hp.b2,  1.0, 1e-12, "highpass b2");
    checkClose (hp.a1, -1.99004745483398, 1e-8, "highpass a1");
    checkClose (hp.a2,  0.99007225036621, 1e-8, "highpass a2");
}

void testAbsoluteCalibration()
{
    std::printf ("\nAbsolute calibration\n");

    // BS.1770-4: 0 dBFS 1 kHz sine, single channel -> -3.01 LKFS.
    const auto mono = makeSine (48000.0, 20.0, 1000.0, 1.0, 1);
    checkClose (measure (mono, 48000.0), -3.01, 0.1, "0 dBFS 1 kHz sine, mono -> -3.01 LKFS");

    // EBU Tech 3341 case 1: 1 kHz sine at -23 dBFS, stereo -> -23.0 LUFS.
    const auto stereo = makeSine (48000.0, 20.0, 1000.0, std::pow (10.0, -23.0 / 20.0), 2);
    checkClose (measure (stereo, 48000.0), -23.0, 0.1, "-23 dBFS 1 kHz sine, stereo -> -23.0 LUFS");

    // Two identical channels sum to exactly +3.01 LU over one.
    const auto monoRef = makeSine (48000.0, 20.0, 1000.0, 0.5, 1);
    const auto stereoRef = makeSine (48000.0, 20.0, 1000.0, 0.5, 2);
    checkClose (measure (stereoRef, 48000.0) - measure (monoRef, 48000.0),
                3.0103, 0.01, "stereo is +3.01 LU over mono");
}

void testSampleRateInvariance()
{
    std::printf ("\nSample-rate invariance (the hardcoded-48k bug)\n");

    const double amplitude = std::pow (10.0, -23.0 / 20.0);
    const double at44 = measure (makeSine (44100.0, 20.0, 1000.0, amplitude, 2), 44100.0);
    const double at48 = measure (makeSine (48000.0, 20.0, 1000.0, amplitude, 2), 48000.0);
    const double at96 = measure (makeSine (96000.0, 20.0, 1000.0, amplitude, 2), 96000.0);

    std::printf ("        44.1k = %.4f   48k = %.4f   96k = %.4f LUFS\n", at44, at48, at96);

    checkClose (at44, at48, 0.1, "44.1 kHz agrees with 48 kHz");
    checkClose (at96, at48, 0.1, "96 kHz agrees with 48 kHz");

    // Phase 0 found Logic hands us 44.1 kHz on a real session, so this one is
    // the case that would actually have shipped broken.
    checkClose (at44, -23.0, 0.1, "44.1 kHz still reads -23.0 LUFS");
}

void testLinearity()
{
    std::printf ("\nLinearity\n");

    const auto quiet = makeSine (48000.0, 20.0, 1000.0, 0.1, 2);
    const auto loud = makeSine (48000.0, 20.0, 1000.0, 0.1 * std::pow (10.0, 6.0 / 20.0), 2);

    checkClose (measure (loud, 48000.0) - measure (quiet, 48000.0), 6.0, 0.01,
                "+6 dB of input raises the reading by 6 LU");
}

void testGating()
{
    std::printf ("\nGating\n");

    const double amplitude = std::pow (10.0, -23.0 / 20.0);
    const auto signalOnly = makeSine (48000.0, 20.0, 1000.0, amplitude, 2);

    // Absolute gate: appended digital silence must not drag the reading down.
    auto withSilence = signalOnly;
    append (withSilence, makeSilence (48000.0, 60.0, 2));

    checkClose (measure (withSilence, 48000.0), measure (signalOnly, 48000.0), 0.05,
                "60 s of appended silence does not change the reading");

    // A track that is mostly silence is the case plain RMS gets catastrophically
    // wrong: at 20 % duty an ungated mean reads 10*log10(0.2) = 7.0 dB low, i.e.
    // about -30 LUFS, and a trim computed from that would be 7 dB too hot.
    //
    // Gating removes almost all of that, but not quite all: with 400 ms blocks
    // at 75 % overlap, blocks straddling a tone/silence edge are genuinely
    // quieter and still clear the relative gate, so they pull the mean down a
    // little. That is correct R128 behaviour, and it scales with the number of
    // edges rather than the amount of silence — which is exactly what the two
    // cases below assert.
    auto makeSparse = [amplitude] (double onSeconds, double offSeconds, int repeats)
    {
        std::vector<std::vector<float>> out (2);
        for (int i = 0; i < repeats; ++i)
        {
            append (out, makeSine (48000.0, onSeconds, 1000.0, amplitude, 2));
            append (out, makeSilence (48000.0, offSeconds, 2));
        }
        return out;
    };

    // Same 20 % duty cycle in both, but the second has a fifth as many edges.
    const double choppy = measure (makeSparse (1.0, 4.0, 5), 48000.0);
    const double blocky = measure (makeSparse (5.0, 20.0, 5), 48000.0);

    std::printf ("        20%% duty, 1 s bursts  = %.4f LUFS\n", choppy);
    std::printf ("        20%% duty, 5 s bursts  = %.4f LUFS\n", blocky);

    checkClose (choppy, -23.0, 1.5, "80 %% silence reads within 1.5 LU of -23 (vs 7 dB low ungated)");
    checkClose (blocky, -23.0, 0.4, "fewer edges reads within 0.4 LU of -23");
    check (std::abs (blocky + 23.0) < std::abs (choppy + 23.0),
           "the deviation tracks edge count, not silence duration");

    // Relative gate: a passage 30 LU below the main one must be excluded.
    auto loudThenQuiet = makeSine (48000.0, 20.0, 1000.0, amplitude, 2);
    append (loudThenQuiet, makeSine (48000.0, 20.0, 1000.0,
                                     amplitude * std::pow (10.0, -30.0 / 20.0), 2));

    checkClose (measure (loudThenQuiet, 48000.0), -23.0, 0.2,
                "a passage 30 LU down is excluded by the relative gate");
}

void testDegenerateInput()
{
    std::printf ("\nDegenerate input\n");

    const auto silent = makeSilence (48000.0, 10.0, 2);
    const double result = measure (silent, 48000.0);

    check (result == gs::LoudnessMeter::silence, "pure silence returns the silence sentinel");
    check (! std::isnan (result), "pure silence does not produce NaN");
    check (! std::isinf (result), "pure silence does not produce inf");

    gs::LoudnessMeter meter;
    meter.prepare (48000.0, 2);
    const double empty = meter.integratedLufs();
    check (empty == gs::LoudnessMeter::silence, "no audio at all returns the silence sentinel");

    // Less than one full 400 ms window must not emit a block.
    const auto tiny = makeSine (48000.0, 0.2, 1000.0, 0.5, 2);
    gs::LoudnessMeter shortMeter;
    shortMeter.prepare (48000.0, 2);
    feed (shortMeter, tiny);
    check (shortMeter.blocksMeasured() == 0, "under 400 ms produces no blocks");
}

void testGatedSeconds()
{
    std::printf ("\nGated duration accounting\n");

    const double amplitude = std::pow (10.0, -23.0 / 20.0);
    auto audio = makeSine (48000.0, 10.0, 1000.0, amplitude, 2);
    append (audio, makeSilence (48000.0, 30.0, 2));

    gs::LoudnessMeter meter;
    meter.prepare (48000.0, 2);
    feed (meter, audio);

    const double gated = meter.gatedSeconds();
    std::printf ("        10 s tone + 30 s silence -> %.2f s gated\n", gated);

    // Should report roughly the tone duration, not the 40 s wall clock. This is
    // what drives auto-commit, so overcounting here would commit on almost no
    // data for a sparse vocal.
    checkClose (gated, 10.0, 0.75, "gated seconds tracks audio, not wall clock");
    checkClose (meter.blockSeconds(), 0.4, 1e-12, "block length is 400 ms");
}

void testTruePeak()
{
    std::printf ("\nTrue peak\n");

    gs::TruePeakMeter tp;
    tp.prepare (48000.0, 1);

    // A full-scale sine sampled right at its peaks: sample peak is 1.0 and true
    // peak should be very close to it.
    auto sine = makeSine (48000.0, 1.0, 1000.0, 1.0, 1);
    std::vector<const float*> ptr { sine[0].data() };
    tp.process (ptr.data(), (int) sine[0].size());
    const double onGrid = tp.truePeakDb();
    std::printf ("        1 kHz at 0 dBFS -> %.3f dBTP\n", onGrid);
    checkClose (onGrid, 0.0, 0.5, "0 dBFS 1 kHz sine reads about 0 dBTP");

    // The classic inter-sample case: fs/4 with a 45 degree phase offset has
    // sample peaks well below the true waveform peak.
    const auto n = (size_t) 48000;
    std::vector<float> tricky (n);
    for (size_t i = 0; i < n; ++i)
        tricky[i] = (float) std::sin (2.0 * pi * 12000.0 * (double) i / 48000.0 + pi / 4.0);

    double samplePeak = 0.0;
    for (auto v : tricky)
        samplePeak = std::max (samplePeak, (double) std::abs (v));

    gs::TruePeakMeter tp2;
    tp2.prepare (48000.0, 1);
    std::vector<const float*> ptr2 { tricky.data() };
    tp2.process (ptr2.data(), (int) n);

    const double samplePeakDb = 20.0 * std::log10 (samplePeak);
    std::printf ("        fs/4 +45 deg: sample peak %.3f dBFS, true peak %.3f dBTP\n",
                 samplePeakDb, tp2.truePeakDb());

    check (tp2.truePeakDb() > samplePeakDb + 2.0,
           "inter-sample peak is caught well above the sample peak");

    gs::TruePeakMeter tp3;
    tp3.prepare (48000.0, 1);
    auto silent = makeSilence (48000.0, 1.0, 1);
    std::vector<const float*> ptr3 { silent[0].data() };
    tp3.process (ptr3.data(), (int) silent[0].size());
    check (tp3.truePeakDb() <= -100.0, "silence reports a floor, not -inf or NaN");
    check (! std::isnan (tp3.truePeakDb()), "silence does not produce NaN");
}

} // namespace

int main()
{
    std::printf ("gain-stager :: loudness core reference tests\n");

    testCoefficientsAt48k();
    testAbsoluteCalibration();
    testSampleRateInvariance();
    testLinearity();
    testGating();
    testDegenerateInput();
    testGatedSeconds();
    testTruePeak();

    std::printf ("\n%d checks, %d failures\n", checks, failures);
    return failures == 0 ? 0 : 1;
}
