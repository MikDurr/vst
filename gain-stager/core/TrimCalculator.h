#pragma once

namespace gs
{

/** Both meters use a large negative sentinel for "nothing measured yet"; no
    real programme material lands anywhere near this. */
bool isValidMeasurement (double value) noexcept;

struct TrimResult
{
    double trimDb = 0.0;

    /** True when the true-peak ceiling forced a smaller trim than the target
        asked for. The UI must surface this rather than silently under-trimming. */
    bool ceilingLimited = false;
};

/** The whole decision the plugin makes, in one testable function.

    @param measured        current reading, in the units of the active mode
    @param target          desired level, same units
    @param truePeakDb      measured true peak, dBTP
    @param ceilingDb       ceiling to respect, dBTP
    @param ceilingEnabled  whether to respect it at all
    @param maxTrimDb       symmetric clamp on the result
*/
TrimResult computeTrim (double measured,
                        double target,
                        double truePeakDb,
                        double ceilingDb,
                        bool ceilingEnabled,
                        double maxTrimDb = 24.0) noexcept;

} // namespace gs
