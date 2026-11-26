"""Forecast Tieout core: one calculation authority for plan against reality.

Typed records and pure functions. No dependency on ``engine.gtm_model``, no
network access and no wall-clock reads: every calculation takes its as-of date
as an argument.
"""
