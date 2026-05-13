"""Tests for resilience patterns."""

from __future__ import annotations

import pytest

from forge.resilience.circuit_breaker import CircuitBreaker, CircuitBreakerConfig, CircuitBreakerOpen, CircuitState
from forge.resilience.retry import RetryPolicy, exponential_backoff


class TestCircuitBreaker:
    """Test suite for circuit breaker."""

    @pytest.fixture
    def breaker(self):
        return CircuitBreaker(config=CircuitBreakerConfig(
            failure_threshold=3,
            recovery_timeout=1.0,
            half_open_max_calls=2,
            success_threshold=2,
        ))

    @pytest.mark.asyncio
    async def test_closed_allows_calls(self, breaker: CircuitBreaker) -> None:
        """Closed circuit allows calls through."""
        async def success_fn():
            return "ok"

        result = await breaker.call("agent-1", success_fn)
        assert result == "ok"
        assert breaker.get_state("agent-1") == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_opens_after_failures(self, breaker: CircuitBreaker) -> None:
        """Circuit opens after threshold failures."""
        async def fail_fn():
            raise ValueError("fail")

        for _ in range(3):
            with pytest.raises(ValueError):
                await breaker.call("agent-1", fail_fn)

        assert breaker.get_state("agent-1") == CircuitState.OPEN

        with pytest.raises(CircuitBreakerOpen):
            await breaker.call("agent-1", fail_fn)

    @pytest.mark.asyncio
    async def test_half_open_after_timeout(self, breaker: CircuitBreaker) -> None:
        """Circuit transitions to half-open after recovery timeout."""
        async def fail_fn():
            raise ValueError("fail")

        for _ in range(3):
            with pytest.raises(ValueError):
                await breaker.call("agent-1", fail_fn)

        assert breaker.get_state("agent-1") == CircuitState.OPEN

        import asyncio
        await asyncio.sleep(1.1)

        assert breaker.get_state("agent-1") == CircuitState.HALF_OPEN

    @pytest.mark.asyncio
    async def test_closes_after_successes(self, breaker: CircuitBreaker) -> None:
        """Circuit closes after success threshold in half-open."""
        async def fail_fn():
            raise ValueError("fail")

        async def success_fn():
            return "ok"

        for _ in range(3):
            with pytest.raises(ValueError):
                await breaker.call("agent-1", fail_fn)

        import asyncio
        await asyncio.sleep(1.1)

        assert breaker.get_state("agent-1") == CircuitState.HALF_OPEN

        for _ in range(2):
            result = await breaker.call("agent-1", success_fn)
            assert result == "ok"

        assert breaker.get_state("agent-1") == CircuitState.CLOSED

    def test_stats(self, breaker: CircuitBreaker) -> None:
        """Stats reflect current state."""
        stats = breaker.get_stats("unknown")
        assert stats["target"] == "unknown"
        assert stats["state"] == "closed"
        assert stats["failure_count"] == 0

    def test_reset(self, breaker: CircuitBreaker) -> None:
        """Reset clears all state."""
        breaker._states["agent-1"] = CircuitState.OPEN
        breaker._failure_counts["agent-1"] = 5
        breaker.reset("agent-1")
        assert breaker.get_state("agent-1") == CircuitState.CLOSED
        assert breaker._failure_counts.get("agent-1", 0) == 0


class TestRetryPolicy:
    """Test suite for retry policy."""

    @pytest.fixture
    def policy(self):
        return RetryPolicy(max_attempts=3, base_delay=0.1, max_delay=1.0)

    @pytest.mark.asyncio
    async def test_succeeds_first_try(self, policy: RetryPolicy) -> None:
        """No retry needed on success."""
        async def success():
            return "ok"

        result = await policy.execute(success)
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_retries_then_succeeds(self, policy: RetryPolicy) -> None:
        """Retries until success."""
        attempts = 0

        async def flaky():
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise ValueError("fail")
            return "ok"

        result = await policy.execute(flaky)
        assert result == "ok"
        assert attempts == 3

    @pytest.mark.asyncio
    async def test_exhausts_retries(self, policy: RetryPolicy) -> None:
        """Raises last exception after retries exhausted."""
        async def always_fail():
            raise ValueError("fail")

        with pytest.raises(ValueError, match="fail"):
            await policy.execute(always_fail)

    def test_exponential_backoff(self) -> None:
        """Backoff increases exponentially."""
        d0 = exponential_backoff(0, base_delay=1.0, max_delay=100.0, jitter=False)
        d1 = exponential_backoff(1, base_delay=1.0, max_delay=100.0, jitter=False)
        d2 = exponential_backoff(2, base_delay=1.0, max_delay=100.0, jitter=False)

        assert d0 == 1.0
        assert d1 == 2.0
        assert d2 == 4.0

    def test_backoff_with_jitter(self) -> None:
        """Jitter adds randomness."""
        d = exponential_backoff(1, base_delay=1.0, max_delay=100.0, jitter=True)
        assert 0.5 <= d <= 2.0

    def test_backoff_max_cap(self) -> None:
        """Backoff respects max delay."""
        d = exponential_backoff(10, base_delay=1.0, max_delay=10.0, jitter=False)
        assert d == 10.0


class TestPersistence:
    """Test suite for workflow persistence."""

    @pytest.fixture
    def store(self, tmp_path):
        from forge.persistence.store import WorkflowStore
        return WorkflowStore(snapshot_dir=tmp_path / "snapshots")

    def test_save_and_load(self, store) -> None:
        """Roundtrip workflow snapshot."""
        from forge.core.orchestrator import Workflow, WorkflowStatus
        from forge.protocols.agent import AgentStatus

        wf = Workflow(workflow_id="wf-1", spec_id="SPEC-1")
        wf.status = WorkflowStatus.RUNNING
        wf.steps["s1"] = type("StepExec", (), {
            "status": AgentStatus.COMPLETED,
            "result": type("Result", (), {"output": {"key": "value"}})(),
            "start_time": 0.0,
            "end_time": 1.0,
            "retry_count": 0,
            "checkpoint_id": None,
        })()

        path = store.save(wf)
        assert path.exists()

        loaded = store.load("wf-1")
        assert loaded is not None
        assert loaded.workflow_id == "wf-1"
        assert loaded.spec_id == "SPEC-1"
        assert loaded.status == "running"

    def test_load_missing(self, store) -> None:
        """Load missing workflow returns None."""
        result = store.load("nonexistent")
        assert result is None

    def test_list_snapshots(self, store) -> None:
        """List saved snapshots."""
        from forge.core.orchestrator import Workflow

        wf1 = Workflow(workflow_id="wf-1", spec_id="SPEC-1")
        wf2 = Workflow(workflow_id="wf-2", spec_id="SPEC-2")
        store.save(wf1)
        store.save(wf2)

        ids = store.list_snapshots()
        assert "wf-1" in ids
        assert "wf-2" in ids

    def test_delete(self, store) -> None:
        """Delete snapshot."""
        from forge.core.orchestrator import Workflow

        wf = Workflow(workflow_id="wf-1", spec_id="SPEC-1")
        store.save(wf)
        assert store.delete("wf-1") is True
        assert store.load("wf-1") is None
        assert store.delete("wf-1") is False
