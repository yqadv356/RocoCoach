# 文档阅读顺序

这些文档介绍宠物对战 LLM 教练的产品流程、技术实现与验证。项目优先完成老师的练习与复盘闭环。

## 快速了解项目

1. [怎么讲项目](INTERVIEW_PLAYBOOK.md)：一分钟介绍、五分钟演示、技术主线和准备事项。
2. [常见问题](INTERVIEW_NOTES.md)：用直白的话解释Agent、RAG、记忆、失败修复和个人贡献。
3. [设计与实现稿](SUBMISSION_DRAFT.md)：项目说明书的正文，对应仓库submission里的Word和PDF。

## 按问题查技术细节

| 想弄清什么 | 阅读入口 |
| --- | --- |
| 功能和演示从哪里看 | [项目导航](REVIEWER_GUIDE.md) |
| 聊天怎样真正开局 | [Agent执行](AGENT_EXECUTION_DESIGN.md) |
| 规则从哪来、怎样检索 | [RAG](RAG_IMPLEMENTATION.md) |
| 技能、数值、上下文是什么 | [规则与上下文](RULES_AND_CONTEXT.md) |
| 一局怎样推进、怎样复盘 | [整局流程](FULL_MATCH_DESIGN.md) |
| 怎样实际重放另一招 | [整局工具](MATCH_TOOLS.md) |
| 文字为什么消失、怎样保留 | [消息生命周期](RESPONSE_LIFECYCLE.md) |
| 终局为什么要放后台 | [后台复盘](ASYNC_REVIEW.md) |
| 次数为什么只有几次 | [短局资源规则](SHORT_MATCH_RESOURCES.md) |
| 像素洛洛怎样反馈状态 | [像素伙伴](MASCOT_DESIGN.md) |
| 提交前哪些功能检查过 | [功能复查](FINAL_ACCEPTANCE.md) |
| 到底验证了什么 | [结果与证据](VALIDATION.md) |

当前结果统一看VALIDATION，不必从多份文件里拼测试数量。[公开工程记录](PUBLIC_BUILD_LOG.md)说明重要变化；本机BUILD_LOG保留更完整的过程，未进入公开包。

早期计划、调研和旧技术方案保留历史用途，已在文首标记。它们不能当作当前功能介绍；修改前的详细原文另存本机archive，未混入公开交付。
