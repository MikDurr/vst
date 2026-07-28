#include "PluginEditor.h"

SpikeAudioProcessorEditor::SpikeAudioProcessorEditor (SpikeAudioProcessor& p)
    : juce::AudioProcessorEditor (&p), spikeProcessor (p)
{
    statusLabel.setJustificationType (juce::Justification::topLeft);
    statusLabel.setFont (juce::FontOptions (15.0f));
    statusLabel.setColour (juce::Label::textColourId, juce::Colours::white);
    addAndMakeVisible (statusLabel);

    setSize (460, 230);
    refreshLabel();
    startTimerHz (5);
}

SpikeAudioProcessorEditor::~SpikeAudioProcessorEditor()
{
    stopTimer();
}

void SpikeAudioProcessorEditor::paint (juce::Graphics& g)
{
    g.fillAll (juce::Colour (0xff202030));
}

void SpikeAudioProcessorEditor::resized()
{
    statusLabel.setBounds (getLocalBounds().reduced (12));
}

void SpikeAudioProcessorEditor::timerCallback()
{
    refreshLabel();
}

void SpikeAudioProcessorEditor::refreshLabel()
{
    const bool bound = spikeProcessor.isBoundToARA();
    const int sources = spikeProcessor.getAudioSourceCountForUI();
    const int events = spikeProcessor.getEventCounterForUI();
    const int archive = spikeProcessor.getArchiveVersionForUI();

    juce::String text;
    text << "ARA Spike\n\n";
    text << "Bound to ARA: " << (bound ? "YES" : "no (plain AU insert)") << "\n";
    text << "Is playback renderer: " << (spikeProcessor.isPlaybackRenderer() ? "yes" : "no") << "\n";
    text << "Audio sources visible in document: " << sources << "\n";
    text << "Document event counter: " << events << "\n";
    text << "Archive version (bumps on save): " << archive << "\n\n";
    text << "[process-wide] createARAFactory() calls: " << getFactoryCreateCountForUI() << "\n";
    text << "[process-wide] DocumentControllers constructed: " << getDocumentControllerCountForUI() << "\n";
    text << "[process-wide] PlaybackRenderers constructed: " << getPlaybackRendererCountForUI();

    statusLabel.setText (text, juce::dontSendNotification);
}
