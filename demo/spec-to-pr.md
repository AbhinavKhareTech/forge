---
id: DEMO-SPEC-001
title: Spec-to-PR Demo
description: |
  End-to-end demo of Forge orchestrating agents from spec to PR.
  This spec demonstrates planner -> coder -> reviewer workflow
  with governance checkpoints.
author: forge-demo
constitution_refs:
  - security
  - testing
---

## Context
Build a simple REST API for user management with authentication.

#### STEP: plan-api
**Type:** plan
**Agent:** planner
**Depends:** []

Design a REST API for user management with:
- CRUD endpoints for users
- JWT-based authentication
- Input validation
- Error handling
- OpenAPI documentation

#### STEP: code-api
**Type:** code
**Agent:** coder
**Depends:** [plan-api]

Implement the API based on the planner's design.
Generate FastAPI application with:
- Pydantic models
- SQLAlchemy ORM
- JWT middleware
- Unit tests

#### STEP: review-api
**Type:** review
**Agent:** reviewer
**Depends:** [code-api]

Review the implementation against:
- Security constitution (no secrets, proper auth)
- Testing constitution (>80% coverage)
- Code quality standards
