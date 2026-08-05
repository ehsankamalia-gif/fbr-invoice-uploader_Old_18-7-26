from __future__ import annotations

from typing import Dict, Any


def feature_flags(request) -> Dict[str, Any]:
    try:
        from app.core.feature_flags import FeatureFlagManager

        enabled = FeatureFlagManager.is_enabled("init_progress_bar")
    except Exception:
        enabled = False

    return {"init_progress_bar_enabled": enabled}

