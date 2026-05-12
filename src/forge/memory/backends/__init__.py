"""Memory backends for Forge.

Provides concrete implementations of the MemoryBackend protocol:
- InMemoryBackend: Fast, ephemeral (testing/development)
- RedisBackend: Persistent, distributed (production)
"""

from forge.memory.backends.redis import RedisBackend

__all__ = ["RedisBackend"]
