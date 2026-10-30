"""Run with the AI Python, not the web environment."""
import unittest
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from ai_tools.forecast_demo import extend_demo
from ai_tools.forecast_training import feature_row, forecast, baseline_forecast, train
from ai_tools.forecast_store import read_daily


class ForecastTrainingTests(unittest.TestCase):
    def test_features_are_strictly_historical(self):
        history = list(range(1, 29))
        row = feature_row(date(2026, 1, 29), history, date(2026, 1, 1))
        self.assertEqual(row[2:], [28, 28, 22, 15, 1, 25, 14.5])

    def test_multiday_forecast_recursively_uses_its_predictions(self):
        seen = []
        class Model:
            def predict(self, frame):
                values = frame.iloc[0]
                seen.append(values.to_dict())
                return [values["don_hom_qua"] + 10]
        history = list(range(1, 29))
        predictions = forecast(Model(), history, date(2026, 1, 29), date(2026, 1, 1))
        self.assertEqual(predictions, [38, 48, 58, 68, 78, 88, 98])
        self.assertEqual(seen[1]["don_hom_qua"], predictions[0])
        self.assertEqual(history, list(range(1, 29)))
        self.assertEqual(baseline_forecast(history), [22, 23, 24, 25, 26, 27, 28])

    def test_rolling_origins_and_final_refit_do_not_see_future(self):
        reference = date(2026, 12, 12)
        with TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "input.csv"
            extend_demo(path, reference + timedelta(days=30))
            observed = []
            class Model:
                def predict(self, frame): return [frame.iloc[0]["don_hom_qua"]]
            def fit(values, dates, first_day):
                observed.append((len(values), dates[-1]))
                self.assertLess(dates[-1], reference)
                return Model()
            def dump_fixture(model, destination): destination.write_bytes(b"fixture")
            with patch("ai_tools.forecast_training.fit_model", side_effect=fit), patch("ai_tools.forecast_training.joblib.dump", side_effect=dump_fixture), patch("builtins.print"):
                train(path, root / "run", "mo_phong", reference, "test-run")
            size = len([row for row in read_daily(path, "mo_phong") if date.fromisoformat(row["ngay"]) < reference])
            self.assertEqual([length for length, _ in observed], [size - 28, size - 21, size - 14, size - 7, size])
            self.assertEqual([day for _, day in observed], [reference - timedelta(days=i) for i in (29, 22, 15, 8, 1)])


if __name__ == "__main__":
    unittest.main()
