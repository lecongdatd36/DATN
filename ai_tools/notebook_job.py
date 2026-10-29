"""Worker embedded in Colab so each experiment imports packages in a fresh process."""

import json
from pathlib import Path
import sys

from ai_tools.apriori import load_transactions, recommend, run_experiment
from ai_tools.demo import write_demo_csv


def notebook_job(job):
    output = Path(job["output"])
    if job["mode"] == "demo":
        csv_path = write_demo_csv(output.parent / f"demo_{output.name}.csv",
                                  baskets=job["baskets"], days=180, seed=42)
    else:
        csv_path = Path(job["csv_path"])
    model = run_experiment(csv_path, output)
    frame = load_transactions(csv_path)
    catalog = model["catalog"]
    lookup = {}
    for item in catalog:
        for value in (item["dish_id"], item["dish_code"], item["dish_name"]):
            lookup.setdefault(value.casefold(), set()).add(item["dish_id"])
    tokens = [value.strip() for value in job["cart_text"].split(",") if value.strip()]
    cart, unknown, ambiguous = [], [], []
    for token in tokens:
        matches = lookup.get(token.casefold(), set())
        if not matches:
            unknown.append(token)
        elif len(matches) > 1:
            ambiguous.append(token)
        else:
            cart.extend(matches)
    if not tokens and model["rules"]:
        cart = list(model["rules"][0]["antecedents"])
    cart = sorted(set(cart))
    suggestions = recommend(cart, model["rules"]) if not unknown and not ambiguous else []
    result = {"cart": cart, "suggestions": suggestions, "unknown": unknown, "ambiguous": ambiguous,
              "basket_count": int(frame["basket_id"].nunique())}
    (output / "suggestions.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    notebook_job(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")))
