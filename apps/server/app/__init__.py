"""Wooju local server: serves the Brain index and the app API."""

# The app's version; kept equal across pyproject, package.json and tauri.conf.json.
__version__ = "0.5.0"

try:  # written by scripts/build-mac.sh: the git commit the app was built from
    from ._build import BUILD
except ImportError:  # running from source
    BUILD = "dev"
