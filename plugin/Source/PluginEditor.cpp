#include "PluginEditor.h"

GainStagerAudioProcessorEditor::GainStagerAudioProcessorEditor (GainStagerAudioProcessor& p)
    : juce::AudioProcessorEditor (&p), processorRef (p)
{
    statusLabel.setJustificationType (juce::Justification::topLeft);
    statusLabel.setFont (juce::FontOptions (juce::Font::getDefaultMonospacedFontName(), 13.0f, juce::Font::plain));
    addAndMakeVisible (statusLabel);

    setSize (420, 180);
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
    statusLabel.setBounds (getLocalBounds().reduced (16));
}

void GainStagerAudioProcessorEditor::timerCallback()
{
    // Decay the held peak so the readout tracks playback rather than latching
    // on the loudest thing that ever happened.
    heldPeak = juce::jmax (processorRef.getPeakSinceLastRead(), heldPeak * 0.85f);

    const auto peakDb = heldPeak > 0.0f ? juce::Decibels::gainToDecibels (heldPeak) : -100.0f;

    juce::String text;
    text << "GAIN STAGER — phase 0 (passthrough)\n\n"
         << "sample rate : " << juce::String (processorRef.getPreparedSampleRate(), 1) << " Hz\n"
         << "block size  : " << processorRef.getPreparedBlockSize() << "\n"
         << "channels    : " << processorRef.getActiveChannels() << "\n"
         << "latency     : " << processorRef.getLatencySamples() << " samples\n"
         << "blocks seen : " << processorRef.getBlockCount() << "\n"
         << "input peak  : " << (peakDb <= -100.0f ? juce::String ("--")
                                                   : juce::String (peakDb, 1) + " dBFS");

    statusLabel.setText (text, juce::dontSendNotification);
}
