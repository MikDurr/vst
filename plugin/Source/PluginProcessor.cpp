#include "PluginProcessor.h"
#include "PluginEditor.h"

namespace
{
    constexpr double maxTrimDb = 24.0;

    constexpr int modeIntegrated = 0;
    constexpr int modeShortTermMax = 1;
    constexpr int modeRms = 2;
    constexpr int modePeak = 3;
}

//==============================================================================
juce::AudioProcessorValueTreeState::ParameterLayout
GainStagerAudioProcessor::createParameterLayout()
{
    using namespace juce;

    AudioProcessorValueTreeState::ParameterLayout layout;

    layout.add (std::make_unique<AudioParameterFloat> (
        ParameterID { "target", 1 }, "Target",
        NormalisableRange<float> (-36.0f, -6.0f, 0.1f), -18.0f));

    layout.add (std::make_unique<AudioParameterChoice> (
        ParameterID { "mode", 1 }, "Mode",
        StringArray { "Integrated (LUFS-I)", "Short-term max", "RMS", "True peak" }, 0));

    // The output of the measurement, but user-editable so a reading can be
    // nudged by hand without re-learning.
    layout.add (std::make_unique<AudioParameterFloat> (
        ParameterID { "trim", 1 }, "Trim",
        NormalisableRange<float> (-24.0f, 24.0f, 0.01f), 0.0f));

    layout.add (std::make_unique<AudioParameterBool> (
        ParameterID { "hold", 1 }, "Hold", false));

    layout.add (std::make_unique<AudioParameterBool> (
        ParameterID { "autoLearn", 1 }, "Auto learn", true));

    layout.add (std::make_unique<AudioParameterFloat> (
        ParameterID { "learnSeconds", 1 }, "Learn time",
        NormalisableRange<float> (5.0f, 120.0f, 1.0f), 20.0f));

    layout.add (std::make_unique<AudioParameterFloat> (
        ParameterID { "ceiling", 1 }, "Ceiling",
        NormalisableRange<float> (-12.0f, 0.0f, 0.1f), -6.0f));

    layout.add (std::make_unique<AudioParameterBool> (
        ParameterID { "ceilingEnabled", 1 }, "Ceiling on", true));

    layout.add (std::make_unique<AudioParameterBool> (
        ParameterID { "bypass", 1 }, "Bypass", false));

    return layout;
}

juce::AudioProcessor::BusesProperties GainStagerAudioProcessor::getBusesProperties()
{
    return BusesProperties()
        .withInput  ("Input",  juce::AudioChannelSet::stereo(), true)
        .withOutput ("Output", juce::AudioChannelSet::stereo(), true);
}

//==============================================================================
GainStagerAudioProcessor::GainStagerAudioProcessor()
    : juce::AudioProcessor (getBusesProperties()),
      apvts (*this, nullptr, "PARAMETERS", createParameterLayout())
{
    targetParam         = dynamic_cast<juce::AudioParameterFloat*>  (apvts.getParameter ("target"));
    modeParam           = dynamic_cast<juce::AudioParameterChoice*> (apvts.getParameter ("mode"));
    trimParam           = dynamic_cast<juce::AudioParameterFloat*>  (apvts.getParameter ("trim"));
    holdParam           = dynamic_cast<juce::AudioParameterBool*>   (apvts.getParameter ("hold"));
    autoLearnParam      = dynamic_cast<juce::AudioParameterBool*>   (apvts.getParameter ("autoLearn"));
    learnSecondsParam   = dynamic_cast<juce::AudioParameterFloat*>  (apvts.getParameter ("learnSeconds"));
    ceilingParam        = dynamic_cast<juce::AudioParameterFloat*>  (apvts.getParameter ("ceiling"));
    ceilingEnabledParam = dynamic_cast<juce::AudioParameterBool*>   (apvts.getParameter ("ceilingEnabled"));
    bypassParam         = dynamic_cast<juce::AudioParameterBool*>   (apvts.getParameter ("bypass"));

    jassert (targetParam && modeParam && trimParam && holdParam && autoLearnParam
             && learnSecondsParam && ceilingParam && ceilingEnabledParam && bypassParam);

    // A trim is a gain. No lookahead here, ever — the true-peak meter is a
    // measurement side-chain and contributes nothing to the audio path.
    setLatencySamples (0);

    startTimerHz (10);
}

