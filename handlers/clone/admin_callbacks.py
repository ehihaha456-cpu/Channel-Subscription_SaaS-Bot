"""Compatibility facade for clone-bot admin callbacks.

Public import path is intentionally preserved while implementation is migrated
feature-by-feature into ``handlers.clone.admin_features``.
"""

from handlers.clone.admin_features.legacy_callbacks import CloneAdminCallbacksMixin

__all__ = ["CloneAdminCallbacksMixin"]
