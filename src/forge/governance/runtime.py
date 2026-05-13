"""Production-hardened governance runtime with immutable audit logging.

Enforces ALLOW/REVIEW/BLOCK decisions with full audit trail, structured logging,
and graceful fallback when BGI Trident is unavailable.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from forge.config import ForgeSettings, get_settings
from forge.telemetry import get_logger, get_meter, get_tracer, trace_span
from forge.telemetry.logging import get_correlation_id

logger = get_logger("forge.governance")


class GovernanceDecision(str, Enum):
    """Governance decision outcomes."""

    ALLOW = "ALLOW"
    REVIEW = "REVIEW"
    BLOCK = "BLOCK"
    ERROR = "ERROR"


class GovernanceSeverity(str, Enum):
    """Severity levels for governance events."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass(frozen=True)
class GovernanceContext:
    """Immutable context for a governance decision."""

    spec_id: str
    agent_id: str
    agent_type: str
    action: str
    resource: str
    correlation_id: str = field(default_factory=get_correlation_id)
    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    trace_id: str = ""
    span_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "spec_id": self.spec_id,
            "agent_id": self.agent_id,
            "agent_type": self.agent_type,
            "action": self.action,
            "resource": self.resource,
            "correlation_id": self.correlation_id,
            "timestamp": self.timestamp,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
        }


@dataclass(frozen=True)
class GovernanceResult:
    """Immutable result of a governance decision."""

    decision: GovernanceDecision
    confidence: float
    reason: str
    context: GovernanceContext
    rule_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision.value,
            "confidence": self.confidence,
            "reason": self.reason,
            "rule_id": self.rule_id,
            "context": self.context.to_dict(),
            "metadata": self.metadata,
        }


