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

    const double targetTrim = std::clamp (target - measured, -maxTrimDb, maxTrimDb);
    result.trimDb = targetTrim;
    result.requestedTrimDb = targetTrim;

    if (! (ceilingEnabled && isValidMeasurement (truePeakDb)))
        return result;

    // The ceiling exists to stop the trim CREATING a peak problem, never to
    // normalise peaks that were already there. If the source already sits above
    // the ceiling, the most the ceiling may ask for is "do not make it worse" —
    // it must not drag a track down that the target was happy with, and turning
    // a track DOWN can never cause clipping, so a negative trim is always free.
    const double reachable = std::max (ceilingDb, truePeakDb);
    const double ceilingTrim = reachable - truePeakDb;   // never negative

    if (targetTrim > ceilingTrim)
    {
        result.trimDb = std::clamp (ceilingTrim, -maxTrimDb, maxTrimDb);
        result.ceilingLimited = true;
    }

    return result;
}

} // namespace gs
