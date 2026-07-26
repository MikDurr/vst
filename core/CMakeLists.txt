# Deliberately free of JUCE. This is the piece that has to be exactly right,
# the piece with published reference values to test against, and the piece a
# future offline CLI would reuse unchanged.
add_library(gs_core STATIC
    LoudnessMeter.cpp
    TrimCalculator.cpp
    TruePeakMeter.cpp
)

target_include_directories(gs_core PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})

add_executable(test_loudness tests/test_loudness.cpp)
target_link_libraries(test_loudness PRIVATE gs_core)

add_test(NAME loudness COMMAND test_loudness)