GainStagerAudioProcessor::~GainStagerAudioProcessor()
{
    stopTimer();
}

//==============================================================================
void GainStagerAudioProcessor::prepareToPlay (double sampleRate, int samplesPerBlock)
{
    preparedSampleRate.store (sampleRate);
    preparedBlockSize.store (samplesPerBlock);
    activeChannels.store (getMainBusNumInputChannels());

    const auto channels = juce::jmax (1, getMainBusNumInputChannels());

    meter.prepare (sampleRate, channels);
    truePeak.prepare (sampleRate, channels);

    gainSmoother.reset (sampleRate, 0.05);
    gainSmoother.setCurrentAndTargetValue (holdParam->get()
                                               ? juce::Decibels::decibelsToGain (trimParam->get())
                                               : 1.0f);
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

    const auto numIn = getTotalNumInputChannels();
    const auto numOut = getTotalNumOutputChannels();
    const auto numSamples = buffer.getNumSamples();

    for (int ch = numIn; ch < numOut; ++ch)
        buffer.clear (ch, 0, numSamples);

    // Freshness stamp for the message thread's transport-idle inference.
    lastBlockMs.store (juce::Time::getMillisecondCounter());

    // Resets happen here rather than on the message thread: clearing the
    // meter's buffers while process() is reading them would be a race. It is a
    // one-off memset, trivial next to a block's deadline.
    if (resetPending.exchange (false))
    {
        meter.reset();
        truePeak.reset();
    }

    const auto activeCh = juce::jmin (numIn, numOut);
    const bool bypassed = bypassParam->get();
    const bool held = holdParam->get();

    float blockPeak = 0.0f;

    for (int ch = 0; ch < activeCh; ++ch)
        blockPeak = juce::jmax (blockPeak, buffer.getMagnitude (ch, 0, numSamples));

    auto previous = peakSinceLastRead.load();
    while (blockPeak > previous
           && ! peakSinceLastRead.compare_exchange_weak (previous, blockPeak))
    {
    }

    // Measure the input, before the trim: what we are staging is the raw track.
    // Once held there is nothing left to learn, so accumulation stops.
    if (! bypassed && ! held && activeCh > 0)
    {
        const float* pointers[8] {};
        const auto n = juce::jmin (activeCh, 8);

        for (int ch = 0; ch < n; ++ch)
            pointers[ch] = buffer.getReadPointer (ch);

        meter.process (pointers, numSamples);
        truePeak.process (pointers, numSamples);
    }

    const float target = (! bypassed && held)
                             ? juce::Decibels::decibelsToGain (trimParam->get())
                             : 1.0f;

    gainSmoother.setTargetValue (target);
    gainSmoother.applyGain (buffer, numSamples);
}

//==============================================================================
double GainStagerAudioProcessor::measureCurrent() const
{
    switch (modeParam->getIndex())
    {
        case modeShortTermMax: return meter.shortTermMaxLufs();
        case modeRms:          return meter.rmsDb();
        case modePeak:         return truePeak.truePeakDb();
        case modeIntegrated:
        default:               return meter.integratedLufs();
    }
}

juce::String GainStagerAudioProcessor::getMeasurementUnit() const
{
    switch (modeParam->getIndex())
    {
        case modeRms:  return "dBFS";
        case modePeak: return "dBTP";
        default:       return "LUFS";
    }
}

GainStagerAudioProcessor::State GainStagerAudioProcessor::getState() const noexcept
{
    if (holdParam->get())
        return State::Hold;

    return cachedGatedSeconds.load() > 0.0 ? State::Learn : State::Idle;
}

