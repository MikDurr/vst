#include "PluginEditor.h"

namespace
{
    juce::Font sans (float height, int style = juce::Font::plain)
    {
        return juce::Font (juce::FontOptions (juce::Font::getDefaultSansSerifFontName(), height, style));
    }

    /** Monospaced for anything that changes every frame — proportional digits
        jitter the layout as the value moves, which reads as instability. */
    juce::Font mono (float height, int style = juce::Font::plain)
    {
        return juce::Font (juce::FontOptions (juce::Font::getDefaultMonospacedFontName(), height, style));
    }

    void fillPanel (juce::Graphics& g, juce::Rectangle<int> area)
    {
        g.setColour (theme::panel);
        g.fillRoundedRectangle (area.toFloat(), 6.0f);
        g.setColour (theme::panelEdge);
        g.drawRoundedRectangle (area.toFloat().reduced (0.5f), 6.0f, 1.0f);
    }

    juce::String signedDb (double value)
    {
        // Without the snap, a parameter sitting a hair below zero renders as
        // "-0.00", which reads as a glitch rather than as no change.
        if (std::abs (value) < 0.005)
            value = 0.0;

        return (value > 0.0 ? "+" : "") + juce::String (value, 2);
    }
}

//==============================================================================
GainStagerLookAndFeel::GainStagerLookAndFeel()
{
    setColour (juce::Slider::textBoxTextColourId, theme::textBright);
    setColour (juce::Slider::textBoxOutlineColourId, juce::Colours::transparentBlack);
    setColour (juce::Slider::textBoxBackgroundColourId, juce::Colours::transparentBlack);
    setColour (juce::Slider::textBoxHighlightColourId, theme::learn.withAlpha (0.4f));

    setColour (juce::ComboBox::textColourId, theme::textBright);
    setColour (juce::ComboBox::backgroundColourId, theme::panel);
    setColour (juce::ComboBox::outlineColourId, theme::panelEdge);
    setColour (juce::ComboBox::arrowColourId, theme::textDim);

    setColour (juce::PopupMenu::backgroundColourId, theme::panel);
    setColour (juce::PopupMenu::textColourId, theme::textBright);
    setColour (juce::PopupMenu::highlightedBackgroundColourId, theme::learn.withAlpha (0.25f));
    setColour (juce::PopupMenu::highlightedTextColourId, theme::textBright);

    setColour (juce::TextButton::buttonColourId, theme::panel);
    setColour (juce::TextButton::textColourOffId, theme::textBright);
    setColour (juce::ToggleButton::textColourId, theme::textDim);
    setColour (juce::Label::textColourId, theme::textDim);
}

void GainStagerLookAndFeel::drawLinearSlider (juce::Graphics& g, int x, int y, int width, int height,
                                              float sliderPos, float, float,
                                              juce::Slider::SliderStyle, juce::Slider& slider)
{
    const auto centreY = (float) y + (float) height * 0.5f;
    const juce::Rectangle<float> track ((float) x, centreY - 2.0f, (float) width, 4.0f);

    g.setColour (theme::panelEdge);
    g.fillRoundedRectangle (track, 2.0f);

    const auto accent = slider.findColour (juce::Slider::thumbColourId);
    const auto filled = track.withRight (juce::jlimit (track.getX(), track.getRight(), sliderPos));

    g.setColour (accent.withAlpha (0.75f));
    g.fillRoundedRectangle (filled, 2.0f);

    g.setColour (accent);
    g.fillEllipse (sliderPos - 6.0f, centreY - 6.0f, 12.0f, 12.0f);
    g.setColour (theme::background);
    g.fillEllipse (sliderPos - 2.5f, centreY - 2.5f, 5.0f, 5.0f);
}

void GainStagerLookAndFeel::drawComboBox (juce::Graphics& g, int width, int height, bool,
                                          int, int, int, int, juce::ComboBox& box)
{
    const juce::Rectangle<float> bounds (0.0f, 0.0f, (float) width, (float) height);

    g.setColour (theme::background);
    g.fillRoundedRectangle (bounds, 4.0f);
    g.setColour (box.hasKeyboardFocus (true) ? theme::learn.withAlpha (0.6f) : theme::panelEdge);
    g.drawRoundedRectangle (bounds.reduced (0.5f), 4.0f, 1.0f);

    juce::Path arrow;
    const auto cx = (float) width - 14.0f;
    const auto cy = (float) height * 0.5f;
    arrow.startNewSubPath (cx - 4.0f, cy - 2.0f);
    arrow.lineTo (cx, cy + 3.0f);
    arrow.lineTo (cx + 4.0f, cy - 2.0f);

    g.setColour (theme::textDim);
    g.strokePath (arrow, juce::PathStrokeType (1.6f, juce::PathStrokeType::curved,
                                               juce::PathStrokeType::rounded));
}

