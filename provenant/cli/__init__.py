"""provenant CLI package.

Entry point: ``provenant`` command (defined in provenant.cli.main).
Codebase intelligence for developers and AI - dependency graphs,
git signals, dead code detection, architectural decisions, and
AI-generated documentation.
"""

from importlib.metadata import version as _version, PackageNotFoundError as _PackageNotFoundError

try:
    __version__ = _version("provenant")
except _PackageNotFoundError:
    __version__ = "0.0.0"
