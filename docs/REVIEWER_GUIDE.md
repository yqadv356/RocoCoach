# 面试官阅读导航

本项目主攻老师的教学流程闭环：整局练习、证据复盘与下一局训练目标。军师和陪聊融合在同一入口。当前代码、初稿与本页共同说明交付范围；测试数量不代表回答正确率或真实学习收益。

## 五分钟演示

1. 按README安装依赖。无密钥先验证规则演示；真实LLM需在自己的本地.env填写配置。
2. 从均衡训练开始，观察回合引导，自主选择招式并写一句理由，实际执行。招式次数来自引擎，局中不展示最佳行动排名。
3. 完成整局，先看即时赛果，再看后台教师复盘。模型服务有实际等待，正文按提供商真实流输出。
4. 赛后问“第二回合换成撞击会怎样”，展开实际执行记录，查看独立单回合重放结果和未改变主局的凭据；没有发生第二回合就换成已发生回合。
5. 要求下一场进阶训练，或先询问方案后确认，检查第1回合和实际执行反馈。要求之后讲短一点，确认档案偏好改变而不是重开。

依赖网络的现场演示可能失败。可打开随附的真实合成证据讲解，但需说明是历史记录；没有密钥的规则演示不能称为真实模型决策。

## 关键代码

| 关注点 | 阅读入口 | 建议核查 |
| --- | --- | --- |
| 整局与教学信息边界 | rococoach/match.py、match_coach.py | 引导不代打；快照区分出招前后；实际理由与回合引用 |
| 在线语义与指代 | rococoach/semantic_control.py | IntentPlan、受限上下文、结构化待办、含糊替换复核 |
| 实际执行与保存 | rococoach/control.py | 参数、后置条件、token、请求幂等与事务合并 |
| 有限原生工具循环 | rococoach/agent.py、match_tools.py | 预算、阶段权限、真实观察、只读分支与引用检查 |
| RAG | rococoach/retrieval.py、data/rag_corpus.json | 版本/哈希、候选分数、未知范围与Top-2 |
| 上下文与档案 | rococoach/memory.py、session.py | 完成对话、显式偏好、失败草稿排除 |
| 流式与复盘 | rococoach/live_ui.py、streaming.py、review_jobs.py、pages/0_AI教练.py | 同一请求状态、可见草稿检查点、后台结果持久化 |
| 引擎与进阶 | engine/bridge.cjs、rococoach/battle.py | 不自研结算公式、不偷看行动、策略与规则版本重放 |

## 当前证据及其局限

- 本机完整回归：227项通过94.45秒，含发布检查与像素伙伴状态测试。测试替身用于协议和故障边界，不代表模型语义能力；之后发布检查与报告另列，不混成同一指标。
- `semantic-actions-live-evidence.json`：真实模型、独立临时SQLite、合成局。直接进阶2.143秒，提议确认3.431秒，实际创建和保存均通过。
- `semantic-intent-probe-evidence.json` 与 `semantic-intent-probe-normalized-evidence.json`：同一14项探索集，两次均13/14；第一轮等价类型、第二轮含糊重试失败均保留。非独立盲测。
- `active-replacement-check-evidence.json`：真实二次语义核对两例，未执行开局，不作为泛化保证。
- `rag-evaluation.json`、`rag-evaluation-final.json`：首次检查与修正后回归保留；人工20题、16可答/4越界。Hit@2不是最终回答正确率。
- `async-review-prefetch-json-live-evidence.json`：独立真实后台复盘，单样例首正文1.490秒、核验10.331秒；不证明P95或所有解释正确。
- `semantic-agent-execution-preview.png`：合成局、真实语义规划执行后页面及刷新验证；原用户私人档案未用于公开演示。

设计取舍见 `SUBMISSION_DRAFT.md`，智能体细节见 `AGENT_EXECUTION_DESIGN.md`，检索对照见 `RAG_IMPLEMENTATION.md`。开发工作区保留全部BUILD_LOG阶段记录；公开包仅选择经过检查的说明和合成证据，避免上传私人截图、原始对局及本机诊断。

## 后续最有价值的工作

冻结版本后，由不同作者标注多轮指代、混合请求和教学反馈；观察意图、实际动作、证据蕴含、延迟和用量。再做玩家独立判断到下一局迁移的评估。没有这些证据前，不宣称胜率提高、自适应课程或生产可靠性。

原创洛洛像素表现层的后续预览见MASCOT_DESIGN.md；对应UI截图使用独立模拟事件，不冒充真实模型新增成绩。