void GainStagerLookAndFeel::drawButtonBackground (juce::Graphics& g, juce::Button& button,
                                                  const juce::Colour&,
                                                  bool shouldDrawButtonAsHighlighted,
                                                  bool shouldDrawButtonAsDown)
{
    auto base = theme::panel;

    if (shouldDrawButtonAsDown)
        base = theme::panel.brighter (0.28f);
    else if (shouldDrawButtonAsHighlighted)
        base = theme::panel.brighter (0.14f);

    const auto bounds = button.getLocalBounds().toFloat();

    g.setColour (base);
    g.fillRoundedRectangle (bounds, 5.0f);
    g.setColour (theme::panelEdge);
    g.drawRoundedRectangle (bounds.reduced (0.5f), 5.0f, 1.0f);
}

void GainStagerLookAndFeel::drawTickBox (juce::Graphics& g, juce::Component&,
                                         float x, float y, float w, float h,
                                         bool ticked, bool, bool shouldDrawButtonAsHighlighted, bool)
{
    const juce::Rectangle<float> box (x, y + (h - 15.0f) * 0.5f, 15.0f, 15.0f);

    g.setColour (ticked ? theme::hold.withAlpha (0.22f) : theme::background);
    g.fillRoundedRectangle (box, 3.5f);
    g.setColour (ticked ? theme::hold
                        : (shouldDrawButtonAsHighlighted ? theme::textDim : theme::panelEdge));
    g.drawRoundedRectangle (box.reduced (0.5f), 3.5f, 1.0f);

    if (! ticked)
        return;

    juce::Path tick;
    tick.startNewSubPath (box.getX() + 3.6f, box.getCentreY());
    tick.lineTo (box.getCentreX() - 0.8f, box.getBottom() - 4.4f);
    tick.lineTo (box.getRight() - 3.4f, box.getY() + 4.4f);

    g.setColour (theme::hold);
    g.strokePath (tick, juce::PathStrokeType (2.0f, juce::PathStrokeType::curved,
                                              juce::PathStrokeType::rounded));
}

juce::Label* GainStagerLookAndFeel::createSliderTextBox (juce::Slider& slider)
{
    auto* label = LookAndFeel_V4::createSliderTextBox (slider);
    label->setFont (mono (12.0f));
    label->setJustificationType (juce::Justification::centredRight);
    return label;
}

//==============================================================================
GainStagerAudioProcessorEditor::GainStagerAudioProcessorEditor (GainStagerAudioProcessor& p)
    : juce::AudioProcessorEditor (&p), processorRef (p)
{
    setLookAndFeel (&lookAndFeel);

    auto setupSlider = [this] (juce::Slider& slider, const juce::String& suffix, juce::Colour accent)
    {
        slider.setSliderStyle (juce::Slider::LinearHorizontal);
        slider.setTextBoxStyle (juce::Slider::TextBoxRight, false, 84, 22);
        slider.setTextValueSuffix (suffix);
        slider.setColour (juce::Slider::thumbColourId, accent);
        addAndMakeVisible (slider);
    };

    setupSlider (targetSlider,  " LUFS", theme::learn);
    setupSlider (trimSlider,    " dB",   theme::hold);
    setupSlider (ceilingSlider, " dBTP", theme::learn);
    setupSlider (learnSlider,   " s",    theme::learn);

    targetAttachment  = std::make_unique<SliderAttachment> (processorRef.apvts, "target", targetSlider);
    trimAttachment    = std::make_unique<SliderAttachment> (processorRef.apvts, "trim", trimSlider);
    ceilingAttachment = std::make_unique<SliderAttachment> (processorRef.apvts, "ceiling", ceilingSlider);
    learnAttachment   = std::make_unique<SliderAttachment> (processorRef.apvts, "learnSeconds", learnSlider);

    if (auto* param = processorRef.apvts.getParameter ("mode"))
    {
        modeBox.addItemList (param->getAllValueStrings(), 1);
        addAndMakeVisible (modeBox);
        modeAttachment = std::make_unique<ComboAttachment> (processorRef.apvts, "mode", modeBox);
    }

    addAndMakeVisible (ceilingToggle);
    ceilingToggleAttachment = std::make_unique<ButtonAttachment> (processorRef.apvts, "ceilingEnabled", ceilingToggle);

    addAndMakeVisible (autoLearnToggle);
    autoLearnAttachment = std::make_unique<ButtonAttachment> (processorRef.apvts, "autoLearn", autoLearnToggle);

    holdButton.onClick  = [this] { processorRef.commitNow(); };
    resetButton.onClick = [this] { processorRef.requestReset(); };
    addAndMakeVisible (holdButton);
    addAndMakeVisible (resetButton);

    auto setupLabel = [this] (juce::Label& label, const juce::String& text)
    {
        label.setText (text, juce::dontSendNotification);
        label.setFont (sans (12.0f));
        label.setJustificationType (juce::Justification::centredLeft);
        addAndMakeVisible (label);
    };

    setupLabel (targetLabel,  "Target");
    setupLabel (trimLabel,    "Trim");
    setupLabel (modeLabel,    "Mode");
    setupLabel (ceilingLabel, "Ceiling");
    setupLabel (learnLabel,   "Learn");

    setSize (470, 464);
    startTimerHz (15);
}

