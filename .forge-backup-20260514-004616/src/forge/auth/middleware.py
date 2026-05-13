"""API key authentication for Forge.

Simple but effective API key auth for production deployments.
Supports header-based and query-param-based keys.
"""

from __future__ import annotations

import os
from typing import Any

from forge.utils.logging import get_logger

logger = get_logger("forge.auth")


class APIKeyAuth:
    """API key authentication provider.

    Keys are loaded from FORGE_API_KEY environment variable.
    If no key is set, authentication is disabled (development mode).
    """

    def __init__(self) -> None:
        self._api_key = os.environ.get("FORGE_API_KEY", "")
        self._enabled = bool(self._api_key)

    def is_enabled(self) -> bool:
        """Check if authentication is enabled."""
        return self._enabled

    def validate(self, key: str | None) -> bool:
        """Validate an API key.

        Args:
            key: The API key to validate.

        Returns:
            True if valid or auth is disabled.
        """
        if not self._enabled:
            return True
        if not key:
            return False
        return key == self._api_key

    def get_auth_dependency(self) -> Any:
        """Get FastAPI dependency for authentication.

        Returns:
            FastAPI dependency function.
        """
        try:
            from fastapi import Header, HTTPException, status
        except ImportError:
            return None

        async def auth_dependency(x_api_key: str | None = Header(default=None)) -> str:
            if not self.validate(x_api_key):
                logger.warning("api_key_invalid", key_provided=bool(x_api_key))
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or missing API key",
                    headers={"WWW-Authenticate": "ApiKey"},
                )
            return x_api_key or ""

        return auth_dependency
