from copy import deepcopy
import unittest
from ai_tools.quality import assess_model_quality


class QualityTests(unittest.TestCase):
    def model(self):
        return {"data_source": "application_export", "data_provenance": {"kind": "confirmed_business"},
            "training": {"baskets": 200}, "evaluation": {"eligible_baskets": 50,
                "protocol": "chronological_business_days_then_hide_one_item_sha256_basket_id",
                "hit_rate_at_k": 0.6, "popularity_baseline_hit_rate_at_k": 0.4}}

    def test_only_enough_verified_data_with_better_holdout_passes(self):
        self.assertTrue(assess_model_quality(self.model())["passed"])
        for section, key, value in (("data_provenance", "kind", "test"), ("training", "baskets", 17),
                ("evaluation", "eligible_baskets", 4), ("evaluation", "hit_rate_at_k", 0.25),
                ("evaluation", "hit_rate_at_k", float("nan")), ("evaluation", "protocol", "random")):
            with self.subTest(key=key):
                model = deepcopy(self.model()); model[section][key] = value
                result = assess_model_quality(model)
                self.assertFalse(result["passed"])
                self.assertEqual(result["serving_strategy"], "popular_paid_dishes")

    def test_empty_and_legacy_metadata_do_not_claim_quality(self):
        self.assertFalse(assess_model_quality({})["passed"])
        model = self.model(); model["data_provenance"] = {"test_orders_confirmed_by_owner": True}
        self.assertFalse(assess_model_quality(model)["passed"])