class AuditLogger:
    """Immutable, append-only audit logger for governance decisions.

    Writes to both structured logs and a dedicated audit log file.
    The audit log file should be mounted on an append-only filesystem
    or forwarded to an immutable log store (e.g., AWS CloudTrail, Splunk).
    """

    def __init__(self, settings: ForgeSettings | None = None) -> None:
        self._settings = settings or get_settings()
        self._audit_path = Path(self._settings.governance_audit_log_path)
        self._ensure_audit_directory()

    def _ensure_audit_directory(self) -> None:
        """Ensure the audit log directory exists."""
        try:
            self._audit_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.error(
                "audit_directory_creation_failed",
                path=str(self._audit_path.parent),
                error=str(exc),
            )

    def _compute_hash(self, entry: dict[str, Any]) -> str:
        """Compute SHA-256 hash of audit entry for tamper detection."""
        canonical = json.dumps(entry, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def log(self, result: GovernanceResult) -> None:
        """Log an immutable audit entry for a governance decision.

        This method is designed to be tamper-evident. Each entry includes
        a hash of its contents. In production, the audit log should be
        forwarded to an immutable external store.
        """
        entry = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.%fZ", time.gmtime()),
            "event_type": "governance_decision",
            "decision": result.decision.value,
            "confidence": result.confidence,
            "reason": result.reason,
            "rule_id": result.rule_id,
            "context": result.context.to_dict(),
            "metadata": result.metadata,
        }
        entry["entry_hash"] = self._compute_hash(entry)

        # Structured logging (always)
        logger.info(
            "governance_decision",
            decision=result.decision.value,
            spec_id=result.context.spec_id,
            agent_id=result.context.agent_id,
            action=result.context.action,
            resource=result.context.resource,
            confidence=result.confidence,
            reason=result.reason,
            rule_id=result.rule_id,
            correlation_id=result.context.correlation_id,
        )

        # Dedicated audit log file
        try:
            with open(self._audit_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
                f.flush()
        except OSError as exc:
            logger.critical(
                "audit_log_write_failed",
                path=str(self._audit_path),
                error=str(exc),
                entry=entry,
            )
            # In production, this should trigger an alert
            raise RuntimeError(f"Failed to write audit log: {exc}") from exc


class RuleBasedGovernance:
    """Fallback rule-based governance engine when BGI Trident is unavailable.

    Provides deterministic, auditable policy enforcement based on
    configurable rules with pattern matching.
    """

    # Critical actions that always require human review
    CRITICAL_ACTIONS = {
        "delete_database",
        "drop_table",
        "delete_production_resource",
        "modify_iam_policy",
        "grant_admin_access",
        "deploy_to_production",
    }

    # Actions that are always blocked
    BLOCKED_ACTIONS = {
        "delete_all_data",
        "wipe_storage",
        "disable_security_controls",
        "exfiltrate_data",
    }

    # Resource patterns that trigger elevated scrutiny
    SENSITIVE_RESOURCES = {
        "production",
        "customer_data",
        "payment",
        "auth",
        "secret",
        "credential",
    }

    def evaluate(self, context: GovernanceContext) -> GovernanceResult:
        """Evaluate a governance request against rule-based policies."""
        action_lower = context.action.lower()
        resource_lower = context.resource.lower()

        # Check blocked actions first (highest priority)
        if any(blocked in action_lower for blocked in self.BLOCKED_ACTIONS):
            return GovernanceResult(
                decision=GovernanceDecision.BLOCK,
                confidence=1.0,
                reason=f"Action '{context.action}' is permanently blocked by policy",
                context=context,
                rule_id="RULE-BLOCK-001",
                metadata={"policy_type": "hard_block", "matched_action": action_lower},
            )

        # Check critical actions
        if any(critical in action_lower for critical in self.CRITICAL_ACTIONS):
            is_sensitive = any(
                sensitive in resource_lower for sensitive in self.SENSITIVE_RESOURCES
            )
            if is_sensitive:
                return GovernanceResult(
                    decision=GovernanceDecision.BLOCK,
                    confidence=0.95,
                    reason=f"Critical action on sensitive resource requires explicit approval",
                    context=context,
                    rule_id="RULE-CRIT-001",
                    metadata={"policy_type": "critical_sensitive", "matched_resource": resource_lower},
                )
            return GovernanceResult(
                decision=GovernanceDecision.REVIEW,
                confidence=0.85,
                reason=f"Critical action '{context.action}' requires human review",
                context=context,
                rule_id="RULE-CRIT-002",
                metadata={"policy_type": "critical_review"},
            )

        # Check sensitive resources
        if any(sensitive in resource_lower for sensitive in self.SENSITIVE_RESOURCES):
            return GovernanceResult(
                decision=GovernanceDecision.REVIEW,
                confidence=0.75,
                reason=f"Action on sensitive resource '{context.resource}' requires review",
                context=context,
                rule_id="RULE-SENS-001",
                metadata={"policy_type": "sensitive_resource"},
            )

        # Default: allow with logging
        return GovernanceResult(
            decision=GovernanceDecision.ALLOW,
            confidence=0.99,
            reason="Action passes all rule-based policies",
            context=context,
            rule_id="RULE-DEFAULT-001",
            metadata={"policy_type": "default_allow"},
        )


class GovernanceRuntime:
    """Production governance runtime with BGI Trident integration and fallback.

    Evaluates agent actions against policies using BGI Trident when available,
    with automatic fallback to rule-based governance. All decisions are
    logged to an immutable audit trail.
    """

    def __init__(self, settings: ForgeSettings | None = None) -> None:
        self._settings = settings or get_settings()
        self._audit_logger = AuditLogger(self._settings)
        self._fallback_engine = RuleBasedGovernance()
        self._meter = get_meter()
        self._tracer = get_tracer()
        self._trident_available: bool | None = None

    async def evaluate(
        self,
        spec_id: str,
        agent_id: str,
        agent_type: str,
        action: str,
        resource: str,
        extra_context: dict[str, Any] | None = None,
    ) -> GovernanceResult:
        """Evaluate an agent action and return a governance decision.

        This is the primary entry point for all governance decisions.
        It attempts BGI Trident first, falls back to rules, and always
        logs the result to the audit trail.
        """
        context = GovernanceContext(
            spec_id=spec_id,
            agent_id=agent_id,
            agent_type=agent_type,
            action=action,
            resource=resource,
        )

        with trace_span(
            "governance.evaluate",
            attributes={
                "spec_id": spec_id,
                "agent_id": agent_id,
                "action": action,
                "resource": resource,
            },
        ) as span:
            span.set_attribute("governance.mode", self._settings.trident_mode.value)

            # Attempt BGI Trident if enabled and available
            if self._settings.trident_mode.value in ("enabled", "fallback_rules"):
                try:
                    result = await self._evaluate_with_trident(context, extra_context)
                    if result.decision != GovernanceDecision.ERROR:
                        self._audit_logger.log(result)
                        self._meter.record_governance_decision(
                            result.decision.value, spec_id, agent_id,
                        )
                        span.set_attribute("governance.decision", result.decision.value)
                        span.set_attribute("governance.confidence", result.confidence)
                        return result
                except Exception as exc:
                    logger.warning(
                        "trident_evaluation_failed",
                        error=str(exc),
                        spec_id=spec_id,
                        agent_id=agent_id,
                    )
                    span.set_attribute("governance.trident_error", str(exc))

                    if self._settings.trident_mode.value == "enabled":
                        # In strict mode, fail closed
                        result = GovernanceResult(
                            decision=GovernanceDecision.BLOCK,
                            confidence=1.0,
                            reason=f"Trident evaluation failed and strict mode is enabled: {exc}",
                            context=context,
                            rule_id="RULE-FAIL-CLOSED",
                            metadata={"error": str(exc), "fail_closed": True},
                        )
                        self._audit_logger.log(result)
                        self._meter.record_governance_decision(
                            result.decision.value, spec_id, agent_id,
                        )
                        return result

            # Fallback to rule-based governance
            result = self._fallback_engine.evaluate(context)
            result = GovernanceResult(
                decision=result.decision,
                confidence=result.confidence * 0.9,  # Slightly lower confidence for fallback
                reason=f"[FALLBACK] {result.reason}",
                context=context,
                rule_id=result.rule_id,
                metadata={**result.metadata, "trident_fallback": True},
            )

            self._audit_logger.log(result)
            self._meter.record_governance_decision(
                result.decision.value, spec_id, agent_id,
            )
            span.set_attribute("governance.decision", result.decision.value)
            span.set_attribute("governance.confidence", result.confidence)
            span.set_attribute("governance.fallback", True)

            return result

    async def _evaluate_with_trident(
        self,
        context: GovernanceContext,
        extra_context: dict[str, Any] | None,
    ) -> GovernanceResult:
        """Evaluate using BGI Trident graph-native scoring.

        This is a placeholder for the actual Trident integration.
        In production, this would call the Trident service with
        the agent relationship graph and behavior features.
        """
        import httpx

        trident_url = self._settings.trident_url.get_secret_value()
        payload = {
            "context": context.to_dict(),
            "extra": extra_context or {},
            "graph_features": {},  # Would be populated by graph_builder
        }

        async with httpx.AsyncClient(timeout=self._settings.trident_timeout) as client:
            response = await client.post(
                f"{trident_url}/evaluate",
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()
            data = response.json()

            decision = GovernanceDecision(data.get("decision", "REVIEW"))
            return GovernanceResult(
                decision=decision,
                confidence=data.get("confidence", 0.5),
                reason=data.get("reason", "Trident evaluation"),
                context=context,
                rule_id=data.get("rule_id", "TRIDENT-001"),
                metadata={"trident_response": data},
            )

    async def batch_evaluate(
        self,
        requests: list[dict[str, Any]],
    ) -> list[GovernanceResult]:
        """Evaluate multiple governance requests efficiently.

        Useful for bulk operations or pre-flight checks.
        """
        results = []
        for req in requests:
            result = await self.evaluate(
                spec_id=req["spec_id"],
                agent_id=req["agent_id"],
                agent_type=req["agent_type"],
                action=req["action"],
                resource=req["resource"],
                extra_context=req.get("extra_context"),
            )
            results.append(result)
        return results
