# Copyright 2023-2024 DreamWorks Animation LLC
# SPDX-License-Identifier: Apache-2.0

cmake_minimum_required (VERSION 3.23.1)

include(OMR_PackageVersion)  # Sets versionString, projectString and PACKAGE_NAME
project(${projectString}
    VERSION ${versionString}
    LANGUAGES NONE) # don't try to test the CXX compiler

install(DIRECTORY render_profile_viewer
        DESTINATION python/render_profile_viewer)

install(FILES setup.py_open
        DESTINATION python/render_profile_viewer
        RENAME setup.py)

