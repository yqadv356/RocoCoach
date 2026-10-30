"""Thin adapter to reused battle engine; no battle formulas implemented here."""
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BUNDLED_NODE = Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node"
SCENARIOS = {
    "practice": "均衡对练：杰尼龟 vs 杰尼龟",
    "electric": "属性与命中：皮卡丘 vs 杰尼龟",
    "fire": "不同招式的收益：喷火龙 vs 妙蛙花",
    "water": "比较伤害区间：水箭龟 vs 喷火龙",
}


def node_path() -> str:
    candidate = os.getenv("ROCOCOACH_NODE") or shutil.which("node")
    if candidate:
        return candidate
    if BUNDLED_NODE.is_file():
        return str(BUNDLED_NODE)
    raise RuntimeError("找不到 Node.js。请安装 Node.js 22+，或设置 ROCOCOACH_NODE。")


def simulate(scenario="electric", seed=42, history=None, *, autoplay=False, ruleset="standard-v1",difficulty="standard"):
    if difficulty not in {'standard','challenge'}:raise ValueError('不支持的训练档位。')
    if ruleset not in {"standard-v1", "short-pp-v1"}:
        raise ValueError("不支持的对局规则版本。")
    if scenario not in SCENARIOS:
        raise ValueError("请选择已提供的教学场景。")
    if type(seed) is not int or not 0 <= seed <= 65535:
        raise ValueError("随机种子必须是 0–65535 的整数。")
    if history is None:
        history = []
    if not isinstance(history, list) or len(history) > 60:
        raise ValueError("最多保留 60 回合。")
    if any(move not in {"move 1", "move 2", "move 3", "move 4"} for move in history):
        raise ValueError("行动不在合法选项内。")
    if not (ROOT / "engine/node_modules/pokemon-showdown").exists():
        raise RuntimeError("对战依赖未安装，请运行 .venv/bin/python scripts/setup_battle.py。")
    try:
        result = subprocess.run(
            [node_path(), str(ROOT / "engine/bridge.cjs")],
            input=json.dumps(dict(scenario=scenario, seed=seed, history=history, autoplay=autoplay, ruleset=ruleset,difficulty=difficulty)),
            text=True, capture_output=True, cwd=ROOT, timeout=20, check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("本地对战计算超时，当前已保存的对局未改变。") from exc
    except OSError as exc:
        raise RuntimeError("无法启动 Node.js，请检查运行环境配置。") from exc
    if result.returncode:
        raise RuntimeError("对战引擎未完成请求：" + result.stderr[:400])
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("对战引擎返回了无法读取的结果。") from exc


def report(battle):
    from rococoach.zh import name
    rows = ["# 宠物对战教学复盘", "", "宝可梦第九世代自定义教学局，不代表洛克王国规则。",
            f"场景：{battle['title']}；种子：{battle['seed']}",
            f"引擎：{battle['engine']}；计算器：{battle['calculator']}",
            "军师按伤害区间均值 × 标称命中率排序，不是最优策略或胜率。",
            f"结果：{name(battle['winner']) if battle['winner'] else '尚未结束'}", ""]
    for turn in battle["rounds"]:
        rows.append(f"- 回合 {turn['turn']}：选择 {name(turn['selected'])}；计算排序首位 {name(turn['recommended'])}；"
                    f"己方 HP {turn['playerHpBefore']} → {turn['playerHpAfter']}；"
                    f"对方 HP {turn['opponentHpBefore']} → {turn['opponentHpAfter']}。")
    rows += ["", "HP 变化包括回合内其他效果，不能直接等同于某招的伤害。",
             "技能资料：Pokémon Showdown Dex；伤害计算：Smogon Damage Calculator。",
             "", "## 原始引擎日志", "```text", battle["log"], "```"]
    return "\n".join(rows)
