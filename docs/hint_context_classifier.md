# Hint Context Classifier

## Purpose

We want a reusable backend agent that classifies clues for user-facing hint context.

The first use case is point-in-time detection, but the design should support additional hint types later. This is not a one-off point-in-time agent. It is a general clue classification agent whose outputs can drive contextual hints in the UI.

Working name:

- `hint_context_classifier`

This name is intended to be broader than `point_in_time_classifier` because the same agent may eventually produce other hint-oriented classifications.

## Product Goal

Some clues are unfairly easy to misread without additional context. The clearest current example is a clue whose correct response depends on the original air date rather than present-day knowledge.

When the classifier determines that a clue is point-in-time-sensitive, the UI should show a hint.

Initial UI copy:

- `Answer might be based on original air date.`

This hint should only appear when the classifier output is positive.

## Scope

Initial scope is one classification:

- `is_point_in_time`

Future scope may include other hint-oriented classifications, so storage and naming should remain generic.

Examples of future expansions:

- answer depends on original cultural context
- answer depends on category wordplay
- clue benefits from special caution about phrasing or date anchoring

These are not part of the first implementation, but the data model should leave room for them.

## Definition

A clue should be marked as point-in-time-sensitive when a reasonable player could answer incorrectly by using present-day knowledge instead of the clue's original air date.

This should be judged conservatively. Precision matters more than recall.

False positives are worse than false negatives because over-warning will train users to overthink ordinary clues.

## Inputs

The classifier should receive only clue-local contextual signals:

- clue text
- expected answer
- air date
- category

The prompt should explicitly instruct the model to reason only from those inputs and not from external current-events knowledge or unstated world knowledge.

The task is not “who is currently correct?” It is “does the clue depend on the original air date for fair answering?”

## Outputs

The normalized stored output should initially include:

- `is_point_in_time: boolean`
- `reason_code: string`
- `confidence: number`

Suggested initial reason codes:

- `current_officeholder`
- `current_titleholder`
- `relative_time_reference`
- `broadcast_time_reference`
- `time_bounded_status`
- `not_point_in_time`

The frontend should only consume the boolean for the first version.

## Storage

Do not store this on `clues` directly.

Create a separate generic table for classifier outputs, named for hint context rather than point-in-time specifically.

Recommended table:

- `clue_hint_contexts`

Recommended initial columns:

- `clue_id`
- `is_point_in_time`
- `reason_code`
- `confidence`
- `agent_name`
- `agent_version`
- `policy_version`
- `prompt_version`
- `model`
- `classified_at`
- `updated_at`

This table should contain the normalized, app-consumable result.

## Explanations and Raw Output

The explanation should not be duplicated into the app-facing table unless we later discover a product need for it.

The explanation and raw model output should live in the existing agent observability tables:

- `agent_runs`
- `agent_run_events`
- `agent_run_artifacts`

That keeps:

- normalized, queryable state in `clue_hint_contexts`
- full audit/debug detail in agent telemetry tables

## Invocation Strategy

Plan of record:

- classify lazily during daily challenge creation
- cache permanently per clue

Concretely:

1. `get_or_create_daily_challenge()` selects clue IDs for the day.
2. For each selected clue, the backend checks `clue_hint_contexts`.
3. If the clue has no cached classification, invoke the classifier once and persist the result.
4. If the clue is already classified, reuse the stored result.

This keeps classification out of answer submission while still ensuring newly surfaced clues are annotated before gameplay.

Future optimization:

- a cron job can pre-create the daily challenge so users never pay the first-classification latency

## Frontend Behavior

Only show the hint when:

- `is_point_in_time = true`

Initial copy:

- `Answer might be based on original air date.`

Do not show uncertain or partial states in the first version.

Do not expose the classifier explanation in the UI.

## Prompt Guidance

The prompt should explicitly instruct the model:

1. use only the supplied clue text, expected answer, category, and air date
2. do not rely on knowledge of current real-world facts beyond what the clue itself implies
3. optimize for precision and be conservative when uncertain
4. mark true only when the air date materially changes what a fair answer should be

## Evaluation

Primary metric:

- precision on `is_point_in_time = true`

Secondary metrics:

- recall
- false positive rate
- reason-code quality

The eval dataset should include:

- obvious time-sensitive clues
- obvious non-time-sensitive clues
- edge cases that mention dates or titles but are still date-invariant

## Implementation Notes

The classifier should be implemented as a second agent in the shared `agents/` framework introduced for the appeal judge.

Recommended package shape:

```text
webapp/backend/agents/hint_context_classifier/
  __init__.py
  agent.py
  prompt.py
  types.py
```

The daily challenge payload should eventually expose at least:

- `is_point_in_time`

for both standard and final clues when available.

## Non-Goals

Initial implementation should not include:

- multiple UI hint classes
- uncertain UI states
- explanation text in the frontend payload
- reclassification on every request
- backfill tooling before the lazy path works
