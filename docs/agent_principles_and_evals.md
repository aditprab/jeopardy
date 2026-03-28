# Agent Principles and Evals

## Goals

We want backend agents to be:

- clearly denoted in the codebase
- independently testable without live model calls
- versioned at the policy and prompt level
- observable in production
- replayable against curated eval datasets

This document defines the minimum architecture to support that.

## Principles

### 1. Agents are first-class modules

Each agent should live in its own module or package under `webapp/backend/agents/`.

Each agent owns:

- `agent_name`
- `agent_version`
- `policy_version`
- `prompt_version`
- typed input and output models
- prompt construction
- output normalization and guardrails

Callers should not know prompt text, response schema details, or parsing rules.

### 2. Separate invocation from execution

Keep these concerns distinct:

- invocation policy: when product code decides to call an agent
- execution runtime: client setup, timeouts, model invocation, JSON schema enforcement
- prompt policy: instructions and examples shown to the model
- post-processing policy: confidence thresholds, normalization, fail-open or fail-closed behavior

This makes agent behavior testable and reusable in API handlers, scripts, and backfills.

### 3. Version everything that affects behavior

Every agent run should persist:

- `agent_name`
- `agent_version`
- `policy_version`
- `prompt_version`
- `model`

If prompt logic or guardrail logic changes, versions should change too. This enables meaningful comparisons across runs and evals.

### 4. Production observability is not the same as evals

The existing `agent_runs`, `agent_run_events`, and `agent_run_artifacts` tables are production telemetry. They are useful for debugging and auditing.

They are not enough for an eval framework by themselves. Evals need:

- curated datasets
- gold labels
- scoring logic
- replay support across agent versions

### 5. Optimize for replayability

An agent should be runnable from:

- request handlers
- scripts
- backfills
- unit tests
- eval jobs

The same input should flow through the same agent entry point in all cases.

## Minimal Architecture

Recommended backend layout:

```text
webapp/backend/agents/
  __init__.py
  runtime.py
  appeal_judge/
    __init__.py
    agent.py
    prompt.py
    types.py
  point_in_time_classifier/
    __init__.py
    agent.py
    prompt.py
    types.py
webapp/backend/tests/
  test_appeal_judge_agent.py
```

## Shared Runtime Responsibilities

The shared runtime should handle:

- OpenAI client initialization
- timeout configuration
- model selection from env or explicit override
- structured JSON schema requests
- token usage extraction
- common execution metadata

The runtime should accept injected clients in tests so unit tests do not require monkeypatching globals or making network calls.

## Agent Contract

Each agent should expose one main callable:

`run(input, runner=...) -> result`

The returned result should include:

- normalized business output
- model metadata
- token usage
- raw parsed output
- guardrail flags

This lets product code use the normalized result while observability and eval tooling retain the raw model output.

## Caller Responsibilities

Product code should only own:

- whether to invoke the agent
- what to do if the agent fails
- how the normalized output affects product behavior

Product code should not:

- build prompts
- parse raw model JSON
- apply agent-specific guardrails
- patch agent metadata after the call

## Testing Strategy

### Unit tests

Fast and offline.

Cover:

- prompt construction
- schema parsing
- normalization and guardrails
- failure handling

### Fixture tests

Use saved examples that represent real product edge cases.

Each fixture should contain:

- agent input
- expected normalized output
- optional gold label

These should be the first layer of an eval corpus.

### Live evals

Replay curated datasets against a specific agent version and model.

For each eval run, persist:

- eval set version
- agent version
- prompt version
- policy version
- model
- per-case outputs
- summary metrics

## Eval Framework Direction

A lightweight future schema should include:

- `agent_eval_sets`
- `agent_eval_cases`
- `agent_eval_runs`
- `agent_eval_results`

This should remain separate from production telemetry tables.

## Immediate Refactor Plan

1. Introduce `webapp/backend/agents/runtime.py`.
2. Move the current appeal judge into `webapp/backend/agents/appeal_judge/`.
3. Keep a compatibility shim at `webapp/backend/appeal_judge.py` during transition.
4. Add offline unit tests for the appeal judge contract.
5. Add the next agent, `point_in_time_classifier`, only after the above structure exists.

## Non-Goals

For now we are not building:

- a generic workflow engine
- multi-agent orchestration
- human review tooling
- online prompt experimentation

The goal is a disciplined single-agent framework that scales cleanly to two or three task-specific agents.
