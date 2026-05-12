"""Voice Spec Generator -- converts voice transcription to Forge specs.

Takes TranscriptionResult from VoiceTranscriber and produces a
complete Forge spec document with steps, dependencies, and agent roles.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from forge.core.spec_engine import Spec, SpecStep, SpecStepType
from forge.voice.transcriber import TranscriptionResult
from forge.utils.logging import get_logger

logger = get_logger("forge.voice.spec_generator")


@dataclass
class GeneratedSpec:
    """Result of voice-to-spec generation."""

    spec: Spec
    confidence: float
    missing_info: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)


class VoiceSpecGenerator:
    """Generates Forge specs from voice transcriptions.

    Uses entity extraction and intent classification to build
    structured specs from natural language descriptions.
    """

    def __init__(self) -> None:
        self._step_counter = 0

    async def generate(self, transcription: TranscriptionResult) -> GeneratedSpec:
        """Generate a Forge spec from voice transcription.

        Args:
            transcription: The transcribed and normalized voice input.

        Returns:
            GeneratedSpec with the spec and metadata.
        """
        self._step_counter = 0

        text = transcription.text
        entities = transcription.entities
        intent = transcription.intent

        logger.info(
            "generating_spec_from_voice",
            intent=intent,
            language=transcription.language.value,
            entities=len(entities),
        )

        # Extract spec metadata
        title = self._extract_title(text)
        description = text
        tags = self._extract_tags(entities)

        # Generate steps from entities and text
        steps = self._generate_steps(text, entities)

        # Add dependencies between steps
        steps = self._add_dependencies(steps)

        spec = Spec(
            id=f"SPEC-VOICE-{self._step_counter:03d}",
            title=title,
            description=description,
            author="voice-user",
            tags=tags,
            steps=steps,
        )

        # Validate and identify gaps
        missing_info = self._identify_gaps(spec, entities)
        suggestions = self._generate_suggestions(spec, entities)

        confidence = self._compute_confidence(transcription, len(steps), len(missing_info))

        return GeneratedSpec(
            spec=spec,
            confidence=confidence,
            missing_info=missing_info,
            suggestions=suggestions,
        )

    def _extract_title(self, text: str) -> str:
        """Extract a concise title from the voice input."""
        # Remove common filler words
        fillers = ["please", "can you", "i want", "we need", "banana hai", "chahiye", "karna hai"]
        cleaned = text.lower()
        for filler in fillers:
            cleaned = cleaned.replace(filler, "")
        cleaned = cleaned.strip()

        # Take first 6-8 words as title
        words = cleaned.split()
        if len(words) > 8:
            return " ".join(words[:8]).title()
        return cleaned.title() if cleaned else "Voice Generated Spec"

    def _extract_tags(self, entities: list[dict[str, Any]]) -> list[str]:
        """Extract tags from entities."""
        tags: set[str] = set()
        for entity in entities:
            if entity["type"] == "technology":
                tags.add(entity["value"])
            elif entity["type"] == "role":
                tags.add(entity["value"])
        return list(tags)

    def _generate_steps(self, text: str, entities: list[dict[str, Any]]) -> list[SpecStep]:
        """Generate spec steps from entities and text."""
        steps: list[SpecStep] = []

        # Map extracted roles to steps
        role_steps: dict[str, SpecStepType] = {
            "planner": SpecStepType.PLAN,
            "coder": SpecStepType.CODE,
            "reviewer": SpecStepType.REVIEW,
            "tester": SpecStepType.TEST,
            "sre": SpecStepType.DEPLOY,
        }

        # Always add a planning step if not explicitly mentioned
        has_planner = any(e["type"] == "role" and e["value"] == "planner" for e in entities)
        if not has_planner:
            steps.append(self._create_step("plan", SpecStepType.PLAN, "planner", text))

        # Add steps for each detected role
        for entity in entities:
            if entity["type"] == "role":
                role = entity["value"]
                if role in role_steps:
                    step_type = role_steps[role]
                    steps.append(self._create_step(role, step_type, role, text))

        # If no specific roles detected, infer from text
        if len(steps) <= 1:
            if any(kw in text for kw in ["implement", "code", "build", "banao"]):
                steps.append(self._create_step("code", SpecStepType.CODE, "coder", text))
            if any(kw in text for kw in ["test", "verify", "check"]):
                steps.append(self._create_step("test", SpecStepType.TEST, "tester", text))
            if any(kw in text for kw in ["review", "audit"]):
                steps.append(self._create_step("review", SpecStepType.REVIEW, "reviewer", text))
            if any(kw in text for kw in ["deploy", "release", "ship", "production"]):
                steps.append(self._create_step("deploy", SpecStepType.DEPLOY, "sre", text))

        # Ensure at least a code step exists
        has_code = any(s.type == SpecStepType.CODE for s in steps)
        if not has_code:
            steps.append(self._create_step("code", SpecStepType.CODE, "coder", text))

        return steps

    def _create_step(self, name: str, step_type: SpecStepType, role: str, description: str) -> SpecStep:
        """Create a single spec step."""
        self._step_counter += 1
        return SpecStep(
            id=f"{name}-{self._step_counter:02d}",
            type=step_type,
            title=f"{step_type.value.title()}: {name}",
            description=description,
            agent_role=role,
            depends_on=[],
        )

    def _add_dependencies(self, steps: list[SpecStep]) -> list[SpecStep]:
        """Add logical dependencies between steps."""
        # Plan must come before code
        plan_steps = [s for s in steps if s.type == SpecStepType.PLAN]
        code_steps = [s for s in steps if s.type == SpecStepType.CODE]
        test_steps = [s for s in steps if s.type == SpecStepType.TEST]
        review_steps = [s for s in steps if s.type == SpecStepType.REVIEW]
        deploy_steps = [s for s in steps if s.type == SpecStepType.DEPLOY]

        for code_step in code_steps:
            deps = list(code_step.depends_on)
            for plan_step in plan_steps:
                if plan_step.id not in deps:
                    deps.append(plan_step.id)
            code_step.depends_on = deps

        for test_step in test_steps:
            deps = list(test_step.depends_on)
            for code_step in code_steps:
                if code_step.id not in deps:
                    deps.append(code_step.id)
            test_step.depends_on = deps

        for review_step in review_steps:
            deps = list(review_step.depends_on)
            for code_step in code_steps:
                if code_step.id not in deps:
                    deps.append(code_step.id)
            for test_step in test_steps:
                if test_step.id not in deps:
                    deps.append(test_step.id)
            review_step.depends_on = deps

        for deploy_step in deploy_steps:
            deps = list(deploy_step.depends_on)
            for review_step in review_steps:
                if review_step.id not in deps:
                    deps.append(review_step.id)
            for test_step in test_steps:
                if test_step.id not in deps:
                    deps.append(test_step.id)
            deploy_step.depends_on = deps

        return steps

    def _identify_gaps(self, spec: Spec, entities: list[dict[str, Any]]) -> list[str]:
        """Identify missing information in the generated spec."""
        gaps: list[str] = []

        # Check for missing technologies
        tech_entities = [e for e in entities if e["type"] == "technology"]
        if not tech_entities:
            gaps.append("No specific technology mentioned. Consider specifying framework, database, etc.")

        # Check for missing acceptance criteria
        for step in spec.steps:
            if not step.acceptance_criteria:
                gaps.append(f"Step '{step.id}' has no acceptance criteria")

        # Check for missing constitution refs
        if "security" not in spec.tags and any(t in ["auth", "mfa", "jwt", "oauth"] for t in spec.tags):
            gaps.append("Security-related spec should reference security constitution")

        return gaps

    def _generate_suggestions(self, spec: Spec, entities: list[dict[str, Any]]) -> list[str]:
        """Generate suggestions for improving the spec."""
        suggestions: list[str] = []

        # Suggest adding missing step types
        present_types = {s.type for s in spec.steps}
        if SpecStepType.TEST not in present_types:
            suggestions.append("Consider adding a testing step")
        if SpecStepType.REVIEW not in present_types:
            suggestions.append("Consider adding a review step")

        # Suggest technologies based on context
        text = spec.description.lower()
        if "api" in text and "fastapi" not in text and "flask" not in text:
            suggestions.append("Consider using FastAPI for API development")
        if "auth" in text and "jwt" not in text and "oauth" not in text:
            suggestions.append("Consider JWT or OAuth for authentication")

        return suggestions

    def _compute_confidence(self, transcription: TranscriptionResult, num_steps: int, num_gaps: int) -> float:
        """Compute overall confidence score for the generated spec."""
        base_confidence = transcription.confidence

        # More steps = higher confidence (more detail captured)
        step_bonus = min(num_steps * 0.05, 0.15)

        # More gaps = lower confidence
        gap_penalty = min(num_gaps * 0.1, 0.3)

        confidence = base_confidence + step_bonus - gap_penalty
        return max(0.0, min(1.0, confidence))
