#include "PluginEditor.h"

namespace
{
    juce::String stateName (GainStagerAudioProcessor::State s)
    {
        switch (s)
        {
            case GainStagerAudioProcessor::State::Learn: return "LEARN";
            case GainStagerAudioProcessor::State::Hold:  return "HOLD";
            case GainStagerAudioProcessor::State::Idle:
            default:                                     return "IDLE";
        }
    }
}

GainStagerAudioProcessorEditor::GainStagerAudioProcessorEditor (GainStagerAudioProcessor& p)
    : juce::AudioProcessorEditor (&p), processorRef (p)
{
    statusLabel.setJustificationType (juce::Justification::topLeft);
    statusLabel.setFont (juce::FontOptions (juce::Font::getDefaultMonospacedFontName(), 13.0f, juce::Font::plain));
    addAndMakeVisible (statusLabel);

    targetSlider.setSliderStyle (juce::Slider::LinearHorizontal);
    targetSlider.setTextBoxStyle (juce::Slider::TextBoxRight, false, 70, 20);
    targetSlider.setTextValueSuffix (" LUFS");
    addAndMakeVisible (targetLabel);
    addAndMakeVisible (targetSlider);
    targetAttachment = std::make_unique<SliderAttachment> (processorRef.apvts, "target", targetSlider);

    trimSlider.setSliderStyle (juce::Slider::LinearHorizontal);
    trimSlider.setTextBoxStyle (juce::Slider::TextBoxRight, false, 70, 20);
    trimSlider.setTextValueSuffix (" dB");
    addAndMakeVisible (trimLabel);
    addAndMakeVisible (trimSlider);
    trimAttachment = std::make_unique<SliderAttachment> (processorRef.apvts, "trim", trimSlider);

    if (auto* param = processorRef.apvts.getParameter ("mode"))
    {
        modeBox.addItemList (param->getAllValueStrings(), 1);
        addAndMakeVisible (modeLabel);
        addAndMakeVisible (modeBox);
        modeAttachment = std::make_unique<ComboAttachment> (processorRef.apvts, "mode", modeBox);
    }

    addAndMakeVisible (autoLearnButton);
    autoLearnAttachment = std::make_unique<ButtonAttachment> (processorRef.apvts, "autoLearn", autoLearnButton);

    holdButton.onClick = [this] { processorRef.commitNow(); };
    resetButton.onClick = [this] { processorRef.requestReset(); };
    addAndMakeVisible (holdButton);
    addAndMakeVisible (resetButton);

    setSize (460, 340);
    startTimerHz (10);
}

GainStagerAudioProcessorEditor::~GainStagerAudioProcessorEditor()
{
    stopTimer();
}

void GainStagerAudioProcessorEditor::paint (juce::Graphics& g)
{
    g.fillAll (juce::Colour (0xff1b1b1f));
}

void GainStagerAudioProcessorEditor::resized()
{
    auto area = getLocalBounds().reduced (16);

    statusLabel.setBounds (area.removeFromTop (128));
    area.removeFromTop (8);

    auto row = [&area] (int height)
    {
        auto r = area.removeFromTop (height);
        area.removeFromTop (6);
        return r;
    };

    {
        auto r = row (24);
        targetLabel.setBounds (r.removeFromLeft (60));
        targetSlider.setBounds (r);
    }
    {
        auto r = row (24);
        trimLabel.setBounds (r.removeFromLeft (60));
        trimSlider.setBounds (r);
    }
    {
        auto r = row (24);
        modeLabel.setBounds (r.removeFromLeft (60));
        modeBox.setBounds (r);
    }

    auto buttons = row (28);
    autoLearnButton.setBounds (buttons.removeFromLeft (110));
    buttons.removeFromLeft (8);
    holdButton.setBounds (buttons.removeFromLeft (100));
    buttons.removeFromLeft (8);
    resetButton.setBounds (buttons.removeFromLeft (80));
}

juce::String GainStagerAudioProcessorEditor::describe (double value, const juce::String& unit) const
{
    if (value <= -150.0)
        return "--";

    return juce::String (value, 2) + " " + unit;
}

void GainStagerAudioProcessorEditor::timerCallback()
{
    heldPeak = juce::jmax (processorRef.getPeakSinceLastRead(), heldPeak * 0.85f);

    const auto peakDb = heldPeak > 0.0f ? juce::Decibels::gainToDecibels (heldPeak) : -100.0f;
    const auto unit = processorRef.getMeasurementUnit();

    juce::String text;
    text << "GAIN STAGER\n\n"
         << "state       : " << stateName (processorRef.getState()) << "\n"
         << "measured    : " << describe (processorRef.getMeasured(), unit) << "\n"
         << "learned from: " << juce::String (processorRef.getGatedSeconds(), 1) << " s of audio\n"
         << "true peak   : " << describe (processorRef.getTruePeakDb(), "dBTP") << "\n"
         << "input peak  : " << (peakDb <= -100.0f ? juce::String ("--")
                                                   : juce::String (peakDb, 1) + " dBFS") << "\n"
         << "rate        : " << juce::String (processorRef.getPreparedSampleRate(), 0) << " Hz, "
                             << processorRef.getActiveChannels() << " ch, "
                             << processorRef.getLatencySamples() << " smp latency";

    // Phase 4: the plugin sat in LEARN doing nothing because it was 0.3 s short
    // of the commit threshold, and said nothing about it. Never leave the user
    // guessing why it has not committed.
    const auto state = processorRef.getState();

    if (state != GainStagerAudioProcessor::State::Hold)
    {
        const auto gated = processorRef.getGatedSeconds();
        const auto minimum = GainStagerAudioProcessor::minimumGatedSeconds;

        text << "\n\n";

        if (processorRef.isResetPending())
            text << "reset — waiting for audio to arrive";
        else if (gated < minimum)
            text << "needs " << juce::String (minimum - gated, 1)
                 << " s more audio before it can commit";
        else
            text << "ready — commits when the transport stops, or at "
                 << juce::String (processorRef.getLearnSeconds(), 0) << " s";
    }

    if (processorRef.isCeilingLimited())
        text << "\n\n*** trim reduced to respect the ceiling ***";

    statusLabel.setText (text, juce::dontSendNotification);
}
