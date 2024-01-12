# Copyright 2023-2024 DreamWorks Animation LLC
# SPDX-License-Identifier: Apache-2.0

from __future__ import absolute_import, division, print_function

import logging

# Setting top level logger according to library standard in
# https://docs.python.org/2/howto/logging.html#configuring-logging-for-a-library
#
# Submodules can now do "logger = logging.getLogger(__name__)" to get a logger
#
# Users of this package are responsible for setting handlers
# (i.e. logging.basicConfig()) and (optionally) set logging level using
# render_profile_viewer.logger.setLevel() in order to see/configure logging output
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


try:
    from ._version import __version__
except ImportError:
    logger.warning("Package needs built to expose an accurate version number.")
    __version__ = '0.0.0'

