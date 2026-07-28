#pragma once

#include <juce_audio_processors/juce_audio_processors.h>
#include <atomic>

// Host-independent counters: these increment regardless of whether our own
// getSpikeDocumentController() lookup logic works, so they tell us directly
// whether Logic ever calls into the ARA factory / role classes at all.
int getFactoryCreateCountForUI();
int getDocumentControllerCountForUI();
int getPlaybackRendererCountForUI();

//==============================================================================
// Does nothing but pass audio through. Its only job is to exist so the plugin
// instance validly fulfils the ARAPlaybackRenderer role.
class SpikePlaybackRenderer final : public juce::ARAPlaybackRenderer
{
public:
    explicit SpikePlaybackRenderer (ARA::PlugIn::DocumentController* dc)
        : juce::ARAPlaybackRenderer (dc)
    {
        ++playbackRendererConstructCount();
    }

    static std::atomic<int>& playbackRendererConstructCount()
    {
        static std::atomic<int> count { 0 };
        return count;
    }

    bool processBlock (juce::AudioBuffer<float>&,
                        juce::AudioProcessor::Realtime,
                        const juce::AudioPlayHead::PositionInfo&) noexcept override
    {
        // Passthrough: leave whatever's already in the buffer (silence in this host-agnostic spike).
        return true;
    }
};

//==============================================================================
// Minimal ARA document controller. Tracks how many audio sources this document
// currently has and logs role/lifecycle events so we can see them in Console.app
// (or stdout, for the Standalone build) while poking at the plugin in Logic.
class SpikeDocumentController final : public juce::ARADocumentControllerSpecialisation
{
public:
    using juce::ARADocumentControllerSpecialisation::ARADocumentControllerSpecialisation;

    SpikeDocumentController (const ARA::PlugIn::PlugInEntry* entry,
                              const ARA::ARADocumentControllerHostInstance* instance)
        : juce::ARADocumentControllerSpecialisation (entry, instance)
    {
        ++documentControllerConstructCount();
    }

    static std::atomic<int>& documentControllerConstructCount()
    {
        static std::atomic<int> count { 0 };
        return count;
    }

    std::atomic<int> audioSourceCount { 0 };
    std::atomic<int> eventCounter { 0 }; // bumped on every document event, for UI polling

    // Persistence round-trip check: incremented once per save, so we can see in
    // the UI that state survived a Logic project save/reopen cycle.
    std::atomic<int> archiveVersion { 0 };

protected:
    juce::ARAPlaybackRenderer* doCreatePlaybackRenderer() override
    {
        return new SpikePlaybackRenderer (getDocumentController());
    }

    void didAddAudioSourceToDocument (juce::ARADocument*, juce::ARAAudioSource* audioSource) override
    {
        ++audioSourceCount;
        ++eventCounter;
        const char* name = audioSource->getName();
        juce::ignoreUnused (name);
        DBG ("SpikeDocumentController: audio source added, name=\""
             << (name != nullptr ? name : "(unnamed)") << "\", total=" << audioSourceCount.load());
    }

    void willRemoveAudioSourceFromDocument (juce::ARADocument*, juce::ARAAudioSource*) override
    {
        --audioSourceCount;
        ++eventCounter;
        DBG ("SpikeDocumentController: audio source removed, total=" << audioSourceCount.load());
    }

    void didAddPlaybackRegionToRegionSequence (juce::ARARegionSequence* regionSequence,
                                               juce::ARAPlaybackRegion* playbackRegion) override
    {
        ++eventCounter;
        const char* seqName = regionSequence->getName();
        juce::ignoreUnused (seqName);
        DBG ("SpikeDocumentController: playback region added to region sequence "
             << (seqName != nullptr ? seqName : "(unnamed)"));
        juce::ignoreUnused (playbackRegion);
    }

    // Trivial archive: a single int32 version counter, bumped every time we're
    // asked to store. If this comes back incremented after reopening the Logic
    // project, ARA state persistence works.
    bool doStoreObjectsToStream (juce::ARAOutputStream& output, const juce::ARAStoreObjectsFilter*) override
    {
        ++archiveVersion;
        output.writeInt (archiveVersion.load());
        return true;
    }

    bool doRestoreObjectsFromStream (juce::ARAInputStream& input, const juce::ARARestoreObjectsFilter*) override
    {
        if (input.getNumBytesRemaining() >= (juce::int64) sizeof (int))
            archiveVersion = input.readInt();
        ++eventCounter;
        return true;
    }
};

//==============================================================================
class SpikeAudioProcessor final : public juce::AudioProcessor,
                                  public juce::AudioProcessorARAExtension
{
public:
    SpikeAudioProcessor();
    ~SpikeAudioProcessor() override = default;

    void prepareToPlay (double sampleRate, int samplesPerBlock) override;
    void releaseResources() override;
    bool isBusesLayoutSupported (const BusesLayout& layouts) const override;
    void processBlock (juce::AudioBuffer<float>&, juce::MidiBuffer&) override;
    using AudioProcessor::processBlock;

    juce::AudioProcessorEditor* createEditor() override;
    bool hasEditor() const override { return true; }

    const juce::String getName() const override { return "ARA Spike"; }
    bool acceptsMidi() const override { return false; }
    bool producesMidi() const override { return false; }
    double getTailLengthSeconds() const override { return 0.0; }

    int getNumPrograms() override { return 1; }
    int getCurrentProgram() override { return 0; }
    void setCurrentProgram (int) override {}
    const juce::String getProgramName (int) override { return "Default"; }
    void changeProgramName (int, const juce::String&) override {}

    void getStateInformation (juce::MemoryBlock&) override {}
    void setStateInformation (const void*, int) override {}

    // Convenience accessor for the editor: -1 if this instance isn't bound to ARA.
    int getAudioSourceCountForUI() const;
    int getEventCounterForUI() const;
    int getArchiveVersionForUI() const;

private:
    static BusesProperties getBusesProperties()
    {
        return BusesProperties().withInput ("Input", juce::AudioChannelSet::stereo(), true)
                                 .withOutput ("Output", juce::AudioChannelSet::stereo(), true);
    }

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR (SpikeAudioProcessor)
};
