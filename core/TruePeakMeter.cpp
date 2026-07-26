#include "TruePeakMeter.h"

#include <algorithm>
#include <cmath>

namespace gs
{

namespace
{
    constexpr double pi = 3.14159265358979323846;
    constexpr double kaiserBeta = 8.6;

    double sinc (double x) noexcept
    {
        if (std::abs (x) < 1e-12)
            return 1.0;

        return std::sin (pi * x) / (pi * x);
    }

    /** Modified Bessel function of the first kind, order 0, by series. */
    double besselI0 (double x) noexcept
    {
        double sum = 1.0;
        double term = 1.0;

        for (int k = 1; k < 64; ++k)
        {
            term *= (x / (2.0 * (double) k)) * (x / (2.0 * (double) k));
            sum += term;

            if (term < sum * 1e-18)
                break;
        }

        return sum;
    }
}

void TruePeakMeter::designFilter()
{
    constexpr int length = oversample * tapsPerPhase;
    const double centre = (double) (length - 1) * 0.5;
    const double denom = besselI0 (kaiserBeta);

    std::vector<double> prototype ((size_t) length);

    for (int n = 0; n < length; ++n)
    {
        const double ratio = (2.0 * (double) n / (double) (length - 1)) - 1.0;
        const double window = besselI0 (kaiserBeta * std::sqrt (std::max (0.0, 1.0 - ratio * ratio))) / denom;

        // Cutoff at pi/oversample, i.e. the original Nyquist.
        prototype[(size_t) n] = sinc (((double) n - centre) / (double) oversample) * window;
    }

    phases.assign ((size_t) (oversample * tapsPerPhase), 0.0);

    for (int p = 0; p < oversample; ++p)
    {
        double sum = 0.0;

        for (int k = 0; k < tapsPerPhase; ++k)
        {
            const double tap = prototype[(size_t) (k * oversample + p)];
            phases[(size_t) (p * tapsPerPhase + k)] = tap;
            sum += tap;
        }

        // Unity DC gain per phase, so a constant input interpolates to itself.
        if (std::abs (sum) > 1e-12)
            for (int k = 0; k < tapsPerPhase; ++k)
                phases[(size_t) (p * tapsPerPhase + k)] /= sum;
    }
}

void TruePeakMeter::prepare (double /*sampleRate*/, int newNumChannels)
{
    numChannels = std::max (1, newNumChannels);
    designFilter();
    history.assign ((size_t) numChannels * (size_t) tapsPerPhase, 0.0);
    reset();
}

void TruePeakMeter::reset() noexcept
{
    std::fill (history.begin(), history.end(), 0.0);
    writePos = 0;
    peak = 0.0;
}

void TruePeakMeter::process (const float* const* channels, int numSamples) noexcept
{
    if (numChannels <= 0 || phases.empty())
        return;

    for (int n = 0; n < numSamples; ++n)
    {
        for (int ch = 0; ch < numChannels; ++ch)
        {
            double* line = history.data() + (size_t) ch * (size_t) tapsPerPhase;
            line[writePos] = (double) channels[ch][n];
        }

        // Advance first so index 0 of the convolution is the newest sample.
        writePos = (writePos + 1) % tapsPerPhase;

        for (int ch = 0; ch < numChannels; ++ch)
        {
            const double* line = history.data() + (size_t) ch * (size_t) tapsPerPhase;

            for (int p = 0; p < oversample; ++p)
            {
                const double* coeffs = phases.data() + (size_t) p * (size_t) tapsPerPhase;
                double acc = 0.0;

                for (int k = 0; k < tapsPerPhase; ++k)
                {
                    const int index = (writePos - 1 - k + 2 * tapsPerPhase) % tapsPerPhase;
                    acc += coeffs[k] * line[index];
                }

                peak = std::max (peak, std::abs (acc));
            }
        }
    }
}

double TruePeakMeter::truePeakDb() const noexcept
{
    if (! (peak > 0.0))
        return floorDb;

    return std::max (floorDb, 20.0 * std::log10 (peak));
}

} // namespace gs
