"""Tests for voice-driven spec creation."""

from __future__ import annotations

import pytest

from forge.voice.transcriber import Language, TranscriptionResult, VoiceTranscriber
from forge.voice.spec_generator import GeneratedSpec, VoiceSpecGenerator
from forge.voice.session import VoiceSession


class TestVoiceTranscriber:
    """Test suite for voice transcription."""

    @pytest.fixture
    def transcriber(self):
        return VoiceTranscriber(language=Language.HINGLISH)

    @pytest.mark.asyncio
    async def test_transcribe_english(self, transcriber: VoiceTranscriber) -> None:
        """Transcribe plain English input."""
        result = await transcriber.transcribe(text_input="create authentication system with MFA")

        assert isinstance(result, TranscriptionResult)
        assert result.language == Language.ENGLISH
        assert "authentication" in result.text
        assert result.intent == "create_spec"
        assert len(result.entities) > 0

    @pytest.mark.asyncio
    async def test_transcribe_hinglish(self, transcriber: VoiceTranscriber) -> None:
        """Transcribe Hinglish code-mix input."""
        result = await transcriber.transcribe(text_input="ek auth system banana hai with JWT")

        assert result.language == Language.HINGLISH
        assert "create" in result.text
        assert "auth" in result.text
        assert result.is_code_mix is True

    @pytest.mark.asyncio
    async def test_extract_entities(self, transcriber: VoiceTranscriber) -> None:
        """Extract roles and technologies from text."""
        result = await transcriber.transcribe(
            text_input="planner should design the API, coder will implement with FastAPI"
        )

        roles = [e for e in result.entities if e["type"] == "role"]
        techs = [e for e in result.entities if e["type"] == "technology"]

        assert any(e["value"] == "planner" for e in roles)
        assert any(e["value"] == "coder" for e in roles)
        assert any(e["value"] == "fastapi" for e in techs)

    @pytest.mark.asyncio
    async def test_classify_intent_create(self, transcriber: VoiceTranscriber) -> None:
        """Classify create_spec intent."""
        result = await transcriber.transcribe(text_input="create a new payment system")
        assert result.intent == "create_spec"

    @pytest.mark.asyncio
    async def test_classify_intent_run(self, transcriber: VoiceTranscriber) -> None:
        """Classify run_workflow intent."""
        result = await transcriber.transcribe(text_input="run the auth workflow")
        assert result.intent == "run_workflow"

    def test_detect_language_hinglish(self, transcriber: VoiceTranscriber) -> None:
        """Detect Hinglish from markers."""
        lang = transcriber._detect_language("ek system banana hai")
        assert lang == Language.HINGLISH

    def test_detect_language_english(self, transcriber: VoiceTranscriber) -> None:
        """Detect English text."""
        lang = transcriber._detect_language("create a new system")
        assert lang == Language.ENGLISH

    def test_normalize_vernacular(self, transcriber: VoiceTranscriber) -> None:
        """Convert Hinglish to English."""
        normalized = transcriber._normalize_vernacular("ek auth system banana hai")
        assert "create" in normalized
        assert "banana" not in normalized