GainStagerAudioProcessorEditor::~GainStagerAudioProcessorEditor()
{
    stopTimer();
    setLookAndFeel (nullptr);
}

//==============================================================================
juce::Colour GainStagerAudioProcessorEditor::stateColour() const
{
    switch (state)
    {
        case GainStagerAudioProcessor::State::Learn: return theme::learn;
        case GainStagerAudioProcessor::State::Hold:  return theme::hold;
        case GainStagerAudioProcessor::State::Idle:
        default:                                     return theme::idle;
    }
}

juce::String GainStagerAudioProcessorEditor::stateName() const
{
    switch (state)
    {
        case GainStagerAudioProcessor::State::Learn: return "LEARNING";
        case GainStagerAudioProcessor::State::Hold:  return "HOLDING";
        case GainStagerAudioProcessor::State::Idle:
        default:                                     return "IDLE";
    }
}

juce::String GainStagerAudioProcessorEditor::statusLine() const
{
    if (state == GainStagerAudioProcessor::State::Hold)
        return "Trim is applied to everything downstream. Bounce to commit it.";

    if (resetPending)
        return "Reset. Waiting for audio to arrive.";

    const auto minimum = GainStagerAudioProcessor::minimumGatedSeconds;

    if (gatedSeconds < minimum)
        return "Needs " + juce::String (minimum - gatedSeconds, 1)
             + " s more audio before it can commit.";

    return "Ready. Commits when the transport stops, or at "
         + juce::String (learnSeconds, 0) + " s.";
}

//==============================================================================
void GainStagerAudioProcessorEditor::paint (juce::Graphics& g)
{
    g.fillAll (theme::background);

    paintHeader (g, headerArea);
    paintReadouts (g, readoutArea);
    paintStatus (g, statusArea);
}

void GainStagerAudioProcessorEditor::paintHeader (juce::Graphics& g, juce::Rectangle<int> area)
{
    g.setColour (theme::textBright);
    g.setFont (sans (15.0f, juce::Font::bold));
    g.drawText ("GAIN STAGER", area, juce::Justification::centredLeft);

    // State pill.
    const auto accent = stateColour();
    const auto name = stateName();
    const auto textWidth = juce::GlyphArrangement::getStringWidthInt (sans (10.5f, juce::Font::bold), name);
    auto pill = area.removeFromRight (textWidth + 26).withSizeKeepingCentre (textWidth + 26, 20);

    g.setColour (accent.withAlpha (0.16f));
    g.fillRoundedRectangle (pill.toFloat(), 10.0f);
    g.setColour (accent);
    g.drawRoundedRectangle (pill.toFloat().reduced (0.5f), 10.0f, 1.0f);
    g.setFont (sans (10.5f, juce::Font::bold));
    g.drawText (name, pill, juce::Justification::centred);
}

