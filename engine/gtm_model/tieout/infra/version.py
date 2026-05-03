"""Single source of truth for Planning Tie-Out cache/model versioning.

Bump this when model logic changes to invalidate:
- Streamlit's @st.cache_data results
- Persisted baseline snapshots on disk
"""

CACHE_VERSION = "v5.0-reorg"
