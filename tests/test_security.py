"""Security tests for Forge.

Validates secrets handling, input sanitization, and access control.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from forge.auth.middleware import (
    create_access_token,
    verify_password,
    hash_password,
    get_current_user,
    ForgeUser,
    Role,
    Permission,
    require_permissions,
    require_role,
)
from forge.config import ForgeSettings, reload_settings


class TestPasswordSecurity:
    """Test password hashing and verification."""

    def test_password_hashing(self):
        """Passwords should be properly hashed and verifiable."""
        password = "my_secure_password_123"
        hashed = hash_password(password)
        assert hashed != password
        assert verify_password(password, hashed) is True
        assert verify_password("wrong_password", hashed) is False

    def test_different_passwords_different_hashes(self):
        """Different passwords should produce different hashes."""
        hash1 = hash_password("password1")
        hash2 = hash_password("password2")
        assert hash1 != hash2


class TestJWTSecurity:
    """Test JWT token creation and validation."""

    def test_token_creation_and_validation(self, monkeypatch):
        """Tokens should be creatable and validatable."""
        monkeypatch.setenv("FORGE_JWT_SECRET", "test-secret-key-at-least-32-characters-long")
        monkeypatch.setenv("FORGE_ENVIRONMENT", "test")
        reload_settings()

        token = create_access_token("user-1", "testuser", Role.OPERATOR)
        assert token is not None
        assert isinstance(token, str)

    def test_token_contains_expected_claims(self, monkeypatch):
        """Tokens should contain user ID, username, and role."""
        import jwt as pyjwt

        monkeypatch.setenv("FORGE_JWT_SECRET", "test-secret-key-at-least-32-characters-long")
        monkeypatch.setenv("FORGE_ENVIRONMENT", "test")
        settings = reload_settings()

        token = create_access_token("user-1", "testuser", Role.ADMIN)
        payload = pyjwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
        )

        assert payload["sub"] == "user-1"
        assert payload["username"] == "testuser"
        assert payload["role"] == "admin"
        assert payload["type"] == "access"


class TestRBAC:
    """Test role-based access control."""

    def test_admin_has_all_permissions(self):
        """Admin role should have all permissions."""
        user = ForgeUser("user-1", "admin", Role.ADMIN)
        assert user.has_permission(Permission.ADMIN_ACCESS)
        assert user.has_permission(Permission.SPEC_EXECUTE)
        assert user.has_permission(Permission.GOVERNANCE_OVERRIDE)

    def test_viewer_limited_permissions(self):
        """Viewer should only have read permissions."""
        user = ForgeUser("user-1", "viewer", Role.VIEWER)
        assert user.has_permission(Permission.SPEC_READ)
        assert not user.has_permission(Permission.SPEC_EXECUTE)
        assert not user.has_permission(Permission.ADMIN_ACCESS)

    def test_agent_service_permissions(self):
        """Agent role should have execution permissions."""
        user = ForgeUser("service", "service", Role.AGENT)
        assert user.has_permission(Permission.SPEC_EXECUTE)
        assert user.has_permission(Permission.AGENT_EXECUTE)
        assert not user.has_permission(Permission.ADMIN_ACCESS)


class TestInputValidation:
    """Test input validation and sanitization."""

    def test_settings_rejects_weak_jwt_in_production(self, monkeypatch):
        """Production should reject weak JWT secrets."""
        monkeypatch.setenv("FORGE_ENVIRONMENT", "production")
        monkeypatch.setenv("FORGE_JWT_SECRET", "short")
        monkeypatch.setenv("FORGE_DATABASE_BACKEND", "postgresql")
        monkeypatch.setenv("FORGE_DATABASE_URL", "postgresql+asyncpg://user:pass@localhost/db")
        monkeypatch.setenv("FORGE_REDIS_URL", "redis://localhost:6379/0")
        monkeypatch.setenv("FORGE_SENTRY_DSN", "https://example.com/1")
        monkeypatch.setenv("FORGE_ENCRYPTION_KEY", "test-encryption-key-32-bytes!")

        with pytest.raises(ValueError, match="at least 32 characters"):
            ForgeSettings()

    def test_settings_rejects_sqlite_in_production(self, monkeypatch):
        """Production should reject SQLite."""
        monkeypatch.setenv("FORGE_ENVIRONMENT", "production")
        monkeypatch.setenv("FORGE_JWT_SECRET", "test-secret-key-at-least-32-characters-long")
        monkeypatch.setenv("FORGE_DATABASE_BACKEND", "sqlite")
        monkeypatch.setenv("FORGE_REDIS_URL", "redis://localhost:6379/0")
        monkeypatch.setenv("FORGE_SENTRY_DSN", "https://example.com/1")
        monkeypatch.setenv("FORGE_ENCRYPTION_KEY", "test-encryption-key-32-bytes!")

        with pytest.raises(ValueError, match="SQLite is not allowed"):
            ForgeSettings()

    def test_settings_rejects_debug_in_production(self, monkeypatch):
        """Production should reject debug mode."""
        monkeypatch.setenv("FORGE_ENVIRONMENT", "production")
        monkeypatch.setenv("FORGE_DEBUG", "true")
        monkeypatch.setenv("FORGE_JWT_SECRET", "test-secret-key-at-least-32-characters-long")
        monkeypatch.setenv("FORGE_DATABASE_BACKEND", "postgresql")
        monkeypatch.setenv("FORGE_DATABASE_URL", "postgresql+asyncpg://user:pass@localhost/db")
        monkeypatch.setenv("FORGE_REDIS_URL", "redis://localhost:6379/0")
        monkeypatch.setenv("FORGE_SENTRY_DSN", "https://example.com/1")
        monkeypatch.setenv("FORGE_ENCRYPTION_KEY", "test-encryption-key-32-bytes!")

        with pytest.raises(ValueError, match="must be False"):
            ForgeSettings()
