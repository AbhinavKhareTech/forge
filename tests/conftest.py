"""Pytest configuration with fixtures for production testing.

Provides database, Redis, and telemetry fixtures with proper cleanup.
"""

from __future__ import annotations

import asyncio
from typing import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from forge.config import ForgeSettings, reload_settings
from forge.core.orchestrator import Base, Orchestrator
from forge.telemetry import configure_structlog, shutdown_telemetry


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session", autouse=True)
def setup_logging() -> None:
    """Configure structured logging for tests."""
    configure_structlog()


@pytest.fixture(scope="function")
def test_settings(monkeypatch) -> ForgeSettings:
    """Provide test-specific settings with safe defaults."""
    monkeypatch.setenv("FORGE_ENVIRONMENT", "test")
    monkeypatch.setenv("FORGE_DEBUG", "false")
    monkeypatch.setenv("FORGE_DATABASE_BACKEND", "sqlite")
    monkeypatch.setenv("FORGE_DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("FORGE_REDIS_URL", "redis://localhost:6379/15")  # Test DB
    monkeypatch.setenv("FORGE_JWT_SECRET", "test-secret-key-at-least-32-characters-long")
    monkeypatch.setenv("FORGE_API_KEY", "test-api-key")
    monkeypatch.setenv("FORGE_ENCRYPTION_KEY", "test-encryption-key-32-bytes!")
    monkeypatch.setenv("FORGE_TRIDENT_MODE", "disabled")
    monkeypatch.setenv("FORGE_SENTRY_DSN", "")
    monkeypatch.setenv("FORGE_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("FORGE_RATE_LIMIT_REQUESTS", "10000")

    return reload_settings()


@pytest_asyncio.fixture(scope="function")
async def db_engine(test_settings):
    """Provide an async database engine for tests."""
    engine = create_async_engine(
        test_settings.database_url.get_secret_value(),
        echo=False,
        future=True,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    """Provide a database session for tests."""
    async_session = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session


@pytest_asyncio.fixture(scope="function")
async def orchestrator(test_settings, db_engine) -> AsyncGenerator[Orchestrator, None]:
    """Provide an orchestrator instance for tests."""
    orch = Orchestrator(test_settings)
    yield orch


@pytest.fixture(scope="function")
def mock_trident_response() -> dict:
    """Provide a mock Trident response for testing."""
    return {
        "decision": "ALLOW",
        "confidence": 0.95,
        "reason": "Mock Trident evaluation passed",
        "rule_id": "TRIDENT-MOCK-001",
    }


@pytest.fixture(scope="function")
def sample_spec() -> str:
    """Provide a sample spec for testing."""
    return """
---
id: SPEC-TEST-001
title: Test Authentication
description: Test spec for validation
constitution_refs:
  - security
---

#### STEP: plan-auth
**Type:** plan
**Agent:** planner
**Depends:** []

Design the authentication flow.

#### STEP: code-auth
**Type:** code
**Agent:** coder
**Depends:** [plan-auth]

Implement the auth service.
"""


@pytest.fixture(scope="function")
def sample_governance_context() -> dict:
    """Provide a sample governance context for testing."""
    return {
        "spec_id": "SPEC-TEST-001",
        "agent_id": "agent-001",
        "agent_type": "coder",
        "action": "execute_step",
        "resource": "code-auth",
    }


def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line("markers", "slow: marks tests as slow")
    config.addinivalue_line("markers", "integration: marks tests as integration tests")
    config.addinivalue_line("markers", "e2e: marks tests as end-to-end tests")
    config.addinivalue_line("markers", "chaos: marks tests as chaos engineering tests")
    config.addinivalue_line("markers", "security: marks tests as security tests")