void GainStagerAudioProcessor::requestReset()
{
    resetPending.store (true);

    // Clear the readouts immediately so the UI reflects the reset even though
    // the meters themselves are not cleared until the next callback — which,
    // on a silent track, may not come until playback resumes.
    cachedMeasured.store (gs::LoudnessMeter::silence);
    cachedGatedSeconds.store (0.0);
    cachedTruePeakDb.store (gs::TruePeakMeter::floorDb);
    ceilingLimited.store (false);

    setParameter (holdParam, 0.0f);
    wasHeld = false;
}

void GainStagerAudioProcessor::commitNow()
{
    commit();
}

void GainStagerAudioProcessor::commit()
{
    const double measured = measureCurrent();

    if (! gs::isValidMeasurement (measured))
        return;

    // The arithmetic lives in core/ so the test suite can reach it — a sign
    // error here would be silent and would wreck a mix.
    const auto result = gs::computeTrim (measured,
                                         (double) targetParam->get(),
                                         truePeak.truePeakDb(),
                                         (double) ceilingParam->get(),
                                         ceilingEnabledParam->get(),
                                         maxTrimDb);

    ceilingLimited.store (result.ceilingLimited);
    cachedMeasured.store (measured);

    setParameter (trimParam, (float) result.trimDb);
    setParameter (holdParam, 1.0f);
    wasHeld = true;
}

void GainStagerAudioProcessor::setParameter (juce::RangedAudioParameter* param, float value)
{
    param->setValueNotifyingHost (param->convertTo0to1 (value));
}

//==============================================================================
void GainStagerAudioProcessor::timerCallback()
{
    const bool held = holdParam->get();

    // Manually leaving Hold means "learn it again".
    if (wasHeld && ! held)
        requestReset();

    wasHeld = held;

    if (! held)
    {
        cachedMeasured.store (measureCurrent());
        cachedGatedSeconds.store (meter.gatedSeconds());
        cachedTruePeakDb.store (truePeak.truePeakDb());
    }

    if (held || ! autoLearnParam->get())
        return;

    const double gated = cachedGatedSeconds.load();

    if (gated >= (double) learnSecondsParam->get())
    {
        commit();
        return;
    }

    // Transport idle. Per the Phase 0 finding this cannot distinguish a stopped
    // transport from a silent passage mid-song, so it only commits once there
    // is a defensible amount of audio behind the reading.
    const auto age = juce::Time::getMillisecondCounter() - lastBlockMs.load();

    if (lastBlockMs.load() != 0 && age > (juce::uint32) transportIdleMs
        && gated >= minimumGatedSeconds)
    {
        commit();
    }
}

//==============================================================================
void GainStagerAudioProcessor::getStateInformation (juce::MemoryBlock& destData)
{
    auto state = apvts.copyState();
    state.setProperty ("measured", cachedMeasured.load(), nullptr);
    state.setProperty ("ceilingLimited", ceilingLimited.load(), nullptr);

    if (auto xml = std::unique_ptr<juce::XmlElement> (state.createXml()))
        copyXmlToBinary (*xml, destData);
}

void GainStagerAudioProcessor::setStateInformation (const void* data, int sizeInBytes)
{
    auto xml = getXmlFromBinary (data, sizeInBytes);

    if (xml == nullptr || ! xml->hasTagName (apvts.state.getType()))
        return;

    const auto tree = juce::ValueTree::fromXml (*xml);
    apvts.replaceState (tree);

    cachedMeasured.store ((double) tree.getProperty ("measured", gs::LoudnessMeter::silence));
    ceilingLimited.store ((bool) tree.getProperty ("ceilingLimited", false));

    // Reopening a project must never change the mix. If a trim was committed,
    // come back in Hold with that exact trim and do not re-arm. Syncing wasHeld
    // is what stops the timer seeing a phantom Hold->Learn transition and
    // wiping the trim on load. PLAN.md §3.
    wasHeld = holdParam->get();

    if (wasHeld)
        cachedGatedSeconds.store (0.0);
}

//==============================================================================
juce::AudioProcessorEditor* GainStagerAudioProcessor::createEditor()
{
    return new GainStagerAudioProcessorEditor (*this);
}

juce::AudioProcessor* JUCE_CALLTYPE createPluginFilter()
{
    return new GainStagerAudioProcessor();
}
