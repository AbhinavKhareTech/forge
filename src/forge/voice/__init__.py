"""Voice-driven spec creation via Swar integration.

Enables developers to create Forge specs using natural language voice
input in vernacular (Hindi-English mix, Hinglish, etc.). Swar NLU
converts speech to structured spec documents.
"""

from forge.voice.transcriber import VoiceTranscriber
from forge.voice.spec_generator import VoiceSpecGenerator
from forge.voice.session import VoiceSession

__all__ = ["VoiceTranscriber", "VoiceSpecGenerator", "VoiceSession"]
