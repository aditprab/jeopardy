from __future__ import annotations

import sys
import types
import unittest

if "thefuzz" not in sys.modules:
    fuzz_module = types.SimpleNamespace(ratio=lambda a, b: 0, token_sort_ratio=lambda a, b: 0)
    sys.modules["thefuzz"] = types.SimpleNamespace(fuzz=fuzz_module)
if "psycopg2" not in sys.modules:
    extras_module = types.SimpleNamespace(Json=lambda value: value)
    psycopg2_module = types.ModuleType("psycopg2")
    psycopg2_module.extras = extras_module
    sys.modules["psycopg2"] = psycopg2_module
    sys.modules["psycopg2.extras"] = extras_module

from webapp.backend.agents.appeal_judge.agent import (
    HIGH_CONFIDENCE_THRESHOLD,
    judge_appeal,
    run_appeal_judge,
    judge_appeal_llm_only_observed,
)
from webapp.backend.agents.appeal_judge.prompt import build_user_prompt
from webapp.backend.agents.appeal_judge.types import AppealJudgeInput
from webapp.backend.agents.runtime import AgentUsage, JsonSchemaResponse


class FakeRunner:
    def __init__(self, payload: dict[str, object]):
        self.payload = payload

    def resolve_model(self, model=None):
        return model or "fake-model"

    def run_json_schema(self, request, *, model=None):
        return JsonSchemaResponse(
            model=model or "fake-model",
            response_id="resp_test",
            payload=self.payload,
            usage=AgentUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        )


class FakeCursor:
    def __init__(self):
        self.run_id = 41
        self.last_fetchone = None
        self.executed: list[tuple[str, tuple | None]] = []

    def execute(self, sql, params=None):
        self.executed.append((" ".join(str(sql).split()), params))
        if "RETURNING id" in sql:
            self.last_fetchone = (self.run_id,)
        else:
            self.last_fetchone = None

    def fetchone(self):
        return self.last_fetchone


class AppealJudgeAgentTests(unittest.TestCase):
    def test_prompt_contains_core_context(self):
        prompt = build_user_prompt(
            AppealJudgeInput(
                clue_text="This investor led Berkshire Hathaway",
                expected_response="Warren Buffett",
                user_response="Buffet",
                user_justification="Minor typo",
            )
        )
        self.assertIn("Clue: This investor led Berkshire Hathaway", prompt)
        self.assertIn("Expected: Warren Buffett", prompt)
        self.assertIn("User response: Buffet", prompt)

    def test_run_appeal_judge_normalizes_low_confidence_accept_to_reject(self):
        decision = run_appeal_judge(
            AppealJudgeInput(
                clue_text="This investor led Berkshire Hathaway",
                expected_response="Warren Buffett",
                user_response="Buffet",
                user_justification=None,
            ),
            runner=FakeRunner(
                {
                    "overturn": True,
                    "final_correct": True,
                    "reason_code": "semantic_equivalence",
                    "match_type": "alias",
                    "same_entity_likelihood": 0.95,
                    "reason": "Likely the same person",
                    "confidence": HIGH_CONFIDENCE_THRESHOLD - 0.01,
                }
            ),
        )
        self.assertFalse(decision.final_correct)
        self.assertEqual(decision.reason_code, "no_match")
        self.assertIn("low_confidence_no_overturn", decision.guardrail_flags)

    def test_judge_appeal_blank_response_stays_deterministic(self):
        decision = judge_appeal(
            clue_text="This investor led Berkshire Hathaway",
            expected_response="Warren Buffett",
            user_response="",
            fuzzy_correct=False,
            user_justification=None,
        )
        self.assertFalse(decision.final_correct)
        self.assertEqual(decision.reason_code, "empty_response")

    def test_observed_path_records_run_and_returns_decision(self):
        cur = FakeCursor()
        result = judge_appeal_llm_only_observed(
            cur,
            trace_id="trace-1",
            run_type="initial_answer_judge",
            clue_id=99,
            clue_text="This investor led Berkshire Hathaway",
            expected_response="Warren Buffett",
            user_response="Buffet",
            user_justification=None,
            runner=FakeRunner(
                {
                    "overturn": True,
                    "final_correct": True,
                    "reason_code": "minor_typo_match",
                    "match_type": "minor_typo",
                    "same_entity_likelihood": 0.98,
                    "reason": "Clearly the same person",
                    "confidence": 0.95,
                }
            ),
        )
        self.assertEqual(result.run_id, 41)
        self.assertIsNotNone(result.decision)
        self.assertIsNone(result.failure)
        executed_sql = "\n".join(sql for sql, _ in cur.executed)
        self.assertIn("INSERT INTO agent_runs", executed_sql)
        self.assertIn("INSERT INTO agent_run_artifacts", executed_sql)
        self.assertIn("UPDATE agent_runs", executed_sql)


if __name__ == "__main__":
    unittest.main()
