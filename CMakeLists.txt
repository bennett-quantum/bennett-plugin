cmake_minimum_required(VERSION 3.20)
project(bennett-plugin LANGUAGES C CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
option(BENNETT_COVERAGE "Instrument a single LLVM-major GCC build with gcov" OFF)
if(BENNETT_COVERAGE AND NOT LLVM_DIR)
  message(FATAL_ERROR "Set LLVM_DIR to select one major for coverage")
endif()
if(NOT LLVM_DIR)
  include(ExternalProject)
  foreach(major 18 23)
    ExternalProject_Add(llvm${major}
      SOURCE_DIR "${CMAKE_CURRENT_SOURCE_DIR}"
      BINARY_DIR "${CMAKE_CURRENT_BINARY_DIR}/llvm${major}"
      CMAKE_ARGS -DLLVM_DIR=/usr/lib/llvm-${major}/lib/cmake/llvm
        -DCMAKE_BUILD_TYPE=RelWithDebInfo -DBENNETT_OUTPUT_DIR=${CMAKE_CURRENT_BINARY_DIR}
      INSTALL_COMMAND "" BUILD_ALWAYS TRUE)
  endforeach()
else()
  find_package(LLVM REQUIRED CONFIG)
  if(NOT LLVM_VERSION_MAJOR MATCHES "^(18|23)$")
    message(FATAL_ERROR "Tested LLVM majors are 18 and 23")
  endif()
  add_library(BennettPlugin MODULE src/BennettPlugin.cpp src/NativeComparison.cpp src/Analysis.cpp src/Scalar.cpp src/Normalise.cpp src/SoftFloat.cpp src/Wide.cpp src/Integer.cpp src/Memory.cpp src/Residual.cpp src/Production.cpp src/Snapshot.cpp)
  if(BENNETT_COVERAGE)
    if(NOT CMAKE_CXX_COMPILER_ID STREQUAL "GNU")
      message(FATAL_ERROR "BENNETT_COVERAGE requires GCC and matching gcov")
    endif()
    target_compile_options(BennettPlugin PRIVATE --coverage -O0 -g1)
    target_link_options(BennettPlugin PRIVATE --coverage)
  endif()
  target_include_directories(BennettPlugin SYSTEM PRIVATE ${LLVM_INCLUDE_DIRS})
  target_compile_definitions(BennettPlugin PRIVATE ${LLVM_DEFINITIONS})
  set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS
    "${CMAKE_CURRENT_SOURCE_DIR}/SPEC_VERSIONS.toml"
    "${CMAKE_CURRENT_SOURCE_DIR}/gate.toml"
    "${CMAKE_CURRENT_SOURCE_DIR}/tests/contracts.py"
    "${CMAKE_CURRENT_SOURCE_DIR}/tests/pinned_siblings.py")
  find_package(Python3 REQUIRED COMPONENTS Interpreter)
  execute_process(
    COMMAND "${Python3_EXECUTABLE}" -c
      "import sys; sys.path.insert(0, sys.argv[1] + '/tests'); from contracts import arith_path; print(arith_path(int(sys.argv[2])).absolute())"
      "${CMAKE_CURRENT_SOURCE_DIR}" "${LLVM_VERSION_MAJOR}"
    WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
    RESULT_VARIABLE arith_status OUTPUT_VARIABLE arith_path ERROR_VARIABLE arith_error
    OUTPUT_STRIP_TRAILING_WHITESPACE)
  if(NOT arith_status STREQUAL "0")
    message(FATAL_ERROR "Pinned arithmetic LLVM ${LLVM_VERSION_MAJOR} unavailable:\n${arith_error}")
  endif()
  file(READ "${CMAKE_CURRENT_SOURCE_DIR}/SPEC_VERSIONS.toml" spec_pins)
  string(REGEX MATCH "llvm${LLVM_VERSION_MAJOR}_sha256 = \"([^\"]+)\"" arith_pin "${spec_pins}")
  if(NOT arith_pin)
    message(FATAL_ERROR "Missing arith LLVM ${LLVM_VERSION_MAJOR} sha256 pin")
  endif()
  set(arith_sha256 "${CMAKE_MATCH_1}")
  target_compile_definitions(BennettPlugin PRIVATE
    BENNETT_ARITH_DEFAULT_PATH="${arith_path}"
    BENNETT_ARITH_DEFAULT_SHA256="${arith_sha256}")
  set_target_properties(BennettPlugin PROPERTIES OUTPUT_NAME bennett-plugin-${LLVM_VERSION_MAJOR})
  if(BENNETT_OUTPUT_DIR)
    set_target_properties(BennettPlugin PROPERTIES LIBRARY_OUTPUT_DIRECTORY "${BENNETT_OUTPUT_DIR}")
  endif()
endif()
