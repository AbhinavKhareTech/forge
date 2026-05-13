"""Production-grade authentication and authorization middleware.

Implements JWT-based authentication with role-based access control (RBAC),
API key validation, and secure token handling.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum
from functools import wraps
from typing import Any, Callable

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext

from forge.config import get_settings
from forge.telemetry import get_logger

logger = get_logger("forge.auth")

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Security scheme
security = HTTPBearer(auto_error=False)


class Role(str, Enum):
    """User roles with hierarchical permissions."""

    ADMIN = "admin"           # Full access
    OPERATOR = "operator"     # Can execute specs, review governance decisions
    VIEWER = "viewer"         # Read-only access
    AGENT = "agent"           # Service-to-service authentication


class Permission(str, Enum):
    """Granular permissions for RBAC."""

    SPEC_READ = "spec:read"
    SPEC_WRITE = "spec:write"
    SPEC_EXECUTE = "spec:execute"
    SPEC_DELETE = "spec:delete"
    AGENT_READ = "agent:read"
    AGENT_EXECUTE = "agent:execute"
    GOVERNANCE_READ = "governance:read"
    GOVERNANCE_OVERRIDE = "governance:override"
    MEMORY_READ = "memory:read"
    MEMORY_WRITE = "memory:write"
    ADMIN_ACCESS = "admin:access"
    AUDIT_READ = "audit:read"


# Role-to-permissions mapping
ROLE_PERMISSIONS: dict[Role, set[Permission]] = {
    Role.ADMIN: set(Permission),
    Role.OPERATOR: {
        Permission.SPEC_READ,
        Permission.SPEC_WRITE,
        Permission.SPEC_EXECUTE,
        Permission.AGENT_READ,
        Permission.AGENT_EXECUTE,
        Permission.GOVERNANCE_READ,
        Permission.GOVERNANCE_OVERRIDE,
        Permission.MEMORY_READ,
        Permission.MEMORY_WRITE,
    },
    Role.VIEWER: {
        Permission.SPEC_READ,
        Permission.AGENT_READ,
        Permission.GOVERNANCE_READ,
        Permission.MEMORY_READ,
        Permission.AUDIT_READ,
    },
    Role.AGENT: {
        Permission.SPEC_READ,
        Permission.SPEC_EXECUTE,
        Permission.AGENT_EXECUTE,
        Permission.MEMORY_READ,
        Permission.MEMORY_WRITE,
    },
}


class ForgeUser:
    """Authenticated user with role and permissions."""

    def __init__(
        self,
        user_id: str,
        username: str,
        role: Role,
        permissions: set[Permission] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.user_id = user_id
        self.username = username
        self.role = role
        self.permissions = permissions or ROLE_PERMISSIONS.get(role, set())
        self.metadata = metadata or {}

    def has_permission(self, permission: Permission) -> bool:
        """Check if user has a specific permission."""
        return permission in self.permissions

    def has_any_permission(self, permissions: set[Permission]) -> bool:
        """Check if user has any of the given permissions."""
        return bool(self.permissions & permissions)

    def has_all_permissions(self, permissions: set[Permission]) -> bool:
        """Check if user has all of the given permissions."""
        return permissions.issubset(self.permissions)


def create_access_token(
    user_id: str,
    username: str,
    role: Role,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a JWT access token for a user."""
    settings = get_settings()
    jwt_secret = settings.jwt_secret.get_secret_value()

    if settings.environment.value == "production" and len(jwt_secret) < 32:
        raise ValueError("JWT secret must be at least 32 characters in production")

    to_encode = {
        "sub": user_id,
        "username": username,
        "role": role.value,
        "iat": datetime.now(timezone.utc),
        "type": "access",
    }

    if expires_delta:
        to_encode["exp"] = datetime.now(timezone.utc) + expires_delta
    else:
        to_encode["exp"] = datetime.now(timezone.utc) + timedelta(
            minutes=settings.jwt_expiration_minutes
        )

    return jwt.encode(to_encode, jwt_secret, algorithm=settings.jwt_algorithm)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)


def hash_password(password: str) -> str:
    """Hash a password for storage."""
    return pwd_context.hash(password)


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> ForgeUser:
    """Dependency: authenticate and return the current user from JWT or API key.

    Supports both Bearer token (JWT) and X-API-Key header authentication.
    """
    settings = get_settings()

    # Try API key first
    api_key_header = request.headers.get("X-API-Key")
    if api_key_header:
        expected_key = settings.api_key.get_secret_value()
        if expected_key and api_key_header == expected_key:
            return ForgeUser(
                user_id="service",
                username="service_account",
                role=Role.AGENT,
            )
        logger.warning(
            "invalid_api_key_attempt",
            client_ip=request.client.host if request.client else None,
            path=request.url.path,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Fall back to JWT
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    jwt_secret = settings.jwt_secret.get_secret_value()

    try:
        payload = jwt.decode(
            token,
            jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
        user_id: str = payload.get("sub")
        username: str = payload.get("username", "")
        role_str: str = payload.get("role", "viewer")

        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing subject",
            )

        role = Role(role_str)

        logger.info(
            "user_authenticated",
            user_id=user_id,
            username=username,
            role=role.value,
            path=request.url.path,
        )

        return ForgeUser(
            user_id=user_id,
            username=username,
            role=role,
        )

    except JWTError as exc:
        logger.warning(
            "jwt_validation_failed",
            error=str(exc),
            client_ip=request.client.host if request.client else None,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def require_permissions(required_permissions: set[Permission]):
    """Decorator/dependency factory to require specific permissions.

    Usage:
        @app.get("/specs")
        async def list_specs(user: ForgeUser = Depends(require_permissions({Permission.SPEC_READ}))):
            ...
    """
    def dependency(user: ForgeUser = Depends(get_current_user)) -> ForgeUser:
        if not user.has_all_permissions(required_permissions):
            logger.warning(
                "permission_denied",
                user_id=user.user_id,
                role=user.role.value,
                required=[p.value for p in required_permissions],
                granted=[p.value for p in user.permissions],
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required: {[p.value for p in required_permissions]}",
            )
        return user
    return dependency


def require_role(required_role: Role):
    """Decorator/dependency factory to require a minimum role level.

    Usage:
        @app.delete("/specs/{spec_id}")
        async def delete_spec(user: ForgeUser = Depends(require_role(Role.ADMIN))):
            ...
    """
    def dependency(user: ForgeUser = Depends(get_current_user)) -> ForgeUser:
        role_hierarchy = [Role.VIEWER, Role.OPERATOR, Role.ADMIN]
        user_level = role_hierarchy.index(user.role)
        required_level = role_hierarchy.index(required_role)

        if user_level < required_level:
            logger.warning(
                "role_insufficient",
                user_id=user.user_id,
                user_role=user.role.value,
                required_role=required_role.value,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{required_role.value}' or higher required",
            )
        return user
    return dependency


class AuthMiddleware:
    """FastAPI middleware for authentication and request logging.

    Attaches the current user to the request state for downstream use.
    """

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)

        # Attempt authentication (non-blocking for public endpoints)
        try:
            credentials = await security(request)
            if credentials:
                user = await get_current_user(request, credentials)
                request.state.user = user
        except HTTPException:
            request.state.user = None

        await self.app(scope, receive, send)
