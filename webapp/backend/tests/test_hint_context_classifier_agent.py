from __future__ import annotations

import sys
import types
import unittest

if "psycopg2" not in sys.modules:
    extras_module = types.SimpleNamespace(Json=lambda value: value)
    psycopg2_module = types.ModuleType("psycopg2")
    psycopg2_module.extras = extras_module
    sys.modules["psycopg2"] = psycopg2_module
    sys.modules["psycopg2.extras"] = extras_module

from webapp.backend.agents.hint_context_classifier.agent import (
    run_hint_context_classifier,
    classify_hint_context_llm_only_observed,
)
from webapp.backend.agents.hint_context_classifier.prompt import build_user_prompt
from webapp.backend.agents.hint_context_classifier.types import HintContextClassifierInput
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
            usage=AgentUsage(prompt_tokens=9, completion_tokens=4, total_tokens=13),
        )


class FakeCursor:
    def __init__(self):
        self.run_id = 77
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


class HintContextClassifierAgentTests(unittest.TestCase):
    def test_prompt_contains_expected_fields(self):
        prompt = build_user_prompt(
            HintContextClassifierInput(
                clue_text="In 2009 he became the 44th president of the United States",
                expected_response="Barack Obama",
                category="U.S. Presidents",
                air_date="2010-04-12",
            )
        )
        self.assertIn("Category: U.S. Presidents", prompt)
        self.assertIn("Air date: 2010-04-12", prompt)
        self.assertIn("Expected answer: Barack Obama", prompt)

    def test_run_classifier_normalizes_negative_reason_code(self):
        classification = run_hint_context_classifier(
            HintContextClassifierInput(
                clue_text="This city is currently the home of the reigning monarch",
                expected_response="London",
                category="Capital Cities",
                air_date="2017-05-01",
            ),
            runner=FakeRunner(
                {
                    "is_point_in_time": False,
                    "reason_code": "current_officeholder",
                    "reason": "Not actually date-sensitive.",
                    "confidence": 0.21,
                }
            ),
        )
        self.assertFalse(classification.is_point_in_time)
        self.assertEqual(classification.reason_code, "not_point_in_time")
        self.assertIn("normalized_negative_reason_code", classification.guardrail_flags)

    def test_run_classifier_short_circuits_without_temporal_anchor(self):
        classification = run_hint_context_classifier(
            HintContextClassifierInput(
                clue_text="This city is known as the Windy City",
                expected_response="Chicago",
                category="Cities",
                air_date="2017-05-01",
            )
        )
        self.assertFalse(classification.is_point_in_time)
        self.assertEqual(classification.reason_code, "not_point_in_time")
        self.assertIn("no_temporal_anchor", classification.guardrail_flags)
        self.assertEqual(classification.model, "deterministic_fallback")

    def test_observed_path_records_run_and_returns_classification(self):
        cur = FakeCursor()
        result = classify_hint_context_llm_only_observed(
            cur,
            trace_id="trace-2",
            run_type="daily_challenge_hint_context",
            clue_id=123,
            clue_text="At the time of this clue, he was the current U.S. secretary of state",
            expected_response="Hillary Clinton",
            category="Cabinet",
            air_date="2010-06-14",
            runner=FakeRunner(
                {
                    "is_point_in_time": True,
                    "reason_code": "current_officeholder",
                    "reason": "The fair answer depends on who held the office on the air date.",
                    "confidence": 0.93,
                }
            ),
        )
        self.assertEqual(result.run_id, 77)
        self.assertIsNotNone(result.classification)
        self.assertIsNone(result.failure)
        executed_sql = "\n".join(sql for sql, _ in cur.executed)
        self.assertIn("INSERT INTO agent_runs", executed_sql)
        self.assertIn("INSERT INTO agent_run_artifacts", executed_sql)
        self.assertIn("UPDATE agent_runs", executed_sql)


if __name__ == "__main__":
    unittest.main()
