from dataclasses import dataclass

GOALS = ("探索规划", "对战复盘", "养成决策")
EXERCISES = {
    "探索规划": "选一个探索目标，记录路线、耗时和遇到的障碍；只改变一个路线选择再尝试。",
    "对战复盘": "选一场对战，记录关键回合的信息、你的选择和结果；提出一个可验证的替代选择。",
    "养成决策": "列出当前资源与一个养成目标，比较两种投入方案，先验证成本更低的一种。",
}


@dataclass(frozen=True)
class Plan:
    goal: str
    minutes: int
    obstacle: str
    steps: tuple[str, ...]

    def markdown(self) -> str:
        steps = "\n".join(f"{i}. {step}" for i, step in enumerate(self.steps, 1))
        return (
            f"## {self.goal} · {self.minutes} 分钟练习\n\n"
            f"你提供的困惑：{self.obstacle}\n\n{steps}\n\n"
            "复盘标准：记录一次实际尝试、一个结果、一个下次要验证的改变。\n\n"
            "说明：这是规则演示，不是模型推理；未接入经过核实的游戏攻略。"
        )


def build_plan(goal: str, minutes: int, obstacle: str) -> Plan:
    if goal not in GOALS:
        raise ValueError("请选择支持的训练目标。")
    if type(minutes) is not int or not 10 <= minutes <= 120:
        raise ValueError("训练时长需要是 10–120 分钟的整数。")
    obstacle = obstacle.strip()
    if not obstacle:
        raise ValueError("请先描述你遇到的困惑。")
    if len(obstacle) > 1000:
        raise ValueError("困惑描述请控制在 1000 字以内。")
    prep = max(2, minutes // 5)
    review = max(2, minutes // 5)
    return Plan(goal, minutes, obstacle, (
        f"准备 {prep} 分钟：围绕上述困惑，写下当前情况和本次要验证的问题。",
        f"实践 {minutes - prep - review} 分钟：{EXERCISES[goal]}",
        f"复盘 {review} 分钟：对照预期与结果，记录证据和下一次尝试。",
    ))
