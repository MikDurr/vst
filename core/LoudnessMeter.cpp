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
    hopHistory.assign ((size_t) numChannels * 4, 0.0);

    const auto capacity = std::max<size_t> (16, (size_t) std::lround (maxSeconds * 10.0));
    blockPower.assign (capacity, 0.0);

    reset();
}

void LoudnessMeter::reset() noexcept
{
    for (auto& f : filters)
        f.reset();

    std::fill (hopSumSquares.begin(), hopSumSquares.end(), 0.0);
    std::fill (hopHistory.begin(), hopHistory.end(), 0.0);

    hopWritePos = 0;
    hopsFilled = 0;
    samplesIntoHop = 0;

    blockWritePos = 0;
    blocksStored = 0;
    wrapped = false;
}

void LoudnessMeter::process (const float* const* channels, int numSamples) noexcept
{
    if (filters.empty() || hopSamples <= 0)
        return;

    for (int n = 0; n < numSamples; ++n)
    {
        for (int ch = 0; ch < numChannels; ++ch)
        {
            const double y = filters[(size_t) ch].process ((double) channels[ch][n]);
            hopSumSquares[(size_t) ch] += y * y;
        }

        if (++samplesIntoHop < hopSamples)
            continue;

        // Close the hop.
        for (int ch = 0; ch < numChannels; ++ch)
        {
            hopHistory[(size_t) hopWritePos * (size_t) numChannels + (size_t) ch]
                = hopSumSquares[(size_t) ch];
            hopSumSquares[(size_t) ch] = 0.0;
        }

        hopWritePos = (hopWritePos + 1) % 4;
        hopsFilled = std::min (hopsFilled + 1, 4);
        samplesIntoHop = 0;

        if (hopsFilled < 4)
            continue;

        // A full 400 ms window is available; emit one block.
        double weightedPower = 0.0;

        for (int ch = 0; ch < numChannels; ++ch)
        {
            double sum = 0.0;
            for (int h = 0; h < 4; ++h)
                sum += hopHistory[(size_t) h * (size_t) numChannels + (size_t) ch];

            weightedPower += channelWeight (ch) * (sum / (double) blockSamples);
        }

        blockPower[(size_t) blockWritePos] = weightedPower;
        blockWritePos = (blockWritePos + 1) % (int) blockPower.size();

        if (blockWritePos == 0)
            wrapped = true;

        blocksStored = wrapped ? (int) blockPower.size() : blockWritePos;
    }
}

double LoudnessMeter::integratedLufs() const
{
    if (blocksStored <= 0)
        return silence;

    // Absolute gate.
    double sumAbsolute = 0.0;
    int countAbsolute = 0;

    for (int i = 0; i < blocksStored; ++i)
    {
        const double p = blockPower[(size_t) i];
        if (toLoudness (p) > absoluteGateLufs)
        {
            sumAbsolute += p;
            ++countAbsolute;
        }
    }

    if (countAbsolute == 0)
        return silence;

    // Relative gate, 10 LU below the mean of the survivors.
    const double relativeThreshold =
        toLoudness (sumAbsolute / (double) countAbsolute) - relativeGateLu;

    double sumGated = 0.0;
    int countGated = 0;

    for (int i = 0; i < blocksStored; ++i)
    {
        const double p = blockPower[(size_t) i];
        const double l = toLoudness (p);

        if (l > absoluteGateLufs && l > relativeThreshold)
        {
            sumGated += p;
            ++countGated;
        }
    }

    if (countGated == 0)
        return silence;

    return toLoudness (sumGated / (double) countGated);
}

double LoudnessMeter::gatedSeconds() const
{
    if (blocksStored <= 0)
        return 0.0;

    double sumAbsolute = 0.0;
    int countAbsolute = 0;

    for (int i = 0; i < blocksStored; ++i)
    {
        const double p = blockPower[(size_t) i];
        if (toLoudness (p) > absoluteGateLufs)
        {
            sumAbsolute += p;
            ++countAbsolute;
        }
    }

    if (countAbsolute == 0)
        return 0.0;

    const double relativeThreshold =
        toLoudness (sumAbsolute / (double) countAbsolute) - relativeGateLu;

    int countGated = 0;

    for (int i = 0; i < blocksStored; ++i)
    {
        const double l = toLoudness (blockPower[(size_t) i]);
        if (l > absoluteGateLufs && l > relativeThreshold)
            ++countGated;
    }

    // Blocks overlap by 75 %, so each additional gated block represents one hop
    // of new audio, not a whole block. Counting blocks would overstate by 4x.
    return (double) countGated * ((double) hopSamples / sampleRate);
}

} // namespace gs
