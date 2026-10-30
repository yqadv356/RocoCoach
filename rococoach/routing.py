"""One coach, observable rule routing; no extra model call or fake classifier."""
from dataclasses import asdict, dataclass
import re


@dataclass(frozen=True)
class Route:
    role: str
    reason: str
    source: str
    version: str = "intent-rules-v1"

    def as_dict(self):
        return asdict(self)


def route_query(message, battle=None, history=None, event="query"):
    """Explicit needs precede mood; short follow-ups inherit the last response style."""
    if event in {"review", "quiz"}:
        return Route("老师", "练习阶段需要复盘或迁移反馈", "scene")
    q=re.sub(r"\s+", "", message).lower()
    if re.search(r"什么.*模型|哪个.*模型",q):
        return Route("陪聊", "询问模型身份", "query")
    if re.search(r"别.*(?:讲道理|分析|讲课)|先不讲|只想聊|陪我(?:聊|说)|安慰我|先聊",q):
        return Route("陪聊", "用户明确要求先陪伴", "query")
    if re.search(r"为什么|为何|怎么理解|讲解|解释|复盘|没懂|看不懂|教我|怎么进步|怎么练|如果|会怎样|模拟|验证|换成|反事实|对比|比较|查一下|查查|规则|命中率|威力|优先度|属性|特性|资料|附加效果|算一下|再讲|讲一下|提示|答对|选对|对不对|这题",q):
        return Route("老师", "请求原因、解释或学习提示", "query")
    if re.search(r"怎么选|选哪|选什么|用哪|用什么|推荐|建议|下一招|下一步|阵容|配队|怎么打|怎么办|哪个好|哪招",q):
        return Route("军师", "请求可执行的游戏决策", "query")
    if re.search(r"难过|挫败|烦|累了|不开心|开心|紧张|郁闷|压力|你好|早上好|谢谢|聊天|输了|赢了",q):
        return Route("陪聊", "情绪表达或日常交流", "query")
    # Only tightly scoped continuations inherit a style; unrelated messages do not.
    if re.fullmatch(r"[那所以嗯哦好这它]*[呢吗呀啊？?！!，,。\.]*",q) or q in {"继续","然后呢","详细点","还有呢","说下去"}:
        previous=(history or [])[-1:]
        if previous and previous[0].get("role") in {"军师","老师","陪聊"}:
            return Route(previous[0]["role"], "短追问延续最近回应方式", "history")
    if battle and (battle.get("ended") or battle.get("capped")):
        return Route("老师", "已结束的对局默认提供复盘支持", "scene")
    return Route("陪聊", "意图不明确时先自然交流，不强行给攻略", "default")
