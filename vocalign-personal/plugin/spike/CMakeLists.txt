juce_add_plugin(AraSpike
    COMPANY_NAME "mikaild"
    BUNDLE_ID "com.mikaild.arspike"
    IS_SYNTH FALSE
    NEEDS_MIDI_INPUT FALSE
    NEEDS_MIDI_OUTPUT FALSE
    IS_MIDI_EFFECT FALSE
    IS_ARA_EFFECT TRUE
    EDITOR_WANTS_KEYBOARD_FOCUS FALSE
    COPY_PLUGIN_AFTER_BUILD TRUE
    PLUGIN_MANUFACTURER_CODE Mkdd
    PLUGIN_CODE Arsp
    FORMATS AU Standalone
    PRODUCT_NAME "ARA Spike"
)

target_sources(AraSpike PRIVATE
    Source/PluginProcessor.cpp
    Source/PluginEditor.cpp
)

target_compile_definitions(AraSpike PUBLIC
    JUCE_WEB_BROWSER=0
    JUCE_USE_CURL=0
    JUCE_VST3_CAN_REPLACE_VST2=0
)

target_link_libraries(AraSpike PRIVATE
    juce::juce_audio_utils
    juce::juce_audio_processors
    juce::juce_gui_basics
    juce_ara_sdk
    juce::juce_recommended_config_flags
    juce::juce_recommended_warning_flags
)
