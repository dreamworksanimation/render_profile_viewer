# -*- coding: utf-8 -*-
#
# render_profile_viewer documentation build configuration file.
#
# This file is execfile()d with the current directory set to its containing dir.

from distutils.errors import DistutilsFileError
import os
import pkg_resources
from recommonmark.parser import CommonMarkParser
from recommonmark.transform import AutoStructify
import setuptools.config
import sys


# If extensions (or modules to document with autodoc) are in another directory,
# add these directories to sys.path here. If the directory is relative to the
# documentation root, use os.path.abspath to make it absolute, like shown here.
# sys.path.insert(0, os.path.abspath('.'))
sys.path.insert(0, os.path.abspath('../'))

# -- General configuration ------------------------------------------------

# If your documentation needs a minimal Sphinx version, state it here.
#
needs_sphinx = '1.8'

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom ones.
extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.doctest',
    'sphinx.ext.intersphinx',
    'sphinx.ext.todo',
    'sphinx.ext.coverage',
    'sphinx.ext.ifconfig',
    'sphinx.ext.viewcode',
    'sphinx.ext.napoleon',
    'sphinx.ext.extlinks',
    'sphinx.ext.autosummary',
    'sphinxcontrib.apidoc',
    'sphinx.ext.mathjax',
    # 'nbsphinx',  # Uncomment for Jupyter Notebook support
]

# Add any imports that Sphinx needs to mock when building. These are python
# imports that are literally impossible to include in any virtualenv, such
# as the 'nuke' and 'hou' modules that you get by launching Nuke and Houdini.
# See http://mydw.anim.dreamworks.com/display/DTDDOC/ReadTheDocs+Walkthroughs
# For more information
autodoc_mock_imports = [
]

# autoclass_content is the option to show only the class docstring with 'class'
# both class and __init__ with 'both'
# or just __init__ with 'init'
# If the class doesn't have __init__ or it isn't documented, __new__ is used.
# http://www.sphinx-doc.org/en/master/usage/extensions/autodoc.html#confval-autoclass_content
autoclass_content = 'both'

# These options control which methods and functions sphinx builds when it
# documents a class and module.
# You can choose to document specific special-members, etc.
# Note that the 'member-order' option doesn't work. Alphabetical only.
# http://www.sphinx-doc.org/en/master/usage/extensions/autodoc.html#confval-autodoc_default_options
autodoc_default_options = {
    'members': None,  # None means all
    'undoc-members': None,
    'inherited-members': None,
    'show-inheritance': None,
}

# Add any paths that contain templates here, relative to this directory.
templates_path = ['_templates']

# The suffix of source filenames.
source_suffix = '.rst'

# Instructions for how to render different extensions
source_parsers = {
    '.md': CommonMarkParser,
}

# The master toctree document.
master_doc = 'index'

# General information about the project.
project = u'render_profile_viewer'

# Apidoc controls how apidocumentation is built.
# Documentation: https://github.com/sphinx-contrib/apidoc
apidoc_module_dir = '../render_profile_viewer'
apidoc_output_dir = 'api'
apidoc_separate_modules = True
apidoc_toc_file = False
apidoc_excluded_paths = ['_version.py']
apidoc_extra_args = ['-P', '-f']

# The version info for the project you're documenting, acts as replacement for
# |version| and |release|, also used in various other places throughout the
# built documents.
try:
    config = setuptools.config.read_configuration(os.path.abspath('../setup.cfg'))
except DistutilsFileError:
    # No config file. This build will be without a version
    pass
else:
    # The full version, including alpha/beta/rc tags.
    release = pkg_resources.safe_version(config["metadata"]["version"])
    # The short X.Y version.
    version = '.'.join(release.split('.')[0:2])

# There are two options for replacing |today|: either, you set today to some
# non-false value, then it is used:
#
# today = ''
#
# Else, today_fmt is used as the format for a strftime call.
#
today_fmt = '%Y-%m-%d %H:%M:%S'

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
# This pattern also affects the html_static_path and html_extra_path folders.
exclude_patterns = [
    '_build',
    '**.ipynb_checkpoints',
]

