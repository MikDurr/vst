#pragma once

#include <atomic>
#include <vector>
#include <cstddef>

namespace gs
{

//==============================================================================
/** A single biquad section, direct form II transposed. */
struct Biquad
{
    double b0 = 1.0, b1 = 0.0, b2 = 0.0, a1 = 0.0, a2 = 0.0;
};

//==============================================================================
/** ITU-R BS.1770-4 K-weighting: a high-shelf followed by an RLB high-pass.

    The coefficient tables published in BS.1770 are given at 48 kHz only, and
    hardcoding them is silently wrong at every other rate. Phase 0 confirmed
    Logic hands us 44.1 kHz on a real session, so both sections are derived
    analytically at the actual sample rate from the analog prototype constants
    below. `designShelf(48000)` reproduces the published table to ~1e-9, which
    the test suite asserts.
*/
class KFilter
{
public:
    // Prototype constants. These are the values for which the bilinear designs
    // below reproduce the BS.1770-4 48 kHz tables exactly.
    static constexpr double shelfF0 = 1681.974450955533;
    static constexpr double shelfGainDb = 3.999843853973347;
    static constexpr double shelfQ = 0.7071752369554196;

    static constexpr double hpF0 = 38.13547087602444;
    static constexpr double hpQ = 0.5003270373238773;

    static Biquad designShelf (double sampleRate);
    static Biquad designHighpass (double sampleRate);

    void prepare (double sampleRate);
    void reset() noexcept;

    double process (double x) noexcept;

private:
    Biquad shelf {}, highpass {};
    double s1z1 = 0.0, s1z2 = 0.0;
    double s2z1 = 0.0, s2z2 = 0.0;
};

//==============================================================================
/** Gated loudness measurement per BS.1770-4 / EBU R128.

    Mean square over 400 ms blocks at 75 % overlap, then two gates: an absolute
    gate at -70 LUFS, and a relative gate 10 LU below the mean of whatever
    survived the absolute one.

    The relative gate is the reason this exists instead of plain RMS. A vocal
    that is 60 % silence reads catastrophically low on RMS, and a trim computed
    from that would push the track 15 dB into the ceiling.

    Threading: `process()` is realtime-safe — no allocation, no locks, all
    storage sized in `prepare()`. The readers below run the gating and are for
    the message thread. Publication is a single-producer/single-consumer release
    store on `blocksStored`, so every block the reader can see is fully written.
*/
class LoudnessMeter
{
public:
    /** Returned when there is nothing above the absolute gate. */
    static constexpr double silence = -1000.0;

    /** Hops in the short-term window: 30 x 100 ms = 3 s, per EBU Tech 3341. */
    static constexpr int shortTermHops = 30;

    /** @param maxSeconds  capacity of the block ring; older blocks are dropped. */
    void prepare (double sampleRate, int numChannels, double maxSeconds = 3600.0);
    void reset() noexcept;

    /** Realtime-safe. `channels` is an array of `numChannels` pointers. */
    void process (const float* const* channels, int numSamples) noexcept;

    //==========================================================================
    // Readers. Message thread.

    /** Gated integrated loudness in LUFS, or `silence`. */
    double integratedLufs() const;

    /** Loudest 3 s short-term window seen, in LUFS, or `silence`. Tracked
        incrementally on the audio thread rather than from the block history. */
    double shortTermMaxLufs() const;

    /** Unweighted RMS in dBFS over the same gated block selection as
        `integratedLufs()`, for traditional -18 dBFS RMS staging. */
    double rmsDb() const;

    /** Seconds of audio that survived both gates — the honest measure of how
        much has actually been learned from, and what drives auto-commit. */
    double gatedSeconds() const;

    int blocksMeasured() const noexcept { return blocksStored.load (std::memory_order_acquire); }
    double blockSeconds() const noexcept { return blockLengthSeconds; }

private:
    /** Channel weights G_i from BS.1770-4 table 3: unity for L/R/C, 1.41 for
        the surround pair. Mono and stereo are therefore all-unity. */
    static double channelWeight (int index) noexcept;

    static double toLoudness (double weightedPower) noexcept;

    struct GateResult
    {
        double meanWeighted = 0.0;
        double meanRaw = 0.0;
        int count = 0;
    };

    /** Runs both gates once. Every public reader is a view onto this. */
    GateResult computeGated() const;

    double sampleRate = 0.0;
    int numChannels = 0;

    int hopSamples = 0;          // 100 ms
    int blockSamples = 0;        // 400 ms == 4 hops, giving exact 75 % overlap
    double blockLengthSeconds = 0.0;

    std::vector<KFilter> filters;         // one per channel
    std::vector<double> hopSumSquares;    // K-weighted, current hop, per channel
    std::vector<double> hopSumSquaresRaw; // unweighted, current hop, per channel
    std::vector<double> hopHistory;       // [hop * numChannels + ch], 4 hops
    std::vector<double> hopHistoryRaw;
    int hopWritePos = 0;
    int hopsFilled = 0;
    int samplesIntoHop = 0;

    // Rolling 3 s window for short-term, kept as a running sum over hop powers.
    std::vector<double> shortTermRing;
    double shortTermSum = 0.0;
    int shortTermPos = 0;
    int shortTermFilled = 0;
    std::atomic<double> shortTermMaxPower { 0.0 };

    // One value per 400 ms block. Storing the channel-weighted sum rather than
    // per-channel values is exact: the gating means are linear in z, so
    // sum-then-mean and mean-then-sum agree.
    std::vector<double> blockPower;
    std::vector<double> blockPowerRaw;
    int blockWritePos = 0;
    std::atomic<int> blocksStored { 0 };
    bool wrapped = false;
};

} // namespace gs
