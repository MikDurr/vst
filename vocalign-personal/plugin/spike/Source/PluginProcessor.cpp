#include "PluginProcessor.h"
#include "PluginEditor.h"

SpikeAudioProcessor::SpikeAudioProcessor()
    : juce::AudioProcessor (getBusesProperties())
{
}

void SpikeAudioProcessor::prepareToPlay (double sampleRate, int samplesPerBlock)
{
    prepareToPlayForARA (sampleRate, samplesPerBlock, getMainBusNumOutputChannels(), getProcessingPrecision());
}

void SpikeAudioProcessor::releaseResources()
{
    releaseResourcesForARA();
}

bool SpikeAudioProcessor::isBusesLayoutSupported (const BusesLayout& layouts) const
{
    return layouts.getMainOutputChannelSet() == juce::AudioChannelSet::mono()
        || layouts.getMainOutputChannelSet() == juce::AudioChannelSet::stereo();
}

void SpikeAudioProcessor::processBlock (juce::AudioBuffer<float>& buffer, juce::MidiBuffer& midi)
{
    juce::ignoreUnused (midi);
    juce::ScopedNoDenormals noDenormals;

    auto* playHead = getPlayHead();
    const auto positionInfo = playHead != nullptr ? playHead->getPosition() : std::nullopt;

    if (! processBlockForARA (buffer, isRealtime(), playHead))
        processBlockBypassed (buffer, midi);

    juce::ignoreUnused (positionInfo);
}

juce::AudioProcessorEditor* SpikeAudioProcessor::createEditor()
{
    return new SpikeAudioProcessorEditor (*this);
}

namespace
{
    SpikeDocumentController* getSpikeDocumentController (const SpikeAudioProcessor& processor)
    {
        if (! processor.isBoundToARA())
            return nullptr;

        auto* renderer = processor.getPlaybackRenderer<SpikePlaybackRenderer>();
        if (renderer == nullptr)
            return nullptr;

        auto* rawDocumentController = renderer->getDocumentController();
        return juce::ARADocumentControllerSpecialisation::getSpecialisedDocumentController<SpikeDocumentController> (rawDocumentController);
    }
}

int SpikeAudioProcessor::getAudioSourceCountForUI() const
{
    if (auto* dc = getSpikeDocumentController (*this))
        return dc->audioSourceCount.load();

    return -1;
}

int SpikeAudioProcessor::getEventCounterForUI() const
{
    if (auto* dc = getSpikeDocumentController (*this))
        return dc->eventCounter.load();

    return -1;
}

int SpikeAudioProcessor::getArchiveVersionForUI() const
{
    if (auto* dc = getSpikeDocumentController (*this))
        return dc->archiveVersion.load();

    return -1;
}

namespace
{
    std::atomic<int>& factoryCreateCount()
    {
        static std::atomic<int> count { 0 };
        return count;
    }
}

int getFactoryCreateCountForUI()
{
    return factoryCreateCount().load();
}

int getDocumentControllerCountForUI()
{
    return SpikeDocumentController::documentControllerConstructCount().load();
}

int getPlaybackRendererCountForUI()
{
    return SpikePlaybackRenderer::playbackRendererConstructCount().load();
}

//==============================================================================
juce::AudioProcessor* JUCE_CALLTYPE createPluginFilter()
{
    return new SpikeAudioProcessor();
}

const ARA::ARAFactory* JUCE_CALLTYPE createARAFactory()
{
    ++factoryCreateCount();
    return juce::ARADocumentControllerSpecialisation::createARAFactory<SpikeDocumentController>();
}
