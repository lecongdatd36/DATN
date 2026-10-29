import csv
from datetime import datetime
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import pandas as pd

from ai_tools.apriori import evaluate_rules, fit_rules, load_transactions, recommend, run_experiment, split_baskets
from ai_tools.demo import demo_rows, write_demo_csv
from ai_tools.schema import TRANSACTION_FIELDS


class AprioriPipelineTests(unittest.TestCase):
    def write_rows(self, directory, rows):
        path = Path(directory) / "input.csv"
        with path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=TRANSACTION_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        return path

    def test_demo_is_reproducible_and_explicitly_labelled(self):
        first = list(demo_rows(baskets=100, days=20, seed=7))
        self.assertEqual(first, list(demo_rows(baskets=100, days=20, seed=7)))
        self.assertEqual({row["data_source"] for row in first}, {"synthetic_demo"})
        self.assertEqual(len({row["basket_id"] for row in first}), 100)

    def test_invalid_demo_does_not_create_file_and_existing_file_is_preserved(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "demo.csv"
            with self.assertRaises(ValueError):
                write_demo_csv(path, baskets=1)
            self.assertFalse(path.exists())
            path.write_text("keep me", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                write_demo_csv(path)
            self.assertEqual(path.read_text(), "keep me")

    def test_split_keeps_whole_baskets_and_business_days_together(self):
        with TemporaryDirectory() as directory:
            path = write_demo_csv(Path(directory) / "demo.csv", baskets=100, days=20)
            train, test, cutoff = split_baskets(load_transactions(path))
            self.assertEqual(len(train) + len(test), 100)
            self.assertFalse(set(train["basket_id"]) & set(test["basket_id"]))
            self.assertLess(train["closed_at"].max(), test["closed_at"].min())
            self.assertLess(max(train["business_day"]), min(test["business_day"]))
            self.assertEqual(min(test["business_day"]), cutoff)

    def test_mixed_sources_and_conflicting_basket_timestamps_are_rejected(self):
        rows = list(demo_rows(baskets=10, days=10))
        for field, value in (("data_source", "application_export"), ("basket_closed_at", "2025-01-01T01:00:00+07:00")):
            with self.subTest(field=field), TemporaryDirectory() as directory:
                changed = [dict(row) for row in rows]
                changed[0][field] = value
                with self.assertRaises(ValueError):
                    load_transactions(self.write_rows(directory, changed))

    def test_empty_input_naive_dates_and_bad_quantities_are_rejected(self):
        for field, value in (("quantity", "nan"), ("quantity", "inf"), ("quantity", "0"),
                             ("quantity", "1.5"), ("basket_closed_at", "2026-01-01T12:00:00")):
            with self.subTest(field=field, value=value), TemporaryDirectory() as directory:
                rows = list(demo_rows(baskets=10, days=10))
                rows[0][field] = value
                with self.assertRaises(ValueError):
                    load_transactions(self.write_rows(directory, rows))
        with TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                load_transactions(self.write_rows(directory, []))

    def test_rules_have_correct_support_and_do_not_recommend_selected_items(self):
        train = pd.DataFrame({"items": [("A", "B")] * 6 + [("A",)] + [("C", "D")] * 4 + [("C",)]})
        rules, _ = fit_rules(train, min_support=0.1, min_confidence=0.3)
        rule = next(rule for rule in rules if rule["antecedents"] == ["A"] and rule["consequents"] == ["B"])
        self.assertAlmostEqual(rule["support"], 0.5)
        self.assertAlmostEqual(rule["confidence"], 6 / 7)
        self.assertEqual(recommend(["A"], rules), ["B"])
        self.assertEqual(recommend(["A", "B"], rules), [])

    def test_quantity_does_not_duplicate_baskets_or_increase_support(self):
        with TemporaryDirectory() as directory:
            rows = list(demo_rows(baskets=100, days=20))
            original = load_transactions(self.write_rows(directory, rows))
            for row in rows:
                row["quantity"] = 100
            changed = load_transactions(self.write_rows(directory, rows))
            original_train, _, _ = split_baskets(original)
            changed_train, _, _ = split_baskets(changed)
            self.assertEqual(fit_rules(original_train)[0], fit_rules(changed_train)[0])

    def test_singletons_remain_in_training_and_have_no_fake_evaluation_score(self):
        train = pd.DataFrame({"items": [("A",), ("B",)]})
        self.assertEqual(fit_rules(train)[0], [])
        test = pd.DataFrame({"basket_id": ["x"], "items": [("A",)]})
        metrics = evaluate_rules(train, test, [])
        self.assertEqual(metrics["eligible_baskets"], 0)
        self.assertIsNone(metrics["hit_rate_at_k"])

    def test_holdout_unseen_dish_counts_as_a_miss(self):
        train = pd.DataFrame({"items": [("A", "B")] * 10})
        rules, _ = fit_rules(train, min_lift=1)
        test = pd.DataFrame({"basket_id": ["unknown"], "items": [("X", "Y")]})
        metrics = evaluate_rules(train, test, rules)
        self.assertEqual(metrics["eligible_baskets"], 1)
        self.assertEqual(metrics["hit_rate_at_k"], 0)
        self.assertEqual(metrics["popularity_baseline_hit_rate_at_k"], 0)

    def test_end_to_end_exports_json_safe_rules_metrics_and_fold_provenance(self):
        with TemporaryDirectory() as directory:
            csv_path = write_demo_csv(Path(directory) / "demo.csv", baskets=500, days=60)
            output = Path(directory) / "results"
            model = run_experiment(csv_path, output)
            saved = json.loads((output / "apriori_model.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["rules"], model["rules"])
            self.assertTrue(model["rules"])
            self.assertEqual(saved["data_source"], "synthetic_demo")
            self.assertEqual(saved["training"]["baskets"] + saved["training"]["holdout_baskets"], 500)
            self.assertEqual(len(saved["input_sha256"]), 64)
            for name in ("evaluation.json", "association_rules.csv", "frequent_itemsets.csv", "train_baskets.csv", "holdout_baskets.csv"):
                self.assertTrue((output / name).is_file())
            self.assertLess(datetime.fromisoformat(saved["training"]["train_end"]),
                            datetime.fromisoformat(saved["training"]["holdout_start_business_day"] + "T00:00:00+07:00"))
