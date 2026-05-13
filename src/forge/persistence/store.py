"""Workflow state persistence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from forge.config import get_config
from forge.utils.logging import get_logger

if TYPE_CHECKING:
    from forge.core.orchestrator import Workflow

logger = get_logger("forge.persistence.store")


@dataclass
class WorkflowSnapshot:
    """A point-in-time snapshot of workflow state."""

    workflow_id: str
    spec_id: str
    status: str
    steps: dict[str, dict[str, Any]]
    context: dict[str, Any]
    created_at: str
    snapshot_at: str
    version: int = 1


class WorkflowStore:
    """Persists workflow state to disk."""

    def __init__(self, snapshot_dir: Path | None = None) -> None:
        self.config = get_config()
        self._snapshot_dir = snapshot_dir or Path("./.forge/snapshots")
        self._snapshot_dir.mkdir(parents=True, exist_ok=True)

    def save(self, workflow: Workflow) -> Path:
        snapshot = WorkflowSnapshot(
            workflow_id=workflow.workflow_id,
            spec_id=workflow.spec_id,
            status=workflow.status.value,
            steps={
                sid: {
                    "status": s.status.value,
                    "result": s.result.output if s.result else None,
                    "start_time": s.start_time,
                    "end_time": s.end_time,
                    "retry_count": s.retry_count,
                    "checkpoint_id": s.checkpoint_id,
                }
                for sid, s in workflow.steps.items()
            },
            context=dict(workflow.context),
            created_at=datetime.utcnow().isoformat(),
            snapshot_at=datetime.utcnow().isoformat(),
        )

        path = self._snapshot_dir / f"{workflow.workflow_id}.json"
        path.write_text(
            json.dumps(snapshot.__dict__, indent=2, default=str),
            encoding="utf-8",
        )

        logger.info("workflow_snapshot_saved", workflow_id=workflow.workflow_id, path=str(path))
        return path

    def load(self, workflow_id: str) -> WorkflowSnapshot | None:
        path = self._snapshot_dir / f"{workflow_id}.json"
        if not path.exists():
            return None

        data = json.loads(path.read_text(encoding="utf-8"))
        snapshot = WorkflowSnapshot(**data)
        logger.info("workflow_snapshot_loaded", workflow_id=workflow_id)
        return snapshot

    def list_snapshots(self) -> list[str]:
        return [p.stem for p in self._snapshot_dir.glob("*.json")]

    def delete(self, workflow_id: str) -> bool:
        path = self._snapshot_dir / f"{workflow_id}.json"
        if path.exists():
            path.unlink()
            logger.info("workflow_snapshot_deleted", workflow_id=workflow_id)
            return True
        return False

    def cleanup_old(self, max_age_hours: int = 168) -> int:
        now = datetime.utcnow()
        deleted = 0
        for path in self._snapshot_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                snapshot_at = datetime.fromisoformat(data["snapshot_at"])
                age = (now - snapshot_at).total_seconds() / 3600
                if age > max_age_hours:
                    path.unlink()
                    deleted += 1
            except Exception:
                pass
        logger.info("workflow_snapshots_cleaned", deleted=deleted)
        return deleted
