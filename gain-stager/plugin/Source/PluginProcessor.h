#pragma once

#include <juce_audio_processors/juce_audio_processors.h>

#include "LoudnessMeter.h"
#include "Presets.h"
#include "TrimCalculator.h"
#include "TruePeakMeter.h"

#include <atomic>

//==============================================================================
/** Auto gain staging: measure the track, apply one static trim, stop.

    Deliberately not dynamic. Anything that adjusts gain continuously over time
    is a leveler — it pumps, it fights the compressor after it, and it is a
    different plugin. See PLAN.md §0.
*/
class GainStagerAudioProcessor final : public juce::AudioProcessor,
                                       private juce::Timer
{
public:
    enum class State { Idle, Learn, Hold };

    /** Auto-commit fires once this much gated audio has accumulated, or once
        the callbacks stop for `transportIdleMs` with at least
        `minimumGatedSeconds` in hand.

        Phase 4 measured a real vocal: ~20 s of playback yielded 2.7 s of gated
        audio. The commit-on-stop path is therefore the one that fires in
        practice, and its threshold has to sit below what a single sung phrase
        produces — 3.0 s missed by a hair on real material. */
    static constexpr int transportIdleMs = 1500;
    static constexpr double minimumGatedSeconds = 2.0;

    GainStagerAudioProcessor();
    ~GainStagerAudioProcessor() override;

    void prepareToPlay (double sampleRate, int samplesPerBlock) override;
    void releaseResources() override;
    bool isBusesLayoutSupported (const BusesLayout& layouts) const override;
    void processBlock (juce::AudioBuffer<float>& buffer, juce::MidiBuffer& midi) override;

    juce::AudioProcessorEditor* createEditor() override;
    bool hasEditor() const override { return true; }

    const juce::String getName() const override { return JucePlugin_Name; }
    bool acceptsMidi() const override { return false; }
    bool producesMidi() const override { return false; }
    bool isMidiEffect() const override { return false; }
    double getTailLengthSeconds() const override { return 0.0; }
    juce::AudioProcessorParameter* getBypassParameter() const override { return bypassParam; }

    // Factory presets, exposed as AU programs so Logic lists them in its own
    // plugin header menu as well as in our editor.
    int getNumPrograms() override { return gs::presetCount(); }
    int getCurrentProgram() override { return currentProgram; }
    void setCurrentProgram (int index) override;
    const juce::String getProgramName (int index) override;
    void changeProgramName (int, const juce::String&) override {}

    void getStateInformation (juce::MemoryBlock& destData) override;
    void setStateInformation (const void* data, int sizeInBytes) override;

    //==========================================================================
    // UI-facing. All message thread.

    juce::AudioProcessorValueTreeState apvts;

    /** Drop everything learned so far and re-arm. */
    void requestReset();

    /** Commit whatever has been measured right now, regardless of duration. */
    void commitNow();

    State getState() const noexcept;

    double getMeasured() const noexcept      { return cachedMeasured.load(); }
    double getGatedSeconds() const noexcept  { return cachedGatedSeconds.load(); }
    double getTruePeakDb() const noexcept    { return cachedTruePeakDb.load(); }
    bool isCeilingLimited() const noexcept   { return ceilingLimited.load(); }

    /** What the target alone asked for, before the ceiling capped it. */
    double getRequestedTrimDb() const noexcept { return cachedRequestedTrim.load(); }

    /** Units of the current mode: LUFS for the loudness modes, dBFS otherwise. */
    juce::String getMeasurementUnit() const;

    /** Gated audio needed before auto-commit fires on its own. */
    double getLearnSeconds() const;

    /** True between pressing Reset and the audio thread actually clearing the
        meters. On a stopped transport this can persist indefinitely, which is
        why the UI must not present stale readings as current. */
    bool isResetPending() const noexcept { return resetPending.load(); }

    double getPreparedSampleRate() const noexcept { return preparedSampleRate.load(); }
    int    getPreparedBlockSize()  const noexcept { return preparedBlockSize.load(); }
    int    getActiveChannels()     const noexcept { return activeChannels.load(); }
    float  getPeakSinceLastRead() noexcept        { return peakSinceLastRead.exchange (0.0f); }

    static juce::AudioProcessorValueTreeState::ParameterLayout createParameterLayout();

private:
    static BusesProperties getBusesProperties();

    void timerCallback() override;

    /** The measurement the current mode cares about. Message thread. */
    double measureCurrent() const;

    /** Computes and stores the trim, then latches Hold. Message thread. */
    void commit();

    void setParamValue (juce::RangedAudioParameter* param, float value);

    //==========================================================================
    gs::LoudnessMeter meter;
    gs::TruePeakMeter truePeak;

    juce::SmoothedValue<float> gainSmoother;

    // Cached parameter pointers, looked up once.
    juce::AudioParameterFloat*  targetParam = nullptr;
    juce::AudioParameterChoice* modeParam = nullptr;
    juce::AudioParameterFloat*  trimParam = nullptr;
    juce::AudioParameterBool*   holdParam = nullptr;
    juce::AudioParameterBool*   autoLearnParam = nullptr;
    juce::AudioParameterFloat*  learnSecondsParam = nullptr;
    juce::AudioParameterFloat*  ceilingParam = nullptr;
    juce::AudioParameterBool*   ceilingEnabledParam = nullptr;
    juce::AudioParameterBool*   bypassParam = nullptr;

    // Audio thread performs the reset, because clearing the meter's buffers
    // from the message thread while process() is reading them is a race. It is
    // a one-off memset, cheap next to a block's budget.
    std::atomic<bool> resetPending { false };

    // Phase 0 finding: Logic stops calling processBlock entirely on a silent
    // track, so a stopped transport and a silent track are indistinguishable
    // from the audio thread. Transport-idle is therefore inferred from the age
    // of the last callback, on the message thread.
    std::atomic<juce::uint32> lastBlockMs { 0 };

    std::atomic<double> cachedMeasured { gs::LoudnessMeter::silence };
    std::atomic<double> cachedGatedSeconds { 0.0 };
    std::atomic<double> cachedTruePeakDb { gs::TruePeakMeter::floorDb };
    std::atomic<bool> ceilingLimited { false };
    std::atomic<double> cachedRequestedTrim { 0.0 };

    bool wasHeld = false;
    int currentProgram = 0;

    // Settings in force at the last commit. While held the measurement is
    // frozen, so if any of these move the trim must be recomputed from it --
    // otherwise the Target slider silently does nothing once committed.
    float committedTarget = 0.0f;
    float committedCeiling = 0.0f;
    bool committedCeilingEnabled = true;

    void recomputeTrimFromCommitted();

    std::atomic<double> preparedSampleRate { 0.0 };
    std::atomic<int>    preparedBlockSize  { 0 };
    std::atomic<int>    activeChannels     { 0 };
    std::atomic<float>  peakSinceLastRead  { 0.0f };

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR (GainStagerAudioProcessor)
};
