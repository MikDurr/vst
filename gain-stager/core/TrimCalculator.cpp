#include "TrimCalculator.h"

#include <algorithm>

namespace gs
{

bool isValidMeasurement (double value) noexcept
{
    return value > -150.0;
}

TrimResult computeTrim (double measured,
                        double target,
                        double truePeakDb,
                        double ceilingDb,
                        bool ceilingEnabled,
                        double maxTrimDb) noexcept
{
    TrimResult result;

    if (! isValidMeasurement (measured))
        return result;

    result.trimDb = std::clamp (target - measured, -maxTrimDb, maxTrimDb);

    // Applying the trim must not push peaks past the ceiling. Back off to
    // whatever lands exactly on it, and say so — under-trimming silently would
    // leave the track quieter than the readout claims.
    if (ceilingEnabled && isValidMeasurement (truePeakDb)
        && truePeakDb + result.trimDb > ceilingDb)
    {
        result.trimDb = std::clamp (ceilingDb - truePeakDb, -maxTrimDb, maxTrimDb);
        result.ceilingLimited = true;
    }

    return result;
}

} // namespace gs
