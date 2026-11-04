"""rutrackarr — Torznab indexer for RuTracker with language-aware ranking."""

import os

# Release images set RUTRACKARR_VERSION from the git tag at build time.
__version__ = os.environ.get("RUTRACKARR_VERSION") or "0.0.0-dev"