# The name of the Pygments (syntax highlighting) style to use.
pygments_style = 'sphinx'

# If true, keep warnings as "system message" paragraphs in the built documents.
# keep_warnings = False

# If true, `todo` and `todoList` produce output, else they produce nothing.
todo_include_todos = True

# -- nbsphinx jupyter notebook options -----------------------------------------

# Execute notebooks before conversion: 'always', 'never', 'auto' (default)
# nbsphinx_execute = 'never'

# Use this kernel instead of the one stored in the notebook metadata:
nbsphinx_kernel_name = 'python2'

# List of arguments to be passed to the kernel that executes the notebooks:
# nbsphinx_execute_arguments = [
#     "--InlineBackend.figure_formats={'svg', 'pdf'}",
#     "--InlineBackend.rc={'figure.dpi': 96}",
# ]

# If True, the build process is continued even if an exception occurs:
# nbsphinx_allow_errors = True

# Controls when a cell will time out (defaults to 30; use -1 for no timeout):
# nbsphinx_timeout = 60

# Default Pygments lexer for syntax highlighting in code cells:
# nbsphinx_codecell_lexer = 'ipython3'

# Width of input/output prompts used in CSS:
# nbsphinx_prompt_width = '8ex'

# If window is narrower than this, input/output prompts are on separate lines:
# nbsphinx_responsive_width = '700px'

# This is processed by Jinja2 and inserted before each notebook
# nbsphinx_prolog = ''

# This is processed by Jinja2 and inserted after each notebook
# nbsphinx_epilog = ''

# Input prompt for code cells. "%s" is replaced by the execution count.
# nbsphinx_input_prompt = 'In [%s]:'

# Output prompt for code cells. "%s" is replaced by the execution count.
# nbsphinx_output_prompt = 'Out[%s]:'

# Specify conversion functions for custom notebook formats:
# import jupytext
# nbsphinx_custom_formats = {
#     '.Rmd': lambda s: jupytext.reads(s, '.Rmd'),
# }

# -- Options for HTML output --------------------------------------------------

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.
html_theme = 'sphinx_rtd_theme'
# If you want a logo, add it to _static and uncomment the lines below.
# html_logo = '_static/logo.png'
# html_theme_options = {
#     'logo_only': True,
# }

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
html_static_path = ['_static']

# Output file base name for HTML help builder.
htmlhelp_basename = 'render_profile_viewerdocs'


# -- Options for LaTeX output -------------------------------------------------

latex_elements = {}

# Grouping the document tree into LaTeX files. List of tuples
# (source start file, target name, title, author, documentclass [howto/manual]).
latex_documents = [
    (
        'index',
        'render_profile_viewer.tex',
        u'render_profile_viewer Documentation',
        u"""Smart People""", 'manual'
    ),
]


# -- Options for manual page output -------------------------------------------

# One entry per manual page. List of tuples
# (source start file, name, description, authors, manual section).
man_pages = [
    (
        'index',
        'render_profile_viewer',
        u'render_profile_viewer Documentation',
        [u"""Smart People"""],
        1
    )
]


# -- Options for Texinfo output -----------------------------------------------

# Grouping the document tree into Texinfo files. List of tuples
# (source start file, target name, title, author,
#  dir menu entry, description, category)
texinfo_documents = [
    (
        'index',
        'render_profile_viewer',
        u'render_profile_viewer Documentation',
        u"""Smart People""",
        'render_profile_viewer',
        """Tool for viewing render profile results""",
        'Miscellaneous'
    ),
]

# Example configuration for intersphinx: refer to the Python standard library.
intersphinx_mapping = {'http://docs.python.org/': None}

extlinks = {'jira': ('http://jira.anim.dreamworks.com/browse/%s', '')}


# Markdown Support

def setup(app):
    app.add_config_value(
        'recommonmark_config', {
            'enable_eval_rst': True,
        },
        True
    )
    app.add_transform(AutoStructify)
    # This adds wider margins
    app.add_stylesheet('large_width.css')

