"""Compatibility facade for clone-bot user callbacks.

Public import path is intentionally preserved while implementation is migrated
feature-by-feature into ``handlers.clone.user_features``.
"""

from handlers.clone.user_features.legacy_callbacks import CloneUserCallbacksMixin

__all__ = ["CloneUserCallbacksMixin"]
