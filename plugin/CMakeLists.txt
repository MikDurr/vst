juce_add_plugin(GainStager
    COMPANY_NAME "mikaild"
    BUNDLE_ID "com.mikaild.gainstager"
    IS_SYNTH FALSE
    NEEDS_MIDI_INPUT FALSE
    NEEDS_MIDI_OUTPUT FALSE
    IS_MIDI_EFFECT FALSE
    EDITOR_WANTS_KEYBOARD_FOCUS FALSE
    COPY_PLUGIN_AFTER_BUILD TRUE
    PLUGIN_MANUFACTURER_CODE Mkdd
    PLUGIN_CODE Gnst
    FORMATS AU Standalone
    PRODUCT_NAME "Gain Stager"
)

target_sources(GainStager PRIVATE
    Source/PluginProcessor.cpp
    Source/PluginEditor.cpp
)

target_compile_definitions(GainStager PUBLIC
    JUCE_WEB_BROWSER=0
    JUCE_USE_CURL=0
    JUCE_VST3_CAN_REPLACE_VST2=0
)

target_link_libraries(GainStager PRIVATE
    gs_core
    juce::juce_audio_utils
    juce::juce_audio_processors
    juce::juce_dsp
    juce::juce_gui_basics
    juce::juce_recommended_config_flags
    juce::juce_recommended_warning_flags
)

# Logic will not load an unsigned component. JUCE's COPY_PLUGIN_AFTER_BUILD step
# is itself a POST_BUILD command registered earlier, so by the time this runs the
# bundle is already installed and both copies need the ad-hoc signature.
add_custom_command(TARGET GainStager_AU POST_BUILD
    COMMAND codesign --force --sign - --timestamp=none
            "$<TARGET_BUNDLE_DIR:GainStager_AU>"
    COMMAND codesign --force --sign - --timestamp=none
            "$ENV{HOME}/Library/Audio/Plug-Ins/Components/Gain Stager.component"
    VERBATIM
)
