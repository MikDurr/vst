// Processor-level tests. The core tests cover the DSP; these cover the things
// only the whole plugin can be wrong about: gain actually reaching the audio,
// bypass, state round-trips, presets, and the commit state machine.

#include "../Source/PluginProcessor.h"

#include <cmath>
#include <cstdio>
#include <memory>
#include <string>

namespace
{
    constexpr double sr = 48000.0;
    constexpr double pi = 3.14159265358979323846;

    int failures = 0, checks = 0;

    void check (bool ok, const std::string& what, const std::string& detail = {})
    {
        ++checks;
        std::printf (ok ? "  ok    %s\n" : "  FAIL  %s   %s\n", what.c_str(), detail.c_str());
        if (! ok) ++failures;
    }

    void checkClose (double a, double b, double tol, const std::string& what)
    {
        char d[192];
        std::snprintf (d, sizeof (d), "(got %.4f, expected %.4f, tol %.4f)", a, b, tol);
        check (std::abs (a - b) <= tol, what, d);
    }

    void pump (int ms) { juce::MessageManager::getInstance()->runDispatchLoopUntil (ms); }

    /** Feeds a sine and returns the RMS ratio out/in in dB. */
    double feed (GainStagerAudioProcessor& p, double freq, double amp, double seconds)
    {
        constexpr int block = 512;
        juce::AudioBuffer<float> buf (2, block);
        juce::MidiBuffer midi;
        const auto total = (int) (sr * seconds);
        double inSum = 0.0, outSum = 0.0; long n = 0;

        for (int done = 0; done < total; done += block)
        {
            const auto count = juce::jmin (block, total - done);
            buf.setSize (2, count, false, false, true);

            for (int i = 0; i < count; ++i)
            {
                const auto v = (float) (amp * std::sin (2.0 * pi * freq * (done + i) / sr));
                buf.setSample (0, i, v); buf.setSample (1, i, v);
                inSum += (double) v * v; ++n;
            }

            p.processBlock (buf, midi);

            for (int i = 0; i < count; ++i)
                outSum += (double) buf.getSample (0, i) * buf.getSample (0, i);
        }

        if (n == 0 || inSum <= 0.0 || outSum <= 0.0) return -1000.0;
        return 10.0 * std::log10 (outSum / inSum);
    }

    struct Rig
    {
        GainStagerAudioProcessor p;
        Rig() { p.prepareToPlay (sr, 512); }
        void set (const juce::String& id, float v)
        {
            if (auto* q = p.apvts.getParameter (id)) q->setValueNotifyingHost (q->convertTo0to1 (v));
        }
        float get (const juce::String& id) const { return *p.apvts.getRawParameterValue (id); }
    };

    const double quietAmp = std::pow (10.0, -30.0 / 20.0);   // -30 LUFS stereo
}

