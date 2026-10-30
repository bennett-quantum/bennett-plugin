cmake_minimum_required(VERSION 3.20)
project(bennett-plugin LANGUAGES C CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(NOT LLVM_DIR)
  include(ExternalProject)
  foreach(major 18 23)
    ExternalProject_Add(llvm${major}
      SOURCE_DIR "${CMAKE_CURRENT_SOURCE_DIR}"
      BINARY_DIR "${CMAKE_CURRENT_BINARY_DIR}/llvm${major}"
      CMAKE_ARGS -DLLVM_DIR=/usr/lib/llvm-${major}/lib/cmake/llvm
        -DCMAKE_BUILD_TYPE=Debug -DBENNETT_OUTPUT_DIR=${CMAKE_CURRENT_BINARY_DIR}
      INSTALL_COMMAND "" BUILD_ALWAYS TRUE)
  endforeach()
else()
  find_package(LLVM REQUIRED CONFIG)
  if(NOT LLVM_VERSION_MAJOR MATCHES "^(18|23)$")
    message(FATAL_ERROR "Tested LLVM majors are 18 and 23")
  endif()
  add_library(BennettPlugin MODULE src/BennettPlugin.cpp src/Analysis.cpp src/Scalar.cpp src/Normalise.cpp)
  target_include_directories(BennettPlugin SYSTEM PRIVATE ${LLVM_INCLUDE_DIRS})
  target_compile_definitions(BennettPlugin PRIVATE ${LLVM_DEFINITIONS})
  set_target_properties(BennettPlugin PROPERTIES OUTPUT_NAME bennett-plugin-${LLVM_VERSION_MAJOR})
  if(BENNETT_OUTPUT_DIR)
    set_target_properties(BennettPlugin PROPERTIES LIBRARY_OUTPUT_DIRECTORY "${BENNETT_OUTPUT_DIR}")
  endif()
endif()
