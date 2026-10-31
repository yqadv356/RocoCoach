# 功能体验与代码导航

项目优先完成老师的教学流程闭环：整局练习、证据复盘和下一局目标。军师与陪练融合在同一入口，不要求玩家切换角色。

## 建议阅读顺序

1. [README](../README.md)：了解体验、实现范围与运行方法。
2. [八部分设计稿](SUBMISSION_DRAFT.md)，或 [PDF](../submission/RocoCoach_设计与实现.pdf)：了解架构、关键难点、解决方案和取舍。
3. [验证结果](VALIDATION.md)：区分云端程序回归、真实模型样例和小规模探索。
4. 根据关注点查看下表代码；[智能体细节](AGENT_EXECUTION_DESIGN.md)与 [RAG 细节](RAG_IMPLEMENTATION.md)提供更深解释。

## 本地网页体验步骤

| 步骤 | 操作 | 重点观察 |
| --- | --- | --- |
| 1 | 开始均衡训练 | 老师闭环；规则来自公开组件，不冒称真实洛克接口 |
| 2 | 完成几个回合，写一句选招理由，穿插聊天 | 玩家自己决策；聊天不推进回合；真实次数扣减 |
| 3 | 结束整局，查看即时赛果与后台复盘 | 流式正文、实际回合引用、下一局练习目标 |
| 4 | 追问某个已发生回合换招会怎样 | 实际工具记录、独立单回合重放、主局不变 |
| 5 | 聊天请求进阶新局，再要求以后讲短些 | 新局真正创建并保存；表达偏好与对局操作分离 |

按[运行指南](DELIVERY_GUIDE.md)启动 Streamlit 后，在本机浏览器按上表体验功能。当前没有公共在线服务，127.0.0.1 仅在运行项目的电脑上可访问。

一局时长由选择和随机性决定，没有固定完成时长。无密钥模式用于体验对局与交互；真实 LLM 功能需要本地模型配置与网络。仓库中的合成记录用于查证，不代表实时响应。

## 代码入口

| 关注点 | 阅读入口 | 建议核查 |
| --- | --- | --- |
| 整局与教学边界 | [match.py](../rococoach/match.py)、[match_coach.py](../rococoach/match_coach.py) | 引导不代打；行动前后快照、理由与引用 |
| 语义与指代 | [semantic_control.py](../rococoach/semantic_control.py) | IntentPlan、受限上下文、结构化待办与替换核对 |
| 操作与保存 | [control.py](../rococoach/control.py) | 参数、操作结果检查、对局状态标记、同一请求只执行一次与事务合并 |
| 工具循环 | [agent.py](../rococoach/agent.py)、[match_tools.py](../rococoach/match_tools.py) | 预算、阶段白名单、真实观察、独立分支 |
| RAG | [retrieval.py](../rococoach/retrieval.py)、[语料](../data/rag_corpus.json) | 固定来源、候选分数、版本与范围筛选 |
| 记忆 | [memory.py](../rococoach/memory.py)、[session.py](../rococoach/session.py) | 完成对话、显式偏好、失败草稿排除 |
| 流式与复盘 | [live_ui.py](../rococoach/live_ui.py)、[streaming.py](../rococoach/streaming.py)、[review_jobs.py](../rococoach/review_jobs.py) | 请求生命周期、草稿检查点与后台结果保存 |
| 引擎与进阶 | [bridge.cjs](../engine/bridge.cjs)、[battle.py](../rococoach/battle.py) | 固定组件结算、公开策略与版本化重放 |
| 像素伙伴 | [mascot.py](../rococoach/mascot.py) | 实际事件映射、保存后完成、动作开关 |

提交前功能检查与本轮真实证据见[FINAL_ACCEPTANCE](FINAL_ACCEPTANCE.md)。项目讲解可参考[讲解路线](INTERVIEW_PLAYBOOK.md)和[常见问题](INTERVIEW_NOTES.md)。

## 三个关键设计问题

**为什么不让模型直接控制一切？** 模型理解语境并提出计划，应用程序限制能力和参数、检查操作结果检查并提交状态。语义错误仍可能发生，但不能直接变成任意代码或数据库写入。

**流式已经显示后为什么还会消失？** 根因涉及显示过滤、片段重绘和末尾校验覆盖。修复重点是同一请求的消息生命周期与持久化，不只是开启 SDK 的 stream 参数。详见[生命周期说明](RESPONSE_LIFECYCLE.md)。

**如何证明有用？** 目前证明流程、契约及少量真实链路。227 项程序回归、14 题意图探索和 20 题检索回归各有不同边界；未证明玩家学习迁移或留存提升，下一轮优先做独立评审与玩家实验。

当前结果统一见 [VALIDATION.md](VALIDATION.md)。历史阶段数量与原始失败证据保留，不累加、不追溯改写。
