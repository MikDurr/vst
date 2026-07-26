// Renders the editor to PNGs without a host.
//
// Looking at the UI used to mean inserting the plugin into a real Logic
// session, which is disruptive and not repeatable. This drives the processor
// directly, pumps the message loop so the timers fire, and writes one image per
// state. Run it after any UI change.
//
//   ./build/plugin/ui_snapshot_artefacts/ui_snapshot <output-dir>

#include "../Source/PluginEditor.h"
#include "../Source/PluginProcessor.h"

#include <cmath>
#include <memory>

namespace
{
    constexpr double sampleRate = 44100.0;
    constexpr double pi = 3.14159265358979323846;

    /** Pushes a sine through processBlock exactly as a host would. */
    void feed (GainStagerAudioProcessor& processor,
               double frequency, double amplitude, double seconds)
    {
        constexpr int blockSize = 512;
        juce::AudioBuffer<float> buffer (2, blockSize);
        juce::MidiBuffer midi;

        const auto total = (int) (sampleRate * seconds);

        for (int done = 0; done < total; done += blockSize)
        {
            const auto n = juce::jmin (blockSize, total - done);
            buffer.setSize (2, n, false, false, true);

            for (int i = 0; i < n; ++i)
            {
                const auto v = (float) (amplitude * std::sin (2.0 * pi * frequency * (done + i) / sampleRate));
                buffer.setSample (0, i, v);
                buffer.setSample (1, i, v);
            }

            processor.processBlock (buffer, midi);
        }
    }

    /** Lets the processor's 10 Hz timer and the editor's 15 Hz timer run. */
    void pump (int milliseconds)
    {
        juce::MessageManager::getInstance()->runDispatchLoopUntil (milliseconds);
    }

    void write (juce::Component& component, const juce::File& file)
    {
        const auto image = component.createComponentSnapshot (component.getLocalBounds(), false, 2.0f);

        file.deleteFile();

        if (auto stream = std::unique_ptr<juce::FileOutputStream> (file.createOutputStream()))
        {
            juce::PNGImageFormat png;
            png.writeImageToStream (image, *stream);
        }

        std::printf ("  wrote %s\n", file.getFullPathName().toRawUTF8());
    }

    struct Rig
    {
        GainStagerAudioProcessor processor;
        std::unique_ptr<juce::AudioProcessorEditor> editor;

        Rig()
        {
            processor.prepareToPlay (sampleRate, 512);
            editor.reset (processor.createEditor());
        }

        void setParam (const juce::String& id, float value)
        {
            if (auto* p = processor.apvts.getParameter (id))
                p->setValueNotifyingHost (p->convertTo0to1 (value));
        }
    };
}

int main (int argc, char** argv)
{
    const juce::ScopedJuceInitialiser_GUI juceInit;

    const juce::File outDir = argc > 1
        ? juce::File::getCurrentWorkingDirectory().getChildFile (juce::String (argv[1]))
        : juce::File::getCurrentWorkingDirectory();

    outDir.createDirectory();
    std::printf ("gain-stager :: UI snapshots -> %s\n", outDir.getFullPathName().toRawUTF8());

    // 1. Idle. Nothing learned, nothing applied.
    {
        Rig rig;
        pump (300);
        write (*rig.editor, outDir.getChildFile ("ui-1-idle.png"));
    }

    // 2. Learning, partway to the auto-commit threshold.
    {
        Rig rig;
        feed (rig.processor, 1000.0, std::pow (10.0, -30.0 / 20.0), 4.0);
        pump (300);
        write (*rig.editor, outDir.getChildFile ("ui-2-learning.png"));
    }

    // 3. Holding, trim applied. -30 LUFS source against a -18 target.
    {
        Rig rig;
        feed (rig.processor, 1000.0, std::pow (10.0, -30.0 / 20.0), 12.0);
        pump (200);
        rig.processor.commitNow();
        pump (300);
        write (*rig.editor, outDir.getChildFile ("ui-3-holding.png"));
    }

    // 4. Ceiling-limited. A 20 Hz tone is heavily attenuated by K-weighting but
    //    keeps its true peak, so the crest factor exceeds the headroom between
    //    the target and the ceiling and the trim has to be backed off.
    {
        Rig rig;
        feed (rig.processor, 20.0, 0.2, 12.0);
        pump (200);
        rig.processor.commitNow();
        pump (300);
        write (*rig.editor, outDir.getChildFile ("ui-4-ceiling-limited.png"));
    }

    std::printf ("done\n");
    return 0;
}
