"""Spec Engine -- parses, validates, and compiles executable specs."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator

from forge.utils.logging import get_logger

logger = get_logger("forge.spec_engine")


class SpecStepType(str, Enum):
    PLAN = "plan"
    CODE = "code"
    TEST = "test"
    REVIEW = "review"
    DOCUMENT = "document"
    DEPLOY = "deploy"
    VERIFY = "verify"
    CUSTOM = "custom"


class SpecStep(BaseModel):
    id: str = Field(..., description="Unique step identifier")
    type: SpecStepType = Field(..., description="Step category")
    title: str = Field(default="", description="Human-readable title")
    description: str = Field(default="", description="Detailed requirements")
    agent_role: str = Field(..., description="Which agent role executes this step")
    depends_on: list[str] = Field(default_factory=list, description="Step IDs that must complete first")
    inputs: dict[str, Any] = Field(default_factory=dict, description="Step-specific inputs")
    outputs: dict[str, str] = Field(default_factory=dict, description="Expected output artifacts")
    acceptance_criteria: list[str] = Field(default_factory=list, description="Completion criteria")
    max_attempts: int = Field(default=3, ge=1, description="Max retries before failure")
    requires_human_approval: bool = Field(default=False, description="Force human checkpoint")
    constitution_refs: list[str] = Field(default_factory=list, description="Org standards to enforce")

    @field_validator("depends_on")
    @classmethod
    def no_self_dependency(cls, v: list[str], info: Any) -> list[str]:
        data = info.data
        if "id" in data and data["id"] in v:
            raise ValueError(f"Step {data['id']} cannot depend on itself")
        return v


class Spec(BaseModel):
    version: str = Field(default="1.0", description="Spec format version")
    id: str = Field(..., description="Unique spec identifier")
    title: str = Field(..., description="Spec title")
    description: str = Field(default="", description="Context and background")
    author: str = Field(default="", description="Spec author")
    tags: list[str] = Field(default_factory=list, description="Categorization tags")
    constitution_refs: list[str] = Field(
        default_factory=list,
        description="Global constitution files for this spec",
    )
    steps: list[SpecStep] = Field(..., description="Ordered execution steps")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Extensible metadata")

    def get_step(self, step_id: str) -> SpecStep | None:
        for step in self.steps:
            if step.id == step_id:
                return step
        return None

    def dependency_graph(self) -> dict[str, list[str]]:
        return {step.id: step.depends_on for step in self.steps}

    def execution_order(self) -> list[str]:
        graph = self.dependency_graph()
        visited: set[str] = set()
        temp_mark: set[str] = set()
        order: list[str] = []

        def visit(node: str) -> None:
            if node in temp_mark:
                raise ValueError(f"Circular dependency detected involving step: {node}")
            if node in visited:
                return
            temp_mark.add(node)
            for dep in graph.get(node, []):
                visit(dep)
            temp_mark.remove(node)
            visited.add(node)
            order.append(node)

        for step_id in graph:
            if step_id not in visited:
                visit(step_id)

        return order


class SpecEngine:
    _FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
    _STEP_BLOCK_RE = re.compile(
        r"####\s+STEP:\s*(?P<id>[^\n]+)\n"
        r"(?P<body>.*?)(?=####\s+STEP:|\Z)",
        re.DOTALL,
    )

    def __init__(self, spec_dir: Path | None = None) -> None:
        self.spec_dir = spec_dir or Path("./specs")
        self._specs: dict[str, Spec] = {}

    def load_from_markdown(self, path: Path) -> Spec:
        content = path.read_text(encoding="utf-8")

        frontmatter_match = self._FRONTMATTER_RE.match(content)
        if not frontmatter_match:
            raise ValueError(f"No YAML frontmatter found in {path}")

        frontmatter = yaml.safe_load(frontmatter_match.group(1))

        steps: list[SpecStep] = []
        for match in self._STEP_BLOCK_RE.finditer(content):
            step_id = match.group("id").strip()
            body = match.group("body")
            step = self._parse_step_block(step_id, body)
            steps.append(step)

        if not steps:
            raw_steps = frontmatter.get("steps", [])
            steps = [SpecStep(**s) for s in raw_steps]

        spec = Spec(
            id=frontmatter.get("id", path.stem),
            title=frontmatter.get("title", path.stem),
            description=frontmatter.get("description", ""),
            author=frontmatter.get("author", ""),
            tags=frontmatter.get("tags", []),
            constitution_refs=frontmatter.get("constitution_refs", []),
            steps=steps,
            metadata=frontmatter.get("metadata", {}),
        )

        spec.execution_order()
        self._specs[spec.id] = spec
        logger.info("spec_loaded", spec_id=spec.id, path=str(path), steps=len(steps))
        return spec

    def load_from_yaml(self, path: Path) -> Spec:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        spec = Spec(**data)
        spec.execution_order()
        self._specs[spec.id] = spec
        logger.info("spec_loaded", spec_id=spec.id, path=str(path), steps=len(spec.steps))
        return spec

    def _parse_step_block(self, step_id: str, body: str) -> SpecStep:
        kv_pattern = re.compile(r"\*\*(?P<key>[^:]+):\*\*\s*(?P<value>[^\n]+)")
        fields: dict[str, Any] = {"id": step_id, "title": step_id}

        for match in kv_pattern.finditer(body):
            key = match.group("key").strip().lower()
            value = match.group("value").strip()

            if key == "type":
                fields["type"] = SpecStepType(value)
            elif key == "agent":
                fields["agent_role"] = value
            elif key == "depends":
                deps = [d.strip() for d in value.strip("[]").split(",") if d.strip()]
                fields["depends_on"] = deps
            elif key == "max attempts":
                fields["max_attempts"] = int(value)
            elif key == "requires approval":
                fields["requires_human_approval"] = value.lower() in ("true", "yes", "1")

        description_lines: list[str] = []
        in_kv = True
        for line in body.split("\n"):
            if in_kv and kv_pattern.match(line):
                continue
            in_kv = False
            description_lines.append(line)

        fields["description"] = "\n".join(description_lines).strip()

        return SpecStep(**fields)

    def get_spec(self, spec_id: str) -> Spec | None:
        return self._specs.get(spec_id)

    def list_specs(self) -> list[str]:
        return list(self._specs.keys())

    def compile_to_dag(self, spec_id: str) -> dict[str, Any]:
        spec = self.get_spec(spec_id)
        if not spec:
            raise ValueError(f"Spec not found: {spec_id}")

        order = spec.execution_order()
        edges: list[tuple[str, str]] = []
        for step in spec.steps:
            for dep in step.depends_on:
                edges.append((dep, step.id))

        return {
            "spec_id": spec_id,
            "nodes": order,
            "edges": edges,
            "steps": {s.id: s.model_dump() for s in spec.steps},
        }
