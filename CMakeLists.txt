# Copyright 2023-2024 DreamWorks Animation LLC
# SPDX-License-Identifier: Apache-2.0

install(DIRECTORY render_profile_viewer
        DESTINATION python/render_profile_viewer)

install(FILES setup.py_open
        DESTINATION python/render_profile_viewer
        RENAME setup.py)

