"""Run a complete offline game with the reused engines."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from rococoach.battle import SCENARIOS, simulate

parser = argparse.ArgumentParser()
parser.add_argument("--scenario", choices=SCENARIOS, default="electric")
parser.add_argument("--seed", type=int, default=42)
parser.add_argument("--output", type=Path, help="Optional new JSON evidence file; never overwrites")
args = parser.parse_args()
result = simulate(args.scenario, args.seed, autoplay=True)
print(json.dumps({k:result[k] for k in ("title", "seed", "ended", "winner", "history", "engine", "calculator")}, ensure_ascii=False, indent=2))
if args.output:
    with args.output.open("x") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
if not result["ended"]:
    raise SystemExit("教学局达到回合限制，未完成。")