void GainStagerAudioProcessorEditor::paintReadout (juce::Graphics& g, juce::Rectangle<int> area,
                                                   const juce::String& caption,
                                                   const juce::String& value,
                                                   const juce::String& unitText,
                                                   juce::Colour valueColour) const
{
    g.setColour (theme::textFaint);
    g.setFont (sans (10.0f, juce::Font::bold));
    g.drawText (caption, area.removeFromTop (18), juce::Justification::centredLeft);

    auto unitStrip = area.removeFromBottom (16);
    g.setColour (theme::textDim);
    g.setFont (sans (11.0f));
    g.drawText (unitText, unitStrip, juce::Justification::centredLeft);

    g.setColour (valueColour);
    g.setFont (mono (32.0f, juce::Font::bold));
    g.drawText (value, area, juce::Justification::centredLeft);
}

void GainStagerAudioProcessorEditor::paintReadouts (juce::Graphics& g, juce::Rectangle<int> area)
{
    fillPanel (g, area);

    auto inner = area.reduced (16, 12);

    // True peak is secondary — it only matters when it collides with the
    // ceiling — so it sits as a footnote rather than competing with the two
    // numbers that carry the plugin.
    auto footer = inner.removeFromBottom (15);
    g.setColour (theme::textFaint);
    g.setFont (mono (10.5f));
    g.drawText (truePeakDb > -150.0
                    ? "true peak " + juce::String (truePeakDb, 2) + " dBTP"
                    : juce::String ("true peak --"),
                footer, juce::Justification::centredRight);

    auto left = inner.removeFromLeft (inner.getWidth() / 2);

    const bool haveMeasurement = measured > -150.0;
    const bool applying = state == GainStagerAudioProcessor::State::Hold;

    paintReadout (g, left, "MEASURED",
                  haveMeasurement ? juce::String (measured, 2) : juce::String ("--"),
                  haveMeasurement ? unit : juce::String(),
                  haveMeasurement ? theme::textBright : theme::textFaint);

    // The trim only greys out when it is not actually being applied, so the
    // panel never implies the audio is being changed when it is not.
    paintReadout (g, inner, "TRIM",
                  signedDb (trimDb), "dB",
                  applying ? theme::hold : theme::textFaint);
}

void GainStagerAudioProcessorEditor::paintStatus (juce::Graphics& g, juce::Rectangle<int> area)
{
    // A ceiling-limited trim is a mix that is wrong without looking wrong, so
    // the warning recolours the whole panel rather than adding a quiet line.
    if (ceilingLimited)
    {
        g.setColour (theme::warning.withAlpha (0.12f));
        g.fillRoundedRectangle (area.toFloat(), 6.0f);
        g.setColour (theme::warning.withAlpha (0.55f));
        g.drawRoundedRectangle (area.toFloat().reduced (0.5f), 6.0f, 1.0f);
    }
    else
    {
        fillPanel (g, area);
    }

    auto inner = area.reduced (16, 11);

    // The bar only exists while there is something to learn.
    if (state != GainStagerAudioProcessor::State::Hold)
    {
        auto barRow = inner.removeFromTop (16);
        auto amount = barRow.removeFromRight (104);

        g.setColour (theme::textDim);
        g.setFont (mono (11.0f));
        g.drawText (juce::String (gatedSeconds, 1) + " s of audio", amount,
                    juce::Justification::centredRight);

        const juce::Rectangle<float> track ((float) barRow.getX(), barRow.getCentreY() - 3.0f,
                                            (float) barRow.getWidth() - 12.0f, 6.0f);
        g.setColour (theme::background);
        g.fillRoundedRectangle (track, 3.0f);

        const auto span = juce::jmax (1.0, learnSeconds);
        const auto fraction = juce::jlimit (0.0, 1.0, gatedSeconds / span);

        if (fraction > 0.0)
            {
                g.setColour (theme::learn);
                g.fillRoundedRectangle (track.withWidth (juce::jmax (6.0f, track.getWidth() * (float) fraction)), 3.0f);
            }

        // Notch marking where a commit-on-stop becomes possible. Without it the
        // bar suggests nothing can happen until it reaches the far end.
        const auto notch = (float) (GainStagerAudioProcessor::minimumGatedSeconds / span);

        if (notch > 0.0f && notch < 1.0f)
        {
            g.setColour (theme::textFaint);
            g.fillRect (track.getX() + track.getWidth() * notch - 0.5f,
                        track.getY() - 3.0f, 1.0f, 12.0f);
        }

        inner.removeFromTop (7);
    }

    if (ceilingLimited)
    {
        // Ceiling limiting can only be set at commit, so this always coexists
        // with HOLD and there is room for both lines.
        auto first = inner.removeFromTop (inner.getHeight() / 2);

        // Plain ASCII only in drawn strings: a literal em-dash here rendered as
        // mojibake, since the char* is not read back as UTF-8.
        g.setColour (theme::warning);
        g.setFont (sans (11.5f, juce::Font::bold));
        g.drawText ("Trim held back by the ceiling: target not reached",
                    first, juce::Justification::centredLeft);

        g.setColour (theme::warning.withAlpha (0.75f));
        g.setFont (sans (11.0f));
        g.drawText ("Source peaks at " + juce::String (truePeakDb, 2)
                        + " dBTP; the full trim would have passed "
                        + juce::String (ceilingDb, 1) + " dBTP",
                    inner, juce::Justification::centredLeft);
        return;
    }

    g.setColour (theme::textDim);
    g.setFont (sans (11.5f));
    g.drawText (statusLine(), inner, juce::Justification::centredLeft);
}

