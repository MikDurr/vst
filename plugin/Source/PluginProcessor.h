#pragma once

#include <juce_audio_processors/juce_audio_processors.h>
#include <atomic>

//==============================================================================
// Phase 0: passthrough only. No metering, no gain, no parameters yet.
//
// Its job is to prove the AU shell is sound — auval passes, Logic loads it,
// zero reported latency — and to report back what the host actually hands us.
// The sample rate in particular matters: the K-weighting coefficients in
// Phase 1 have to be derived at whatever rate this reports, not hardcoded at
// 48 kHz. See PLAN.md §2.
class GainStagerAudioProcessor final : public juce::AudioProcessor
{
public:
    GainStagerAudioProcessor();
    ~GainStagerAudioProcessor() override = default;

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

    int getNumPrograms() override { return 1; }
    int getCurrentProgram() override { return 0; }
    void setCurrentProgram (int) override {}
    const juce::String getProgramName (int) override { return {}; }
    void changeProgramName (int, const juce::String&) override {}

    void getStateInformation (juce::MemoryBlock& destData) override;
    void setStateInformation (const void* data, int sizeInBytes) override;

    //==========================================================================
    // Read by the editor. Written from the audio thread, so all atomic.
    double getPreparedSampleRate() const noexcept { return preparedSampleRate.load(); }
    int    getPreparedBlockSize()  const noexcept { return preparedBlockSize.load(); }
    int    getActiveChannels()     const noexcept { return activeChannels.load(); }
    float  getPeakSinceLastRead() noexcept        { return peakSinceLastRead.exchange (0.0f); }
    int    getBlockCount()         const noexcept { return blockCount.load(); }

private:
    static BusesProperties getBusesProperties();

    std::atomic<double> preparedSampleRate { 0.0 };
    std::atomic<int>    preparedBlockSize  { 0 };
    std::atomic<int>    activeChannels     { 0 };
    std::atomic<float>  peakSinceLastRead  { 0.0f };
    std::atomic<int>    blockCount         { 0 };

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR (GainStagerAudioProcessor)
};
