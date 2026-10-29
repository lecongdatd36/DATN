"""Run the one-cell notebook in a fresh namespace, including its isolated worker."""

import argparse
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--csv", type=Path, help="Verify CSV mode using an application export.")
args = parser.parse_args()
notebook = json.loads((BASE / "notebooks/01_apriori_goi_y_mon.ipynb").read_text(encoding="utf-8"))
cells = [cell for cell in notebook["cells"] if cell["cell_type"] == "code"]
assert len(cells) == 1, "The beginner notebook must have exactly one runnable cell"
source = "".join(cells[0]["source"])
if args.csv:
    source = source.replace('DATA_MODE = "demo"', 'DATA_MODE = "csv"', 1)
    source = source.replace("requirements=TRAINING_REQUIREMENTS,",
                            f"requirements=TRAINING_REQUIREMENTS, csv_path={str(args.csv.resolve())!r}, download=False,", 1)
scope = {"__name__": "__notebook__"}
exec(compile(source, "notebook_one_cell", "exec"), scope)
model, output, inference = scope["MODEL"], scope["OUTPUT_DIR"], scope["INFERENCE"]
assert model["data_source"] == ("application_export" if args.csv else "synthetic_demo")
assert model["training"]["baskets"] + model["training"]["holdout_baskets"] == inference["basket_count"]
if not args.csv:
    assert model["rules"] and inference["suggestions"]
assert (output / "evaluation.json").is_file()
assert Path(scope["ARCHIVE"]).is_file()
assert not set(inference["suggestions"]) & set(inference["cart"])
print(f"One-cell notebook verified from an empty namespace: {len(model['rules'])} rules; {output}")
