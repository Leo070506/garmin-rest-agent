"""Portable skill entrypoint. The release bundle includes the engine beside this script."""
import sys
from pathlib import Path

# Source checkout fallback. A built skill imports its bundled sibling package first.
source = Path(__file__).resolve().parents[3] / "src"
if source.is_dir():
    sys.path.append(str(source))

from garmin_rest_agent.cli import main  # noqa: E402 - portable bundle/source bootstrap

raise SystemExit(main())
