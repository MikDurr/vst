cmake_minimum_required(VERSION 3.24)

project(GainStager VERSION 0.0.1)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_OSX_ARCHITECTURES "arm64" CACHE STRING "" FORCE)
set(CMAKE_OSX_DEPLOYMENT_TARGET "13.0" CACHE STRING "" FORCE)

# JUCE is shared by path with the sibling vocalign-personal checkout rather than
# vendored again here. Override with -DJUCE_PATH=<path> to build standalone.
set(JUCE_PATH "${CMAKE_CURRENT_SOURCE_DIR}/../vocalign-personal/third_party/JUCE"
    CACHE PATH "Path to a JUCE checkout")

if(NOT EXISTS "${JUCE_PATH}/CMakeLists.txt")
    message(FATAL_ERROR
        "JUCE not found at ${JUCE_PATH}\n"
        "Pass -DJUCE_PATH=<path-to-JUCE> to point at a checkout.")
endif()

add_subdirectory(${JUCE_PATH} ${CMAKE_BINARY_DIR}/juce EXCLUDE_FROM_ALL)

enable_testing()

add_subdirectory(core)
add_subdirectory(plugin)
