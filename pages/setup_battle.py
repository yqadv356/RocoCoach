"""Install pinned local battle dependencies without changing global settings."""
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from rococoach.battle import node_path

node = node_path()
bundled = Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/bin/fallback/pnpm"
pnpm = shutil.which("pnpm") or (str(bundled) if bundled.exists() else None)
if not pnpm:
    raise SystemExit("请先安装 pnpm，再重新运行此脚本。项目使用 pnpm-lock.yaml 固定依赖。")
env = dict(os.environ)
env["PATH"] = str(Path(node).parent) + os.pathsep + env.get("PATH", "")
subprocess.run([pnpm, "install", "--frozen-lockfile", "--ignore-scripts"],
               cwd=ROOT / "engine", env=env, check=True)
print("对战依赖就绪。运行 .venv/bin/python scripts/demo_battle.py 验证。")
