"""Actual live smoke test. Never records credentials; no mock success."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from rococoach.battle import simulate
from rococoach.llm import ModelUnavailable, configuration
from rococoach.tutor import make_context, review

parser=argparse.ArgumentParser()
parser.add_argument("--output", type=Path, help="New result file; refuses overwrite")
args=parser.parse_args()
try:
    configuration()
    before=simulate()
    after=simulate(history=["move 4"])
    context=make_context(before,after,"move 4","我以为威力高就应该选 Thunder。",{
        "profile":{"nickname":"演示玩家","preference":"先给提示","mood":"有点挫败"},"recent":[]})
    result=review(context,"live")
except (ValueError,RuntimeError) as exc:
    print(str(exc),file=sys.stderr)
    raise SystemExit(2)
if args.output:
    with args.output.open("x") as f:
        json.dump(result,f,ensure_ascii=False,indent=2)
print(json.dumps({"model":result["metadata"]["model"],"mode":result["metadata"]["mode"],
                  "latency_seconds":result["metadata"]["latency_seconds"],"usage":result["metadata"]["usage"],
                  "suggested_choice":result["answer"]["suggested_choice"],"schema_and_reference_check":"passed"},ensure_ascii=False,indent=2))
