# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

import os

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = "PR_2024_4"
copyright = "2024, IDEA - Narodowe Centrum Badań Jądrowych"
author = "IDEA - Narodowe Centrum Badań Jądrowych"
release = "0.0.1"

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = ["autoapi.extension"]
pages_root = os.environ.get("pages_root", "")
templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]
autoapi_dirs = ["../datafusion"]
autoapi_exclude = ["pydantic", "env"]
autoapi_ignore = ["*/alembic/*", "**/alembic/**"]


# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = "sphinx_book_theme"
html_static_path = ["_static"]

autoapi_options = [
    "exclude-private",
    "undoc-members",
    "special-members",
    "members",
]