int main()
{
    const juce::ScopedJuceInitialiser_GUI init;
    std::printf ("gain-stager :: processor tests\n");

    std::printf ("\nBasics\n");
    {
        Rig r;
        check (r.p.getLatencySamples() == 0, "reports zero latency");
        check (r.p.getNumPrograms() == gs::presetCount(), "exposes every preset as a program");
        check (r.p.getProgramName (1).isNotEmpty(), "programs are named");
    }

    std::printf ("\nGain actually reaches the audio\n");
    {
        Rig r;
        feed (r.p, 1000.0, quietAmp, 12.0);
        pump (400);
        check (r.p.getState() == GainStagerAudioProcessor::State::Hold, "auto-commits after learnSeconds");
        checkClose (r.get ("trim"), 12.0, 0.1, "trim is +12 dB for a -30 LUFS source at -18");

        const auto applied = feed (r.p, 1000.0, quietAmp, 2.0);
        checkClose (applied, 12.0, 0.15, "output is +12 dB louder than input");
    }

    std::printf ("\nBypass\n");
    {
        Rig r;
        feed (r.p, 1000.0, quietAmp, 12.0);
        pump (400);
        r.set ("bypass", 1.0f);
        const auto applied = feed (r.p, 1000.0, quietAmp, 2.0);
        checkClose (applied, 0.0, 0.05, "bypass passes audio through unchanged");
    }

    std::printf ("\nState round-trip\n");
    {
        Rig a;
        a.set ("mode", 0.0f);
        feed (a.p, 1000.0, quietAmp, 12.0);
        pump (400);
        a.p.setCurrentProgram (6);          // Guitar
        feed (a.p, 1000.0, quietAmp, 12.0);
        pump (400);

        const auto trimBefore = a.get ("trim");
        const auto programBefore = a.p.getCurrentProgram();

        juce::MemoryBlock blob;
        a.p.getStateInformation (blob);

        Rig b;
        b.p.setStateInformation (blob.getData(), (int) blob.getSize());

        checkClose (b.get ("trim"), trimBefore, 1e-4, "trim survives save/load");
        check (b.get ("hold") > 0.5f, "comes back in HOLD");
        check (b.p.getCurrentProgram() == programBefore, "program survives save/load");

        // The mix must not change on reload: no re-learning.
        const auto applied = feed (b.p, 1000.0, quietAmp, 3.0);
        checkClose (applied, trimBefore, 0.2, "reloaded plugin applies the same trim");
        check (b.p.getState() == GainStagerAudioProcessor::State::Hold, "and stays in HOLD");
    }

    std::printf ("\nPresets\n");
    {
        Rig r;
        for (int i = 0; i < gs::presetCount(); ++i)
        {
            r.p.setCurrentProgram (i);
            const auto& preset = gs::presets()[i];
            const bool ok = std::abs (r.get ("target") - preset.targetLufs) < 0.05f
                         && std::abs (r.get ("ceiling") - preset.ceilingDbTp) < 0.05f
                         && std::abs (r.get ("learnSeconds") - preset.learnSeconds) < 0.05f;
            if (! ok)
                check (false, std::string ("preset applies its values: ") + preset.name);
        }
        check (true, "every preset applies its target, ceiling and learn time");

        // A preset changes what "correct" means, so it must re-arm.
        r.p.setCurrentProgram (0);          // Default: 10 s learn
        pump (200);
        feed (r.p, 1000.0, quietAmp, 12.0);
        pump (400);
        check (r.p.getState() == GainStagerAudioProcessor::State::Hold, "holds before switching preset");
        r.p.setCurrentProgram (1);
        pump (300);
        check (r.p.getState() != GainStagerAudioProcessor::State::Hold, "switching preset re-arms");
    }

    std::printf ("\nEditing while held\n");
    {
        Rig r;
        feed (r.p, 1000.0, quietAmp, 12.0);
        pump (400);
        checkClose (r.get ("trim"), 12.0, 0.1, "committed at -18 target");

        r.set ("target", -24.0f);
        pump (400);
        checkClose (r.get ("trim"), 6.0, 0.1, "moving the target while held updates the trim");
    }

    std::printf ("\nModes that cannot measure yet\n");
    {
        Rig r;
        r.p.setCurrentProgram (3);            // Drums - bus, short-term max
        feed (r.p, 1000.0, quietAmp, 1.0);    // under the 3 s short-term window
        pump (300);
        r.p.commitNow();
        pump (300);
        check (r.p.getState() != GainStagerAudioProcessor::State::Hold,
               "will not commit a measurement it does not have");
        check (r.p.getMeasured() <= -150.0, "and reports no measurement");
    }

    std::printf ("\nShort material\n");
    {
        Rig r;
        r.p.setCurrentProgram (4);            // Drums - one-shot, true peak
        feed (r.p, 1000.0, quietAmp, 0.4);    // a single hit
        pump (400);
        check (r.p.getState() != GainStagerAudioProcessor::State::Hold,
               "a 0.4 s one-shot does not auto-commit");
        r.p.commitNow();
        pump (200);
        check (r.p.getState() == GainStagerAudioProcessor::State::Hold,
               "but Hold now still works on it");
    }

    std::printf ("\n%d checks, %d failures\n", checks, failures);
    return failures == 0 ? 0 : 1;
}
