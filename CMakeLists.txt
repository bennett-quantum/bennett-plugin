cmake_minimum_required(VERSION 3.16)
project(bennett-plugin LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# LLVM is optional at configure time so the skeleton configures anywhere.
find_package(LLVM CONFIG QUIET)

if(NOT LLVM_FOUND)
  message(STATUS "bennett-plugin: LLVM not found; skipping the BennettPlugin target "
                 "(set LLVM_DIR to <llvm>/lib/cmake/llvm to build)")
else()
  message(STATUS "bennett-plugin: using LLVM ${LLVM_PACKAGE_VERSION} from ${LLVM_DIR}")
  include_directories(${LLVM_INCLUDE_DIRS})
  add_definitions(${LLVM_DEFINITIONS})
  add_library(BennettPlugin MODULE src/BennettPlugin.cpp)
  target_compile_definitions(BennettPlugin PRIVATE BENNETT_HAVE_LLVM=1)
  # Pass plugins resolve LLVM symbols from the host (opt/clang), so do not link LLVM here.
  set_target_properties(BennettPlugin PROPERTIES PREFIX "" CXX_VISIBILITY_PRESET hidden)
endif()
