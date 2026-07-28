cmake_minimum_required(VERSION 3.24)

project(VocalignPersonal VERSION 0.0.1)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_OSX_ARCHITECTURES "arm64" CACHE STRING "" FORCE)
set(CMAKE_OSX_DEPLOYMENT_TARGET "13.0" CACHE STRING "" FORCE)

add_subdirectory(third_party/JUCE)

juce_set_ara_sdk_path(${CMAKE_SOURCE_DIR}/third_party/ARA_SDK)

add_subdirectory(plugin/spike)