//==============================================================================
void GainStagerAudioProcessorEditor::resized()
{
    auto area = getLocalBounds().reduced (18);

    headerArea = area.removeFromTop (26);
    area.removeFromTop (12);

    readoutArea = area.removeFromTop (104);
    area.removeFromTop (10);

    // Sized for the tallest content it ever holds — bar plus one line while
    // learning, two lines when the ceiling has engaged — so nothing below jumps.
    statusArea = area.removeFromTop (62);
    area.removeFromTop (14);

    auto row = [&area] ()
    {
        auto r = area.removeFromTop (26);
        area.removeFromTop (8);
        return r;
    };

    auto layoutRow = [] (juce::Rectangle<int> r, juce::Label& label, juce::Component& control)
    {
        label.setBounds (r.removeFromLeft (62));
        control.setBounds (r);
    };

    layoutRow (row(), targetLabel, targetSlider);
    layoutRow (row(), trimLabel, trimSlider);

    {
        auto r = row();
        modeLabel.setBounds (r.removeFromLeft (62));
        modeBox.setBounds (r.reduced (0, 1));
    }
    {
        auto r = row();
        ceilingLabel.setBounds (r.removeFromLeft (62));
        ceilingToggle.setBounds (r.removeFromRight (26));
        ceilingSlider.setBounds (r);
    }

    layoutRow (row(), learnLabel, learnSlider);

    area.removeFromTop (4);
    auto buttons = area.removeFromTop (30);
    autoLearnToggle.setBounds (buttons.removeFromLeft (110));
    resetButton.setBounds (buttons.removeFromRight (92));
    buttons.removeFromRight (8);
    holdButton.setBounds (buttons.removeFromRight (104));
}

//==============================================================================
void GainStagerAudioProcessorEditor::timerCallback()
{
    const auto newState = processorRef.getState();
    const auto newMeasured = processorRef.getMeasured();
    const auto newTrim = (double) *processorRef.apvts.getRawParameterValue ("trim");
    const auto newGated = processorRef.getGatedSeconds();
    const auto newPeak = processorRef.getTruePeakDb();
    const auto newLearn = processorRef.getLearnSeconds();
    const auto newCeiling = (double) *processorRef.apvts.getRawParameterValue ("ceiling");
    const auto newLimited = processorRef.isCeilingLimited();
    const auto newReset = processorRef.isResetPending();
    const auto newUnit = processorRef.getMeasurementUnit();

    const bool changed = newState != state
                      || newMeasured != measured
                      || newTrim != trimDb
                      || newGated != gatedSeconds
                      || newPeak != truePeakDb
                      || newLearn != learnSeconds
                      || newCeiling != ceilingDb
                      || newLimited != ceilingLimited
                      || newReset != resetPending
                      || newUnit != unit;

    if (! changed)
        return;

    state = newState;
    measured = newMeasured;
    trimDb = newTrim;
    gatedSeconds = newGated;
    truePeakDb = newPeak;
    learnSeconds = newLearn;
    ceilingDb = newCeiling;
    ceilingLimited = newLimited;
    resetPending = newReset;
    unit = newUnit;

    repaint();
}
