#pragma once

#include "PluginProcessor.h"
#include <juce_gui_basics/juce_gui_basics.h>

//==============================================================================
/** Palette. Dark enough to sit inside Logic's own chrome without shouting. */
namespace theme
{
    const juce::Colour background   { 0xff16171a };
    const juce::Colour panel        { 0xff1e2025 };
    const juce::Colour panelEdge    { 0xff2b2e35 };
    const juce::Colour textBright   { 0xffe9eaee };
    const juce::Colour textDim      { 0xff7b808b };
    const juce::Colour textFaint    { 0xff4e535c };

    const juce::Colour idle         { 0xff6b7280 };
    const juce::Colour learn        { 0xffe0a13a };
    const juce::Colour hold         { 0xff45b26b };
    const juce::Colour warning      { 0xffe05a52 };
}

//==============================================================================
class GainStagerLookAndFeel final : public juce::LookAndFeel_V4
{
public:
    GainStagerLookAndFeel();

    void drawLinearSlider (juce::Graphics&, int x, int y, int width, int height,
                           float sliderPos, float minSliderPos, float maxSliderPos,
                           juce::Slider::SliderStyle, juce::Slider&) override;

    void drawComboBox (juce::Graphics&, int width, int height, bool isButtonDown,
                       int buttonX, int buttonY, int buttonW, int buttonH,
                       juce::ComboBox&) override;

    void drawButtonBackground (juce::Graphics&, juce::Button&,
                               const juce::Colour& backgroundColour,
                               bool shouldDrawButtonAsHighlighted,
                               bool shouldDrawButtonAsDown) override;

    void drawTickBox (juce::Graphics&, juce::Component&,
                      float x, float y, float w, float h,
                      bool ticked, bool isEnabled,
                      bool shouldDrawButtonAsHighlighted,
                      bool shouldDrawButtonAsDown) override;

    juce::Label* createSliderTextBox (juce::Slider&) override;
};

//==============================================================================
/** The designed editor.

    Phase 4 decided the priorities here. Two numbers carry the plugin — what it
    measured and what it is doing about it — so they are the only large type on
    the panel. Everything else was a bug found in a real session: the learn
    progress is drawn because a silent LEARN state was indistinguishable from a
    stuck one, and the ceiling warning gets a full banner because a quietly
    reduced trim is a mix that is wrong without looking wrong.
*/
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

    void paintHeader (juce::Graphics&, juce::Rectangle<int>);
    void paintReadouts (juce::Graphics&, juce::Rectangle<int>);

    /** Progress, status text and the ceiling warning share one panel. Reserving
        separate space for a warning that is usually absent left a large dead
        zone; folding it in also means the warning changes the panel's whole
        character rather than appearing as one more line. */
    void paintStatus (juce::Graphics&, juce::Rectangle<int>);

    void paintReadout (juce::Graphics&, juce::Rectangle<int>,
                       const juce::String& caption,
                       const juce::String& value,
                       const juce::String& unit,
                       juce::Colour valueColour) const;

    juce::Colour stateColour() const;
    juce::String stateName() const;

    /** What the plugin is waiting for, in words. Never leave this blank — an
        idle LEARN with no explanation is the exact failure Phase 4 hit. */
    juce::String statusLine() const;

    GainStagerAudioProcessor& processorRef;
    GainStagerLookAndFeel lookAndFeel;

    // Snapshot pulled on the timer so paint() never touches atomics twice.
    GainStagerAudioProcessor::State state {};
    double measured = 0.0;
    double trimDb = 0.0;
    double gatedSeconds = 0.0;
    double truePeakDb = 0.0;
    double learnSeconds = 0.0;
    double ceilingDb = 0.0;
    bool ceilingLimited = false;
    bool resetPending = false;
    juce::String unit { "LUFS" };

    juce::Label presetLabel, targetLabel, trimLabel, modeLabel, ceilingLabel, learnLabel;
    juce::ComboBox presetBox;
    int shownProgram = -1;
    juce::Slider targetSlider, trimSlider, ceilingSlider, learnSlider;
    juce::ComboBox modeBox;
    juce::ToggleButton ceilingToggle, autoLearnToggle { "Auto learn" };
    juce::TextButton holdButton { "Hold now" }, resetButton { "Reset" };

    std::unique_ptr<SliderAttachment> targetAttachment, trimAttachment,
                                      ceilingAttachment, learnAttachment;
    std::unique_ptr<ComboAttachment> modeAttachment;
    std::unique_ptr<ButtonAttachment> ceilingToggleAttachment, autoLearnAttachment;

    juce::Rectangle<int> headerArea, readoutArea, statusArea;

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR (GainStagerAudioProcessorEditor)
};
