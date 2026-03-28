from __future__ import annotations

import unittest

from webapp.backend.evals.dataset_loader import load_local_dataset


class EvalDatasetLoaderTests(unittest.TestCase):
    def test_load_appeal_judge_dataset(self):
        dataset = load_local_dataset("appeal_judge_v1")
        self.assertEqual(dataset.dataset_name, "appeal_judge_v1")
        self.assertEqual(dataset.agent_name, "appeal_judge")
        self.assertGreaterEqual(len(dataset.cases), 3)

    def test_load_hint_context_classifier_dataset(self):
        dataset = load_local_dataset("hint_context_classifier_v1")
        self.assertEqual(dataset.dataset_name, "hint_context_classifier_v1")
        self.assertEqual(dataset.agent_name, "hint_context_classifier")
        self.assertGreaterEqual(len(dataset.cases), 5)


if __name__ == "__main__":
    unittest.main()
