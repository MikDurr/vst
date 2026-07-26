#include "LoudnessMeter.h"

#include <algorithm>
#include <cmath>

namespace gs
{

namespace
{
    constexpr double pi = 3.14159265358979323846;

    // Exponent relating the shelf's mid-band gain to its high-band gain. Part of
    // the prototype that reproduces the BS.1770-4 48 kHz table.
    constexpr double shelfVbExponent = 0.4996667741545416;

    constexpr double absoluteGateLufs = -70.0;
    constexpr double relativeGateLu = 10.0;
    constexpr double loudnessOffset = -0.691;
}

//==============================================================================
Biquad KFilter::designShelf (double sampleRate)
{
    const double K = std::tan (pi * shelfF0 / sampleRate);
    const double Vh = std::pow (10.0, shelfGainDb / 20.0);
    const double Vb = std::pow (Vh, shelfVbExponent);
    const double KsqQ = K / shelfQ;
    const double Ksq = K * K;
    const double a0 = 1.0 + KsqQ + Ksq;

    Biquad b;
    b.b0 = (Vh + Vb * KsqQ + Ksq) / a0;
    b.b1 = 2.0 * (Ksq - Vh) / a0;
    b.b2 = (Vh - Vb * KsqQ + Ksq) / a0;
    b.a1 = 2.0 * (Ksq - 1.0) / a0;
    b.a2 = (1.0 - KsqQ + Ksq) / a0;
    return b;
}

Biquad KFilter::designHighpass (double sampleRate)
{
    const double K = std::tan (pi * hpF0 / sampleRate);
    const double KsqQ = K / hpQ;
    const double Ksq = K * K;
    const double a0 = 1.0 + KsqQ + Ksq;

    // The numerator stays exactly (1, -2, 1): BS.1770-4 specifies it unnormalised.
    Biquad b;
    b.b0 = 1.0;
    b.b1 = -2.0;
    b.b2 = 1.0;
    b.a1 = 2.0 * (Ksq - 1.0) / a0;
    b.a2 = (1.0 - KsqQ + Ksq) / a0;
    return b;
}

void KFilter::prepare (double sampleRate)
{
    shelf = designShelf (sampleRate);
    highpass = designHighpass (sampleRate);
    reset();
}

void KFilter::reset() noexcept
{
    s1z1 = s1z2 = s2z1 = s2z2 = 0.0;
}

double KFilter::process (double x) noexcept
{
    // Transposed direct form II, twice.
    const double y1 = shelf.b0 * x + s1z1;
    s1z1 = shelf.b1 * x - shelf.a1 * y1 + s1z2;
    s1z2 = shelf.b2 * x - shelf.a2 * y1;

    const double y2 = highpass.b0 * y1 + s2z1;
    s2z1 = highpass.b1 * y1 - highpass.a1 * y2 + s2z2;
    s2z2 = highpass.b2 * y1 - highpass.a2 * y2;

    return y2;
}

//==============================================================================
double LoudnessMeter::channelWeight (int index) noexcept
{
    // BS.1770-4 table 3. L, R, C unity; the surround pair 1.41. Mono and stereo
    // never reach the surround case.
    return (index == 3 || index == 4) ? 1.41 : 1.0;
}

double LoudnessMeter::toLoudness (double weightedPower) noexcept
{
    if (! (weightedPower > 0.0))
        return silence;

    return loudnessOffset + 10.0 * std::log10 (weightedPower);
}

void LoudnessMeter::prepare (double newSampleRate, int newNumChannels, double maxSeconds)
{
    sampleRate = newSampleRate;
    numChannels = std::max (1, newNumChannels);

    // 100 ms hop, and a 400 ms block built from exactly 4 hops. Deriving the
    // block from the hop keeps the 75 % overlap exact at every sample rate
    // rather than relying on 0.4*fs and 0.1*fs rounding compatibly.
    hopSamples = std::max (1, (int) std::lround (newSampleRate * 0.1));
    blockSamples = hopSamples * 4;
    blockLengthSeconds = (double) blockSamples / newSampleRate;

    filters.assign ((size_t) numChannels, KFilter());
    for (auto& f : filters)
        f.prepare (newSampleRate);

    hopSumSquares.assign ((size_t) numChannels, 0.0);
    hopSumSquaresRaw.assign ((size_t) numChannels, 0.0);
    hopHistory.assign ((size_t) numChannels * 4, 0.0);
    hopHistoryRaw.assign ((size_t) numChannels * 4, 0.0);

    shortTermRing.assign ((size_t) shortTermHops, 0.0);

    const auto capacity = std::max<size_t> (16, (size_t) std::lround (maxSeconds * 10.0));
    blockPower.assign (capacity, 0.0);
    blockPowerRaw.assign (capacity, 0.0);

    reset();
}

void LoudnessMeter::reset() noexcept
{
    for (auto& f : filters)
        f.reset();

    std::fill (hopSumSquares.begin(), hopSumSquares.end(), 0.0);
    std::fill (hopSumSquaresRaw.begin(), hopSumSquaresRaw.end(), 0.0);
    std::fill (hopHistory.begin(), hopHistory.end(), 0.0);
    std::fill (hopHistoryRaw.begin(), hopHistoryRaw.end(), 0.0);
    std::fill (shortTermRing.begin(), shortTermRing.end(), 0.0);

    hopWritePos = 0;
    hopsFilled = 0;
    samplesIntoHop = 0;

    shortTermSum = 0.0;
    shortTermPos = 0;
    shortTermFilled = 0;
    shortTermMaxPower.store (0.0, std::memory_order_relaxed);

    blockWritePos = 0;
    wrapped = false;
    blocksStored.store (0, std::memory_order_release);
}

void LoudnessMeter::process (const float* const* channels, int numSamples) noexcept
{
    if (filters.empty() || hopSamples <= 0)
        return;

    for (int n = 0; n < numSamples; ++n)
    {
        for (int ch = 0; ch < numChannels; ++ch)
        {
            const double x = (double) channels[ch][n];
            const double y = filters[(size_t) ch].process (x);
            hopSumSquares[(size_t) ch] += y * y;
            hopSumSquaresRaw[(size_t) ch] += x * x;
        }

        if (++samplesIntoHop < hopSamples)
            continue;

        //======================================================================
        // Close the hop.
        double weightedHopPower = 0.0;

        for (int ch = 0; ch < numChannels; ++ch)
        {
            const auto slot = (size_t) hopWritePos * (size_t) numChannels + (size_t) ch;
            hopHistory[slot] = hopSumSquares[(size_t) ch];
            hopHistoryRaw[slot] = hopSumSquaresRaw[(size_t) ch];

            weightedHopPower += channelWeight (ch)
                              * (hopSumSquares[(size_t) ch] / (double) hopSamples);

            hopSumSquares[(size_t) ch] = 0.0;
            hopSumSquaresRaw[(size_t) ch] = 0.0;
        }

        hopWritePos = (hopWritePos + 1) % 4;
        hopsFilled = std::min (hopsFilled + 1, 4);
        samplesIntoHop = 0;

        //======================================================================
        // Short-term: rolling 3 s mean over hop powers, tracking the maximum.
        shortTermSum -= shortTermRing[(size_t) shortTermPos];
        shortTermRing[(size_t) shortTermPos] = weightedHopPower;
        shortTermSum += weightedHopPower;
        shortTermPos = (shortTermPos + 1) % shortTermHops;
        shortTermFilled = std::min (shortTermFilled + 1, shortTermHops);

        if (shortTermFilled == shortTermHops)
        {
            const double stPower = shortTermSum / (double) shortTermHops;

            if (toLoudness (stPower) > absoluteGateLufs
                && stPower > shortTermMaxPower.load (std::memory_order_relaxed))
            {
                shortTermMaxPower.store (stPower, std::memory_order_relaxed);
            }
        }

        if (hopsFilled < 4)
            continue;

        //======================================================================
        // A full 400 ms window is available; emit one block.
        double weightedPower = 0.0;
        double rawPower = 0.0;

        for (int ch = 0; ch < numChannels; ++ch)
        {
            double sum = 0.0, sumRaw = 0.0;

            for (int h = 0; h < 4; ++h)
            {
                const auto slot = (size_t) h * (size_t) numChannels + (size_t) ch;
                sum += hopHistory[slot];
                sumRaw += hopHistoryRaw[slot];
            }

            weightedPower += channelWeight (ch) * (sum / (double) blockSamples);
            rawPower += sumRaw / (double) blockSamples;
        }

        // Raw is a per-channel mean, so a full-scale sine reads -3.01 dBFS RMS.
        rawPower /= (double) numChannels;

        blockPower[(size_t) blockWritePos] = weightedPower;
        blockPowerRaw[(size_t) blockWritePos] = rawPower;
        blockWritePos = (blockWritePos + 1) % (int) blockPower.size();

        if (blockWritePos == 0)
            wrapped = true;

        // Release: everything written above is visible to a reader that sees
        // this count.
        blocksStored.store (wrapped ? (int) blockPower.size() : blockWritePos,
                            std::memory_order_release);
    }
}

//==============================================================================
LoudnessMeter::GateResult LoudnessMeter::computeGated() const
{
    GateResult result;

    const int stored = blocksStored.load (std::memory_order_acquire);

    if (stored <= 0)
        return result;

    // Absolute gate.
    double sumAbsolute = 0.0;
    int countAbsolute = 0;

    for (int i = 0; i < stored; ++i)
    {
        const double p = blockPower[(size_t) i];

        if (toLoudness (p) > absoluteGateLufs)
        {
            sumAbsolute += p;
            ++countAbsolute;
        }
    }

    if (countAbsolute == 0)
        return result;

    // Relative gate, 10 LU below the mean of the survivors.
    const double relativeThreshold =
        toLoudness (sumAbsolute / (double) countAbsolute) - relativeGateLu;

    double sumGated = 0.0, sumGatedRaw = 0.0;
    int countGated = 0;

    for (int i = 0; i < stored; ++i)
    {
        const double p = blockPower[(size_t) i];
        const double l = toLoudness (p);

        if (l > absoluteGateLufs && l > relativeThreshold)
        {
            sumGated += p;
            sumGatedRaw += blockPowerRaw[(size_t) i];
            ++countGated;
        }
    }

    if (countGated == 0)
        return result;

    result.meanWeighted = sumGated / (double) countGated;
    result.meanRaw = sumGatedRaw / (double) countGated;
    result.count = countGated;
    return result;
}

double LoudnessMeter::integratedLufs() const
{
    const auto gated = computeGated();

    if (gated.count == 0)
        return silence;

    return toLoudness (gated.meanWeighted);
}

double LoudnessMeter::rmsDb() const
{
    const auto gated = computeGated();

    if (gated.count == 0 || ! (gated.meanRaw > 0.0))
        return silence;

    return 10.0 * std::log10 (gated.meanRaw);
}

double LoudnessMeter::shortTermMaxLufs() const
{
    const double p = shortTermMaxPower.load (std::memory_order_relaxed);
    return p > 0.0 ? toLoudness (p) : silence;
}

double LoudnessMeter::gatedSeconds() const
{
    const auto gated = computeGated();

    if (gated.count == 0)
        return 0.0;

    // Blocks overlap by 75 %, so each additional gated block represents one hop
    // of new audio, not a whole block. Counting blocks would overstate by 4x.
    return (double) gated.count * ((double) hopSamples / sampleRate);
}

} // namespace gs
