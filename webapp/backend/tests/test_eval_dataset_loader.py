from __future__ import annotations

import unittest

from webapp.backend.evals.dataset_loader import load_local_dataset


class EvalDatasetLoaderTests(unittest.TestCase):
    def test_load_appeal_judge_dataset(self):
        dataset = load_local_dataset("appeal_judge_v1")
        self.assertEqual(dataset.dataset_name, "appeal_judge_v1")
        self.assertEqual(dataset.agent_name, "appeal_judge")
        self.assertGreaterEqual(len(dataset.cases), 3)


if __name__ == "__main__":
    unittest.main()
