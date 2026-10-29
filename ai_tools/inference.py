"""Validated Apriori inference using only the Python standard library."""

import json
import math
from pathlib import Path


class InvalidAprioriModel(ValueError):
    pass


def validate_model(payload):
    if not isinstance(payload, dict) or type(payload.get("schema_version")) is not int or payload["schema_version"] != 1:
        raise InvalidAprioriModel("Unsupported model schema")
    if payload.get("algorithm") != "Apriori" or payload.get("data_source") not in {"application_export", "synthetic_demo"}:
        raise InvalidAprioriModel("Unsupported model algorithm or source")
    catalog, rules = payload.get("catalog"), payload.get("rules")
    if not isinstance(catalog, list) or not 1 <= len(catalog) <= 5000 or not isinstance(rules, list) or len(rules) > 5000:
        raise InvalidAprioriModel("Invalid model size")
    identifiers, codes = set(), set()
    for item in catalog:
        if not isinstance(item, dict) or any(not isinstance(item.get(key), str) or not item[key].strip() or len(item[key]) > 200
                                             for key in ("dish_id", "dish_code", "dish_name")):
            raise InvalidAprioriModel("Invalid catalog item")
        if item["dish_id"] in identifiers or item["dish_code"] in codes:
            raise InvalidAprioriModel("Duplicate catalog identifier")
        identifiers.add(item["dish_id"])
        codes.add(item["dish_code"])
    normalized = []
    for rule in rules:
        if not isinstance(rule, dict):
            raise InvalidAprioriModel("Invalid rule")
        left, right = rule.get("antecedents"), rule.get("consequents")
        if any(not isinstance(values, list) or not 1 <= len(values) <= 10 or
               any(not isinstance(value, str) or value not in identifiers for value in values)
               for values in (left, right)):
            raise InvalidAprioriModel("Invalid rule items")
        if len(set(left)) != len(left) or len(set(right)) != len(right) or set(left) & set(right):
            raise InvalidAprioriModel("Invalid rule overlap")
        metrics = {}
        for key in ("support", "confidence", "lift"):
            value = rule.get(key)
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0 or (key != "lift" and value > 1):
                raise InvalidAprioriModel("Invalid rule metrics")
            metrics[key] = float(value)
        normalized.append({"antecedents": sorted(left), "consequents": sorted(right), **metrics})
    normalized.sort(key=lambda rule: (-rule["confidence"], -rule["lift"], -rule["support"], rule["antecedents"], rule["consequents"]))
    return {**payload, "rules": normalized}


def load_model(path):
    path = Path(path)
    if path.stat().st_size > 2_000_000:
        raise InvalidAprioriModel("Model exceeds size limit")
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (ValueError, UnicodeError, RecursionError) as error:
        raise InvalidAprioriModel("Invalid model JSON") from error
    return validate_model(payload)


def recommend(cart, rules, *, k=3, allowed_items=None):
    if k < 1:
        raise ValueError("k phải dương.")
    selected, suggestions = set(cart), []
    allowed = set(allowed_items) if allowed_items is not None else None
    for rule in rules:
        if set(rule["antecedents"]) <= selected:
            for item in rule["consequents"]:
                if item not in selected and item not in suggestions and (allowed is None or item in allowed):
                    suggestions.append(item)
                    if len(suggestions) == k:
                        return suggestions
    return suggestions
