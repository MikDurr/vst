#pragma once

#include "PluginProcessor.h"
#include <juce_gui_basics/juce_gui_basics.h>

// Phase 2 editor: functional, not final. Enough controls to exercise the state
// machine in a real host and enough readout to see what it decided. The
// designed UI lands in Phase 3.
class GainStagerAudioProcessorEditor final : public juce::AudioProcessorEditor,
                                             private juce::Timer
{
public:
    explicit GainStagerAudioProcessorEditor (GainStagerAudioProcessor&);
    ~GainStagerAudioProcessorEditor() override;

    void paint (juce::Graphics&) override;
    void resized() override;

private:
    using SliderAttachment = juce::AudioProcessorValueTreeState::SliderAttachment;
    using ButtonAttachment = juce::AudioProcessorValueTreeState::ButtonAttachment;
    using ComboAttachment  = juce::AudioProcessorValueTreeState::ComboBoxAttachment;

    void timerCallback() override;
    juce::String describe (double value, const juce::String& unit) const;

    GainStagerAudioProcessor& processorRef;

    juce::Label statusLabel;

    juce::Label targetLabel { {}, "Target" };
    juce::Slider targetSlider;
    std::unique_ptr<SliderAttachment> targetAttachment;

    juce::Label modeLabel { {}, "Mode" };
    juce::ComboBox modeBox;
    std::unique_ptr<ComboAttachment> modeAttachment;

    juce::Label trimLabel { {}, "Trim" };
    juce::Slider trimSlider;
    std::unique_ptr<SliderAttachment> trimAttachment;

    juce::ToggleButton autoLearnButton { "Auto learn" };
    std::unique_ptr<ButtonAttachment> autoLearnAttachment;

    juce::TextButton holdButton { "Hold now" };
    juce::TextButton resetButton { "Reset" };

    float heldPeak = 0.0f;

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR (GainStagerAudioProcessorEditor)
};