class TestVoiceSpecGenerator:
    """Test suite for spec generation from voice."""

    @pytest.fixture
    def generator(self):
        return VoiceSpecGenerator()

    @pytest.fixture
    def sample_transcription(self):
        return TranscriptionResult(
            text="create authentication system with MFA and JWT",
            language=Language.ENGLISH,
            confidence=0.92,
            is_code_mix=False,
            entities=[
                {"type": "technology", "value": "mfa", "confidence": 0.9},
                {"type": "technology", "value": "jwt", "confidence": 0.9},
            ],
            intent="create_spec",
            raw_transcript="create authentication system with MFA and JWT",
        )

    @pytest.mark.asyncio
    async def test_generate_spec(self, generator: VoiceSpecGenerator, sample_transcription: TranscriptionResult) -> None:
        """Generate a spec from transcription."""
        result = await generator.generate(sample_transcription)

        assert isinstance(result, GeneratedSpec)
        assert result.spec.id.startswith("SPEC-VOICE-")
        assert len(result.spec.steps) > 0
        assert result.confidence > 0.5

    @pytest.mark.asyncio
    async def test_spec_has_steps(self, generator: VoiceSpecGenerator, sample_transcription: TranscriptionResult) -> None:
        """Generated spec contains appropriate steps."""
        result = await generator.generate(sample_transcription)
        step_types = [s.type.value for s in result.spec.steps]

        assert "plan" in step_types or "code" in step_types

    @pytest.mark.asyncio
    async def test_dependencies_added(self, generator: VoiceSpecGenerator, sample_transcription: TranscriptionResult) -> None:
        """Steps have logical dependencies."""
        result = await generator.generate(sample_transcription)

        code_steps = [s for s in result.spec.steps if s.type.value == "code"]
        plan_steps = [s for s in result.spec.steps if s.type.value == "plan"]

        if code_steps and plan_steps:
            assert any(plan_steps[0].id in cs.depends_on for cs in code_steps)

    def test_extract_title(self, generator: VoiceSpecGenerator) -> None:
        """Extract concise title from text."""
        title = generator._extract_title("create authentication system with MFA support")
        assert "Authentication" in title
        assert len(title.split()) <= 8


class TestVoiceSession:
    """Test suite for voice sessions."""

    @pytest.mark.asyncio
    async def test_session_start(self) -> None:
        """Create a new voice session."""
        session = VoiceSession(language=Language.ENGLISH)

        assert session.session_id.startswith("voice-")
        assert session.state.status == "active"
        assert session.state.language == Language.ENGLISH

    @pytest.mark.asyncio
    async def test_process_utterance(self) -> None:
        """Process a single utterance."""
        session = VoiceSession(language=Language.ENGLISH)
        result = await session.process_utterance(text_input="create auth system with MFA")

        assert result["session_id"] == session.session_id
        assert result["intent"] == "create_spec"
        assert "spec_preview" in result
        assert result["status"] == "confirming"

    @pytest.mark.asyncio
    async def test_multi_turn_session(self) -> None:
        """Multi-turn session accumulates context."""
        session = VoiceSession(language=Language.ENGLISH)

        await session.process_utterance(text_input="create auth system")
        await session.process_utterance(text_input="add JWT and rate limiting")

        assert len(session.state.utterances) == 2
        assert session.state.generated_spec is not None

    @pytest.mark.asyncio
    async def test_confirm_spec(self) -> None:
        """Confirm and finalize spec."""
        session = VoiceSession(language=Language.ENGLISH)
        await session.process_utterance(text_input="create auth system")

        generated = session.confirm_spec()
        assert session.state.confirmed is True
        assert session.state.status == "completed"
        assert generated.spec.id.startswith("SPEC-VOICE-")

    def test_discard_spec(self) -> None:
        """Discard spec cancels session."""
        session = VoiceSession(language=Language.ENGLISH)
        session.discard_spec()
        assert session.state.status == "cancelled"

    def test_session_summary(self) -> None:
        """Get session summary."""
        session = VoiceSession(language=Language.HINGLISH)
        summary = session.get_session_summary()

        assert summary["session_id"] == session.session_id
        assert summary["language"] == "hi-en"
        assert summary["utterance_count"] == 0

    def test_list_active_sessions(self) -> None:
        """List active sessions."""
        VoiceSession._sessions.clear()
        s1 = VoiceSession(session_id="active-1")
        s2 = VoiceSession(session_id="active-2")
        s2.discard_spec()

        active = VoiceSession.list_active_sessions()
        assert "active-1" in active
        assert "active-2" not in active

    def test_cleanup_old_sessions(self) -> None:
        """Remove old sessions."""
        from datetime import datetime, timedelta
        session = VoiceSession(session_id="old-session")
        session.state.started_at = datetime.utcnow() - timedelta(hours=48)

        removed = VoiceSession.cleanup_old_sessions(max_age_hours=24)
        assert removed >= 1
        assert "old-session" not in VoiceSession._sessions
