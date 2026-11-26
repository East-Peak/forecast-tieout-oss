"""Test-only: pin ``date.today()`` inside subprocesses of the old engine.

The old engine (``engine/gtm_model``) reads the wall clock in several places and
ignores ``--as-of`` there (rebuild design doc, audit item 1), so its narrative
tests aged out as the calendar moved on. Those tests pass ``--as-of``; they put
this directory on the subprocess ``PYTHONPATH`` and set
``GTM_TIEOUT_PINNED_TODAY`` to that same date, so the harness means what it
says. Nothing outside these tests loads it. Retired with the old engine.
"""

import datetime
import os
import runpy
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))

# Keep any interpreter-provided sitecustomize (Homebrew ships one) working.
for _entry in sys.path:
    _candidate = os.path.join(os.path.abspath(_entry or os.getcwd()), "sitecustomize.py")
    if os.path.dirname(_candidate) != _HERE and os.path.exists(_candidate):
        runpy.run_path(_candidate)
        break

_PINNED = os.environ.get("GTM_TIEOUT_PINNED_TODAY")
if _PINNED:
    _FIXED = datetime.date.fromisoformat(_PINNED)

    class _PinnedDate(datetime.date):
        @classmethod
        def today(cls):
            return cls(_FIXED.year, _FIXED.month, _FIXED.day)

    datetime.date = _PinnedDate
