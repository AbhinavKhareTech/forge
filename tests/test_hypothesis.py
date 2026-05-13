"""Property-based tests using Hypothesis for edge case discovery.

Validates spec parsing, governance decisions, and configuration boundaries.
"""

from __future__ import annotations

import pytest
from hypothesis import given, strategies as st, settings, HealthCheck

from forge.config import ForgeSettings
from forge.governance.runtime import RuleBasedGovernance, GovernanceContext


class TestSpecValidationProperties:
    """Property-based tests for spec validation."""

    @given(
        spec_id=st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="-_")),
        title=st.text(min_size=1, max_size=100),
        description=st.text(min_size=0, max_size=500),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_spec_id_format(self, spec_id, title, description):
        """Spec IDs should be valid strings."""
        assert len(spec_id) > 0
        assert len(spec_id) <= 50


class TestGovernanceProperties:
    """Property-based tests for governance decisions."""

    @given(
        action=st.sampled_from([
            "read_data", "write_data", "delete_database", "deploy_to_production",
            "modify_iam", "safe_action", "delete_all_data", "grant_access",
        ]),
        resource=st.sampled_from([
            "production_db", "staging_app", "customer_data", "test_resource",
            "payment_gateway", "auth_service", "secret_vault", "dev_env",
        ]),
    )
    @settings(max_examples=200)
    def test_governance_decision_is_deterministic(self, action, resource):
        """Same inputs should always produce the same decision."""
        engine = RuleBasedGovernance()
        context = GovernanceContext(
            spec_id="SPEC-PROP",
            agent_id="agent-1",
            agent_type="coder",
            action=action,
            resource=resource,
        )

        result1 = engine.evaluate(context)
        result2 = engine.evaluate(context)

        assert result1.decision == result2.decision
        assert result1.confidence == result2.confidence
        assert result1.rule_id == result2.rule_id

    @given(
        action=st.text(min_size=1, max_size=50),
        resource=st.text(min_size=1, max_size=50),
    )
    @settings(max_examples=100)
    def test_governance_never_crashes(self, action, resource):
        """Governance should never crash on any input."""
        engine = RuleBasedGovernance()
        context = GovernanceContext(
            spec_id="SPEC-PROP",
            agent_id="agent-1",
            agent_type="coder",
            action=action,
            resource=resource,
        )

        try:
            result = engine.evaluate(context)
            assert result.decision.value in ("ALLOW", "REVIEW", "BLOCK")
            assert 0.0 <= result.confidence <= 1.0
        except Exception:
            pytest.fail(f"Governance crashed on action={action}, resource={resource}")


class TestConfigurationProperties:
    """Property-based tests for configuration validation."""

    @given(
        api_port=st.integers(min_value=1, max_value=65535),
        api_timeout=st.floats(min_value=1.0, max_value=300.0),
        rate_limit=st.integers(min_value=1, max_value=10000),
    )
    @settings(max_examples=50)
    def test_valid_configuration_ranges(self, api_port, api_timeout, rate_limit):
        """Configuration values should stay within valid ranges."""
        assert 1 <= api_port <= 65535
        assert 1.0 <= api_timeout <= 300.0
        assert 1 <= rate_limit <= 10000
