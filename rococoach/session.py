"""Choose the facts for the question, separately from the response style."""
from dataclasses import dataclass
import re

from rococoach.zh import name


@dataclass(frozen=True)
class ContextSelection:
    battle: dict
    lesson_context: dict | None
    source: str
    reason: str
    practice_result: dict | None = None


def select_context(lesson,query):
    current=lesson.get("after",lesson["before"])
    has_quiz="result" in lesson
    if not has_quiz:
        return ContextSelection(current,lesson.get("context"),"lesson","当前练习或已执行回合")
    quiz_battle=lesson["quiz"]["snapshot"]
    q=query.strip()
    old_names={name(m["name"]) for m in lesson["before"]["advice"]}
    new_names={name(m["name"]) for m in quiz_battle["advice"]}
    # Explicit new-scene references override a vague reference to the last explanation.
    new_scene=any(name(mon["name"]) in q for mon in [quiz_battle["player"],quiz_battle["opponent"]])
    new_scene=new_scene or bool(re.search("这题|本题|这次判断|答对|选对|新场景",q))
    old_reference=bool(re.search("刚才|上一回合|上一招|刚刚|为什么这样选|为什么这么说",q)) or any(n in q for n in old_names-new_names)
    if old_reference and not new_scene:
        return ContextSelection(current,lesson.get("context"),"previous_turn","问题明确回指上一回合或上一招")
    if "quiz_result" in lesson:
        quiz=lesson["quiz"];result=lesson["quiz_result"]
        outcome={"你的答案":name(next(m["name"] for m in quiz["options"] if m["choice"]==result["selected"])),
            "比较规则排序首位":name(next(m["name"] for m in quiz["options"] if m["choice"]==quiz["correct_choice"])),
            "判断与计算一致":result["correct"],"是否使用提示":lesson.get("quiz_assisted",False)}
        return ContextSelection(quiz_battle,None,"transfer_quiz_completed","迁移题已完成，使用该题状态与判断记录",outcome)
    return ContextSelection(quiz_battle,None,"transfer_quiz","迁移练习进行中，使用新场景事实")


def dialogue_history(lesson,limit=6):
    """Completed exchanges in this scene; old sessions cannot steer a short follow-up."""
    rows=[]
    pending=None
    for item in lesson.get("messages",[]):
        if item.get('status') in {'generating','failed'} or item.get('kind') in {'chat_pending','chat_failed'}:
            pending=None
            continue
        if item["speaker"]=="user":pending=item["text"]
        elif pending:
            rows.append({"user":pending,"assistant":item["text"]+("\n"+item["tool_summary"] if item.get("tool_summary") else ""),
                         "role":item.get("role") or ("老师" if item["kind"] in {"review","quiz"} else "陪聊")})
            pending=None
    return rows[-limit:]
