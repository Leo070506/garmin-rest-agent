"""Keep Chinese CLI output readable when Windows redirects to a legacy code page."""
import sys


def ensure_utf8_console():
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="backslashreplace")
