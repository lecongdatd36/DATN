import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from ai_tools.inference import InvalidAprioriModel, load_model, recommend, validate_model


class AprioriInferenceTests(unittest.TestCase):
    def model(self):
        return {"schema_version": 1, "algorithm": "Apriori", "data_source": "application_export",
                "catalog": [{"dish_id": key, "dish_code": key, "dish_name": key} for key in ("A", "B", "C")],
                "rules": [{"antecedents": ["A"], "consequents": ["B"], "support": 0.3, "confidence": 0.8, "lift": 2},
                          {"antecedents": ["A"], "consequents": ["C"], "support": 0.2, "confidence": 0.7, "lift": 1.5}]}

    def test_inference_filters_unavailable_items_before_limiting_results(self):
        model = validate_model(self.model())
        self.assertEqual(recommend(["A"], model["rules"], k=1, allowed_items={"C"}), ["C"])
        self.assertEqual(recommend(["A", "C"], model["rules"], allowed_items={"C"}), [])

    def test_rejects_unknown_items_nonfinite_metrics_and_duplicate_codes(self):
        for change in ("unknown", "nan", "duplicate", "overlap"):
            with self.subTest(change=change):
                model = self.model()
                if change == "unknown": model["rules"][0]["consequents"] = ["X"]
                if change == "nan": model["rules"][0]["confidence"] = float("nan")
                if change == "duplicate": model["catalog"][1]["dish_code"] = "A"
                if change == "overlap": model["rules"][0]["consequents"] = ["A"]
                with self.assertRaises(InvalidAprioriModel): validate_model(model)

    def test_rejects_invalid_json_and_oversized_file(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "model.json"
            path.write_text("invalid", encoding="utf-8")
            with self.assertRaises(InvalidAprioriModel): load_model(path)
            path.write_bytes(b" " * 2_000_001)
            with self.assertRaises(InvalidAprioriModel): load_model(path)
