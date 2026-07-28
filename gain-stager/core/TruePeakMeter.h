#pragma once

#include <vector>

namespace gs
{

/** 4x oversampled true-peak meter, per BS.1770-4 Annex 2's minimum oversampling
    factor for rates up to 48 kHz.

    This is a measurement side-chain only. It never sits in the audio path, so
    it contributes no latency — the plugin reports 0 samples and has no
    lookahead. Its only job is to clamp the computed trim so applying it cannot
    push peaks past the ceiling.

    Note on the filter: BS.1770-4 Annex 2 tabulates a specific 48-tap phase set.
    Rather than transcribe that table, the polyphase interpolator here is
    designed at runtime as a Kaiser-windowed sinc with the same structure
    (4 phases x 12 taps), each phase normalised to unity DC gain. For a safety
    ceiling this is equivalent in practice and it works at any sample rate; it
    is deliberately not claimed to be the literal Annex 2 filter.
*/
class TruePeakMeter
{
public:
    static constexpr int oversample = 4;
    static constexpr int tapsPerPhase = 12;

    /** Floor reported instead of -inf when nothing has been seen. */
    static constexpr double floorDb = -200.0;

    void prepare (double sampleRate, int numChannels);
    void reset() noexcept;

    /** Realtime-safe. `channels` is an array of `numChannels` pointers. */
    void process (const float* const* channels, int numSamples) noexcept;

    /** Highest interpolated absolute sample seen since the last reset. */
    double truePeak() const noexcept { return peak; }
    double truePeakDb() const noexcept;

private:
    void designFilter();

    int numChannels = 0;

    // phases[p * tapsPerPhase + k]
    std::vector<double> phases;

    // Per-channel delay line of the last `tapsPerPhase` input samples.
    std::vector<double> history;
    int writePos = 0;

    double peak = 0.0;
};

} // namespace gs
