"""Tests for the Spec Engine."""

from __future__ import annotations

import pytest
from pathlib import Path

from forge.core.spec_engine import Spec, SpecEngine, SpecStep, SpecStepType


class TestSpecEngine:
    """Test suite for spec parsing and validation."""

    def test_load_from_yaml(self, tmp_path: Path) -> None:
        """Load a valid YAML spec."""
        spec_file = tmp_path / "test.yaml"
        spec_file.write_text("""
id: SPEC-TEST-001
title: Test Spec
description: A test specification
steps:
  - id: step-1
    type: plan
    title: Planning
    agent_role: planner
    depends_on: []
  - id: step-2
    type: code
    title: Coding
    agent_role: coder
    depends_on: [step-1]
""")
        engine = SpecEngine(spec_dir=tmp_path)
        spec = engine.load_from_yaml(spec_file)

        assert spec.id == "SPEC-TEST-001"
        assert spec.title == "Test Spec"
        assert len(spec.steps) == 2
        assert spec.get_step("step-1").type == SpecStepType.PLAN

    def test_load_from_markdown(self, tmp_path: Path) -> None:
        """Load a Markdown spec with frontmatter and step blocks."""
        spec_file = tmp_path / "test.md"
        spec_file.write_text("""---
id: SPEC-MD-001
title: Markdown Spec
---

## Description
Test description.

#### STEP: plan-phase
**Type:** plan
**Agent:** planner
**Depends:** []

Plan the implementation.

#### STEP: code-phase
**Type:** code
**Agent:** coder
**Depends:** [plan-phase]

Implement the solution.
""")
        engine = SpecEngine(spec_dir=tmp_path)
        spec = engine.load_from_markdown(spec_file)

        assert spec.id == "SPEC-MD-001"
        assert len(spec.steps) == 2
        assert spec.get_step("code-phase").agent_role == "coder"

    def test_execution_order(self, tmp_path: Path) -> None:
        """Verify topological sort of steps."""
        spec_file = tmp_path / "order.yaml"
        spec_file.write_text("""
id: SPEC-ORDER
title: Order Test
steps:
  - id: c
    type: code
    title: C
    agent_role: coder
    depends_on: [a, b]
  - id: a
    type: plan
    title: A
    agent_role: planner
    depends_on: []
  - id: b
    type: test
    title: B
    agent_role: tester
    depends_on: [a]
""")
        engine = SpecEngine(spec_dir=tmp_path)
        spec = engine.load_from_yaml(spec_file)
        order = spec.execution_order()

        assert order.index("a") < order.index("b")
        assert order.index("a") < order.index("c")
        assert order.index("b") < order.index("c")

    def test_circular_dependency_detection(self, tmp_path: Path) -> None:
        """Detect circular dependencies."""
        spec_file = tmp_path / "cycle.yaml"
        spec_file.write_text("""
id: SPEC-CYCLE
title: Cycle Test
steps:
  - id: a
    type: plan
    title: A
    agent_role: planner
    depends_on: [b]
  - id: b
    type: code
    title: B
    agent_role: coder
    depends_on: [a]
""")
        engine = SpecEngine(spec_dir=tmp_path)
        with pytest.raises(ValueError, match="Circular dependency"):
            engine.load_from_yaml(spec_file)

    def test_self_dependency_rejection(self) -> None:
        """Reject steps that depend on themselves."""
        with pytest.raises(ValueError):
            SpecStep(
                id="self-dep",
                type=SpecStepType.PLAN,
                title="Bad Step",
                agent_role="planner",
                depends_on=["self-dep"],
            )

    def test_compile_to_dag(self, tmp_path: Path) -> None:
        """Compile spec to executable DAG."""
        spec_file = tmp_path / "dag.yaml"
        spec_file.write_text("""
id: SPEC-DAG
title: DAG Test
steps:
  - id: s1
    type: plan
    title: S1
    agent_role: planner
    depends_on: []
  - id: s2
    type: code
    title: S2
    agent_role: coder
    depends_on: [s1]
""")
        engine = SpecEngine(spec_dir=tmp_path)
        spec = engine.load_from_yaml(spec_file)
        dag = engine.compile_to_dag("SPEC-DAG")

        assert dag["spec_id"] == "SPEC-DAG"
        assert "s1" in dag["nodes"]
        assert "s2" in dag["nodes"]
        assert ("s1", "s2") in dag["edges"]
