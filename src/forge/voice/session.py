"""Voice Session -- manages voice-driven spec creation sessions.

Handles the full lifecycle of a voice session:
1. Start session
2. Collect voice input (multiple utterances)
3. Transcribe and accumulate context
4. Generate spec
5. Confirm with user
6. Save or discard
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from forge.voice.transcriber import Language, TranscriptionResult, VoiceTranscriber
from forge.voice.spec_generator import GeneratedSpec, VoiceSpecGenerator
from forge.utils.logging import get_logger

logger = get_logger("forge.voice.session")


@dataclass
class VoiceSessionState:
    """State of an active voice session."""

    session_id: str
    language: Language
    started_at: datetime = field(default_factory=datetime.utcnow)
    utterances: list[TranscriptionResult] = field(default_factory=list)
    generated_spec: GeneratedSpec | None = None
    confirmed: bool = False
    status: str = "active"  # active | generating | confirming | completed | cancelled


class VoiceSession:
    """Manages a voice-driven spec creation session.

    Supports multi-turn conversations where the user can
    iteratively refine the spec through voice commands.
    """

    _sessions: dict[str, VoiceSessionState] = {}

    def __init__(self, session_id: str | None = None, language: Language = Language.HINGLISH) -> None:
        self.session_id = session_id or f"voice-{datetime.utcnow().timestamp():.0f}"
        self.language = language
        self.transcriber = VoiceTranscriber(language=language)
        self.spec_generator = VoiceSpecGenerator()

        # Initialize session state
        if self.session_id not in self._sessions:
            self._sessions[self.session_id] = VoiceSessionState(
                session_id=self.session_id,
                language=language,
            )

    @property
    def state(self) -> VoiceSessionState:
        """Get current session state."""
        return self._sessions[self.session_id]

    async def process_utterance(self, audio_bytes: bytes | None = None, text_input: str | None = None) -> dict[str, Any]:
        """Process a single voice utterance.

        Args:
            audio_bytes: Raw audio data.
            text_input: Text fallback for testing.

        Returns:
            Dict with transcription, entities, and current spec preview.
        """
        # Transcribe
        transcription = await self.transcriber.transcribe(
            audio_bytes=audio_bytes,
            text_input=text_input,
        )

        # Store utterance
        self.state.utterances.append(transcription)

        # Generate or update spec
        self.state.status = "generating"
        combined_text = " ".join([u.text for u in self.state.utterances])
        combined_entities: list[dict[str, Any]] = []
        for u in self.state.utterances:
            combined_entities.extend(u.entities)

        # Create a synthetic transcription with combined context
        combined_transcription = TranscriptionResult(
            text=combined_text,
            language=self.language,
            confidence=transcription.confidence,
            is_code_mix=transcription.is_code_mix,
            entities=combined_entities,
            intent=transcription.intent,
            raw_transcript=" | ".join([u.raw_transcript for u in self.state.utterances]),
        )

        self.state.generated_spec = await self.spec_generator.generate(combined_transcription)
        self.state.status = "confirming"

        logger.info(
            "voice_utterance_processed",
            session=self.session_id,
            utterances=len(self.state.utterances),
            spec_id=self.state.generated_spec.spec.id,
            confidence=self.state.generated_spec.confidence,
        )

        return {
            "session_id": self.session_id,
            "utterance": transcription.text,
            "intent": transcription.intent,
            "entities": transcription.entities,
            "spec_preview": {
                "id": self.state.generated_spec.spec.id,
                "title": self.state.generated_spec.spec.title,
                "steps": [s.id for s in self.state.generated_spec.spec.steps],
                "confidence": self.state.generated_spec.confidence,
            },
            "missing_info": self.state.generated_spec.missing_info,
            "suggestions": self.state.generated_spec.suggestions,
            "status": self.state.status,
        }

    def confirm_spec(self) -> GeneratedSpec:
        """Confirm the generated spec and finalize the session.

        Returns:
            The finalized GeneratedSpec.
        """
        if not self.state.generated_spec:
            raise ValueError("No spec generated yet")

        self.state.confirmed = True
        self.state.status = "completed"

        logger.info("voice_spec_confirmed", session=self.session_id, spec_id=self.state.generated_spec.spec.id)

        return self.state.generated_spec

    def discard_spec(self) -> None:
        """Discard the generated spec and cancel the session."""
        self.state.status = "cancelled"
        logger.info("voice_spec_discarded", session=self.session_id)

    def get_session_summary(self) -> dict[str, Any]:
        """Get a summary of the voice session."""
        return {
            "session_id": self.session_id,
            "language": self.state.language.value,
            "status": self.state.status,
            "utterance_count": len(self.state.utterances),
            "duration_seconds": (datetime.utcnow() - self.state.started_at).total_seconds(),
            "spec": {
                "id": self.state.generated_spec.spec.id if self.state.generated_spec else None,
                "title": self.state.generated_spec.spec.title if self.state.generated_spec else None,
                "confirmed": self.state.confirmed,
            } if self.state.generated_spec else None,
        }

    @classmethod
    def list_active_sessions(cls) -> list[str]:
        """List all active session IDs."""
        return [
            sid for sid, state in cls._sessions.items()
            if state.status in ("active", "generating", "confirming")
        ]

    @classmethod
    def cleanup_old_sessions(cls, max_age_hours: int = 24) -> int:
        """Remove sessions older than max_age_hours.

        Returns:
            Number of sessions removed.
        """
        now = datetime.utcnow()
        to_remove: list[str] = []
        for sid, state in cls._sessions.items():
            age = (now - state.started_at).total_seconds() / 3600
            if age > max_age_hours:
                to_remove.append(sid)

        for sid in to_remove:
            del cls._sessions[sid]

        logger.info("voice_sessions_cleaned", removed=len(to_remove))
        return len(to_remove)
