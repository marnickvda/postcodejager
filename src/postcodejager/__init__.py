"""Postcodejager — derive the version from package metadata (pyproject is the
single source of truth) so it never drifts."""
from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("postcodejager")
except PackageNotFoundError:  # running from source without an install
    __version__ = "0.0.0+unknown"
