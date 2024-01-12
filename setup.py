# Copyright 2023-2024 DreamWorks Animation LLC
# SPDX-License-Identifier: Apache-2.0

# This setup.py is run under two conditions:
# 1) A developer, Read the Docs server or CI process runs it via python setup.py ...
# 2) A rez-build or rez-release triggers it via bart-setuptools.

# In (1), the only relevant non-standard bits are writing _version.py
# In (2), we need to make sure any build number appended by rez_earlybind
# is removed before it is passed to setup().  Build numbers for pre-releases
# should be set in setup.cfg, so those get preserved.

import os

import pkg_resources
import setuptools.config

CONFIG_FILE = "setup.cfg"
NUMPSEP = "."

config = setuptools.config.read_configuration(CONFIG_FILE)
name = config["metadata"]["name"]
pyversion = pkg_resources.safe_version(config["metadata"]["version"])
rezversion = os.getenv("REZ_BUILD_PROJECT_VERSION")

# Make sure version from rez-build, e.g. 1.2.3.alpha.4 gets PEP440ified.
# Runtime version from rez-build takes precedence over setup.cfg.
if rezversion:
    pyversion = pkg_resources.safe_version(rezversion)

# Conform standard releases to the 3 tokens preferred by the pydevs.
# Pre-releases will always be 3 tokens, e.g. 1.2.3a0
version = NUMPSEP.join(str(_) for _ in pyversion.split(NUMPSEP)[0:3])

# I stole this idea from setuptools_scm.
versionfile = os.path.join(name, "_version.py")
with open(versionfile, "w") as fh:
    fh.write(os.linesep.join(
        [
            "# coding: utf-8",
            "# file generated by setup.py",
            "# don't change, don't track in version control",
            "__version__ = '{}'".format(version)
        ]
    )
    )

setuptools.setup(version=version,
                 data_files=[(name, [versionfile])])

