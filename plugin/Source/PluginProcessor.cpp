#include "PluginProcessor.h"
#include "PluginEditor.h"

juce::AudioProcessor::BusesProperties GainStagerAudioProcessor::getBusesProperties()
{
    return BusesProperties()
        .withInput  ("Input",  juce::AudioChannelSet::stereo(), true)
        .withOutput ("Output", juce::AudioChannelSet::stereo(), true);
}

GainStagerAudioProcessor::GainStagerAudioProcessor()
    : juce::AudioProcessor (getBusesProperties())
{
    // A trim is a gain. There is no lookahead here and there never will be —
    // the true-peak measurement in Phase 1 lives in a side chain. PLAN.md §2.
    setLatencySamples (0);
}

void GainStagerAudioProcessor::prepareToPlay (double sampleRate, int samplesPerBlock)
{
    preparedSampleRate.store (sampleRate);
    preparedBlockSize.store (samplesPerBlock);
    activeChannels.store (getMainBusNumInputChannels());
    blockCount.store (0);
}

void GainStagerAudioProcessor::releaseResources()
{
}

bool GainStagerAudioProcessor::isBusesLayoutSupported (const BusesLayout& layouts) const
{
    const auto& out = layouts.getMainOutputChannelSet();

    if (out != juce::AudioChannelSet::mono() && out != juce::AudioChannelSet::stereo())
        return false;

    return layouts.getMainInputChannelSet() == out;
}

void GainStagerAudioProcessor::processBlock (juce::AudioBuffer<float>& buffer, juce::MidiBuffer& midi)
{
    juce::ignoreUnused (midi);
    juce::ScopedNoDenormals noDenormals;

    const auto numIn  = getTotalNumInputChannels();
    const auto numOut = getTotalNumOutputChannels();

    for (int ch = numIn; ch < numOut; ++ch)
        buffer.clear (ch, 0, buffer.getNumSamples());

    // Passthrough. The only thing measured in Phase 0 is a plain peak, purely so
    // the editor can show that audio is genuinely reaching us in Logic.
    auto blockPeak = 0.0f;

    for (int ch = 0; ch < juce::jmin (numIn, numOut); ++ch)
        blockPeak = juce::jmax (blockPeak, buffer.getMagnitude (ch, 0, buffer.getNumSamples()));

    auto previous = peakSinceLastRead.load();
    while (blockPeak > previous
           && ! peakSinceLastRead.compare_exchange_weak (previous, blockPeak))
    {
    }

    blockCount.fetch_add (1);
}

juce::AudioProcessorEditor* GainStagerAudioProcessor::createEditor()
{
    return new GainStagerAudioProcessorEditor (*this);
}

void GainStagerAudioProcessor::getStateInformation (juce::MemoryBlock& destData)
{
    // No parameters yet. Phase 2 stores trim/measured/state here, and the
    // persistence rule in PLAN.md §3 applies: reopening must not re-learn.
    juce::ignoreUnused (destData);
}

void GainStagerAudioProcessor::setStateInformation (const void* data, int sizeInBytes)
{
    juce::ignoreUnused (data, sizeInBytes);
}

//==============================================================================
juce::AudioProcessor* JUCE_CALLTYPE createPluginFilter()
{
    return new GainStagerAudioProcessor();
}
