#pragma once

#include "PluginProcessor.h"
#include <juce_gui_basics/juce_gui_basics.h>

// Phase 0 editor: a diagnostic readout, not the real UI. It exists to confirm
// in Logic that the host prepared us at the rate/blocksize we expect and that
// audio is actually arriving. The UI in PLAN.md §6 phase 3 replaces this.
class GainStagerAudioProcessorEditor final : public juce::AudioProcessorEditor,
                                             private juce::Timer
{
public:
    explicit GainStagerAudioProcessorEditor (GainStagerAudioProcessor&);
    ~GainStagerAudioProcessorEditor() override;

    void paint (juce::Graphics&) override;
    void resized() override;

private:
    void timerCallback() override;

    GainStagerAudioProcessor& processorRef;
    juce::Label statusLabel;
    float heldPeak = 0.0f;

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR (GainStagerAudioProcessorEditor)
};
