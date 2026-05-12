"""Voice Transcriber -- converts speech to text via Swar NLU.

Supports multiple languages and vernacular mixes common in Indian
development teams (Hinglish, Tanglish, etc.).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from forge.utils.logging import get_logger

logger = get_logger("forge.voice.transcriber")


class Language(str, Enum):
    """Supported languages for voice input."""

    ENGLISH = "en"
    HINDI = "hi"
    HINGLISH = "hi-en"  # Hindi-English code-mix
    TAMIL = "ta"
    TELUGU = "te"
    BENGALI = "bn"
    MARATHI = "mr"
    GUJARATI = "gu"
    KANNADA = "kn"
    MALAYALAM = "ml"


@dataclass
class TranscriptionResult:
    """Result of voice transcription."""

    text: str
    language: Language
    confidence: float  # 0.0 - 1.0
    is_code_mix: bool
    entities: list[dict[str, Any]]  # Extracted entities (roles, actions, tools)
    intent: str  # Classified intent (create_spec, modify_spec, run_workflow, etc.)
    raw_transcript: str  # Unprocessed transcript


class VoiceTranscriber:
    """Transcribes voice input to structured text using Swar NLU.

    In production, this integrates with Swar's speech recognition
    and entity extraction pipeline. The mock implementation
    simulates transcription for testing.
    """

    # Common Hinglish/vernacular patterns and their English equivalents
    _VERNACULAR_PATTERNS: dict[str, str] = {
        # Hinglish patterns
        "ek auth system banana hai": "create an authentication system",
        "mfa chahiye": "need MFA support",
        "user login karega": "user will login",
        "password reset ka option": "password reset option",
        "rate limiting lagao": "add rate limiting",
        "database mein store karo": "store in database",
        "api endpoint banao": "create API endpoint",
        "test cases likho": "write test cases",
        "deploy karna hai": "need to deploy",
        "review kar do": "please review",
        # Generic patterns
        "banana hai": "create",
        "chahiye": "need",
        "karega": "will do",
        "ka option": "option for",
        "lagao": "add",
        "mein store karo": "store in",
        "banao": "create",
        "likho": "write",
        "karna hai": "need to",
        "kar do": "do",
    }

    def __init__(self, language: Language = Language.HINGLISH) -> None:
        self.language = language
        self._session_active = False

    async def transcribe(self, audio_bytes: bytes | None = None, text_input: str | None = None) -> TranscriptionResult:
        """Transcribe voice input to structured text.

        Args:
            audio_bytes: Raw audio data (PCM/WAV). In production, sent to Swar ASR.
            text_input: Fallback text input for testing without audio.

        Returns:
            TranscriptionResult with normalized text and extracted entities.
        """
        # Mock: use text_input directly, simulating ASR output
        raw = text_input or "create authentication system with MFA"

        # Detect language and normalize
        detected_lang = self._detect_language(raw)
        normalized = self._normalize_vernacular(raw)

        # Extract entities and intent
        entities = self._extract_entities(normalized)
        intent = self._classify_intent(normalized)

        logger.info(
            "voice_transcribed",
            language=detected_lang.value,
            intent=intent,
            entities=len(entities),
            confidence=0.92,
        )

        return TranscriptionResult(
            text=normalized,
            language=detected_lang,
            confidence=0.92,
            is_code_mix=detected_lang in (Language.HINGLISH,),
            entities=entities,
            intent=intent,
            raw_transcript=raw,
        )

    def _detect_language(self, text: str) -> Language:
        """Detect language from text patterns."""
        # Simple heuristic: check for Devanagari or common Hinglish words
        hinglish_markers = ["hai", "chahiye", "karna", "banao", "kar", "mein", "ka"]
        if any(marker in text.lower() for marker in hinglish_markers):
            return Language.HINGLISH

        # Check for Devanagari script
        devanagari_range = range(0x0900, 0x097F)
        if any(ord(c) in devanagari_range for c in text):
            return Language.HINDI

        return Language.ENGLISH

    def _normalize_vernacular(self, text: str) -> str:
        """Convert vernacular/code-mix to standard English."""
        normalized = text.lower().strip()

        for pattern, replacement in self._VERNACULAR_PATTERNS.items():
            normalized = normalized.replace(pattern, replacement)

        # Clean up extra spaces
        normalized = " ".join(normalized.split())

        return normalized

    def _extract_entities(self, text: str) -> list[dict[str, Any]]:
        """Extract entities from normalized text."""
        entities: list[dict[str, Any]] = []

        # Extract roles
        role_keywords = {
            "planner": ["plan", "design", "architecture", "break down"],
            "coder": ["implement", "code", "write", "develop", "build"],
            "reviewer": ["review", "check", "audit", "validate"],
            "tester": ["test", "verify", "validate"],
            "sre": ["deploy", "monitor", "scale", "provision"],
        }
        for role, keywords in role_keywords.items():
            if any(kw in text for kw in keywords):
                entities.append({"type": "role", "value": role, "confidence": 0.9})

        # Extract step types
        step_keywords = {
            "plan": ["plan", "design", "architecture"],
            "code": ["implement", "code", "write", "build"],
            "test": ["test", "verify"],
            "review": ["review", "audit"],
            "deploy": ["deploy", "release", "ship"],
        }
        for step_type, keywords in step_keywords.items():
            if any(kw in text for kw in keywords):
                entities.append({"type": "step_type", "value": step_type, "confidence": 0.85})

        # Extract tools/technologies
        tech_patterns = [
            ("jwt", ["jwt", "json web token"]),
            ("mfa", ["mfa", "multi.factor", "two.factor", "2fa", "otp"]),
            ("oauth", ["oauth", "openid"]),
            ("redis", ["redis", "cache"]),
            ("postgres", ["postgres", "postgresql", "sql"]),
            ("mongodb", ["mongo", "mongodb"]),
            ("fastapi", ["fastapi", "fast api"]),
            ("docker", ["docker", "container"]),
            ("kubernetes", ["kubernetes", "k8s"]),
            ("aws", ["aws", "s3", "ec2", "lambda"]),
        ]
        for tech, patterns in tech_patterns:
            if any(p in text for p in patterns):
                entities.append({"type": "technology", "value": tech, "confidence": 0.88})

        return entities

    def _classify_intent(self, text: str) -> str:
        """Classify user intent from text."""
        if any(kw in text for kw in ["create", "make", "build", "banana", "banao", "new"]):
            return "create_spec"
        elif any(kw in text for kw in ["modify", "update", "change", "edit"]):
            return "modify_spec"
        elif any(kw in text for kw in ["run", "execute", "start", "chala"]):
            return "run_workflow"
        elif any(kw in text for kw in ["review", "check", "status", "dekho"]):
            return "check_status"
        elif any(kw in text for kw in ["deploy", "release", "ship", "production"]):
            return "deploy"
        return "create_spec"  # Default
