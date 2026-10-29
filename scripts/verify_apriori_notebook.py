"""Execute every non-installation cell with the optional AI environment."""

import argparse
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--csv", type=Path, help="Also verify the notebook CSV mode using an application export.")
args = parser.parse_args()
notebook = json.loads((BASE / "notebooks/01_apriori_goi_y_mon.ipynb").read_text(encoding="utf-8"))
scope = {"__name__": "__notebook__"}
executed = 0
for index, cell in enumerate(notebook["cells"]):
    if cell["cell_type"] != "code":
        continue
    source = "".join(cell["source"])
    if source.startswith("%pip "):
        continue
    if args.csv and source.startswith('DATA_MODE = "demo"'):
        source = source.replace('DATA_MODE = "demo"', 'DATA_MODE = "csv"', 1)
        source = source.replace('CSV_PATH = Path("transactions.csv")', f"CSV_PATH = Path({str(args.csv.resolve())!r})", 1)
    exec(compile(source, f"notebook_cell_{index}", "exec"), scope)
    executed += 1
model, output = scope["MODEL"], scope["OUTPUT_DIR"]
assert model["data_source"] == ("application_export" if args.csv else "synthetic_demo")
assert model["training"]["baskets"] + model["training"]["holdout_baskets"] == scope["transactions"]["basket_id"].nunique()
if not args.csv:
    assert model["rules"], "The deliberately associated demo should produce rules"
assert (output / "evaluation.json").is_file()
assert Path(scope["ARCHIVE"]).is_file()
if model["rules"]:
    assert scope["suggestions"] and not set(scope["suggestions"]) & set(scope["CART"])
print(f"Notebook verified: {executed} cells, {len(model['rules'])} rules, artifacts: {output}")
