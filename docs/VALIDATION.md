# 验证结果与证据口径

更新于 2026年10月31日。本文集中维护当前结果；历史专题文档中的测试数量只代表对应阶段，不累加为当前成绩。

本轮提交前功能复查见[FINAL_ACCEPTANCE](FINAL_ACCEPTANCE.md)，含真实调用与浏览器检查。

## 程序回归

| 环境 | 版本或阶段 | 结果 | 证据 |
| --- | --- | --- | --- |
| GitHub 全新 Ubuntu runner，Python 3.12、Node 24 | 发布基线 `4c2f381d80c963b195ad8e077ef1577dfb59a8c5` | 227 passed in 196.61s；Python 依赖及引擎安装均成功 | [Actions 41082691035](https://github.com/yqadv356/RocoCoach/actions/runs/41082691035) |
| GitHub全新Linux环境 | 材料优化版本 `0d527af` | 227 passed in 187.28s | [Actions 41085984657](https://github.com/yqadv356/RocoCoach/actions/runs/41085984657) |
| GitHub 全新 Ubuntu runner | 当前公开实现基线 `43fba453a6a93bd9061cf9f79db34ffdf7de89e9` | 227 passed in 117.42s | [Actions 41144977412](https://github.com/yqadv356/RocoCoach/actions/runs/41144977412) |
| 本地macOS | 2026年10月31日提交前复查 | 227 passed in 83.85s | 见FINAL_ACCEPTANCE；非新机器验证 |

云端基线结果固定关联该提交，不自动代表后续改动；[最新工作流](https://github.com/yqadv356/RocoCoach/actions/workflows/tests.yml)展示后续运行。自动化包含模型替身，覆盖程序契约与故障边界，不能称为 227 条真实模型回答正确。

主要覆盖：引擎结算、合法行动、次数耗尽、同配置重放、阶段工具权限、引用、上下文筛选、待办失效、事务冲突、请求幂等、失败草稿保留与像素事件映射。

## 真实模型与网页链路

| 项目 | 观察结果 | 证据与限制 |
| --- | --- | --- |
| 真实千问操作两例 | 直接进阶 2.143 秒；提议确认 3.431 秒；实际创建并保存新局 | [执行证据](semantic-actions-live-evidence.json)；临时数据库与合成局，不是总体延迟或成功率 |
| 14 项真实语义探索两轮 | 两轮均 13/14 | [首轮](semantic-intent-probe-evidence.json)、[重测](semantic-intent-probe-normalized-evidence.json)；同作者探索集，非独立盲测，保留含糊重试误判 |
| 替换未结束整局的语义复核 | 两例分别判定不直接替换、允许明确替换 | [复核证据](active-replacement-check-evidence.json)；未执行开局，不作为泛化保证 |
| 上下文确认到实际开局 | 网页切换进阶新局，刷新保持 | [截图](semantic-agent-execution-preview.png)；合成历史、真实语义规划，不含私人档案 |
| 后台复盘单样例 | 首正文 1.490 秒，核验 10.331 秒 | [原始证据](async-review-prefetch-json-live-evidence.json)；真实流式路径，不是 P95 或加速倍数 |
| 像素伙伴与布局 | 四态、失败保留、后台片段、动作开关与两个桌面视口 | [界面证据](lolo-ui-evidence.json)；模拟模型事件，不是新增真实 LLM 评测 |

## 提交前真实模型样例的语义问题

以下是与早期探索分开的提交前验收批次，数值由原始 JSON 交叉核对：

- [开局与确认](final-semantic-actions-evidence.json)：实际创建并保存检查通过，4.425 秒和 7.260 秒。
- [关键回合与换招](final-match-tools-evidence.json)：关键回合查询依次 find_key_turns、inspect_round(7)、inspect_round(8)、inspect_round(1)，4 次模型、4 次工具，16.769 秒。另一问使用实际引擎重放第 2 回合，主局不变。
- [后台复盘](final-async-review-evidence.json)：首正文 4.458 秒、最终程序核验 11.625 秒，110 次草稿更新。**此样例存在语义错误**：模型把 Torrent（激流）写成“猛火”，并用它解释咬住优势；固定 Showdown 的 Torrent 增强水属性攻击，Blaze 才增强火属性。PokeAPI 官方名称表中 ability_id 67 / 66 分别对应激流 / 猛火。模型还混用了第 6 回合开始与结束的生命值：实际开始 65／18、结束 46／0。以某招“直接决定胜势”作因果结论也缺乏反事实比较支持。
- [偏好与聊天](final-chat-style-evidence.json)：风格保存 4.589 秒，对局未重开；闲聊没有改变战局，不据此宣称自然度或情绪价值已通过评测。

必须分开判断工具执行、证据引用与结构、自然语言解释。`validated_final` 只表示通过当前程序契约，不能作为机制语义正确的证明。原始 JSON 不改写；下一步应补机制名称一致性检查、证据充分性评估和独立人工标注。正式稿只陈述这些已观察事实，不为美化文稿增加真实模型调用。

名称来源：[PokeAPI ability_names.csv](https://github.com/PokeAPI/pokeapi/blob/master/data/v2/csv/ability_names.csv)；机制核对使用本机锁定的 pokemon-showdown@0.11.11 Dex。单次时延不是 P95，程序回归含替身，检索命中与玩家教学收益另行评估。

## RAG 对照

相同 20 个人工合成问题：16 个可答、4 个未覆盖。Hit@2 表示前两条中至少有一条预先标注的相关资料。

| 方法 | 可答 Hit@2 | 未覆盖返回空 |
| --- | --- | --- |
| 4 条资料与原关键词 | 5/16 | 2/4 |
| 26 条资料与原关键词 | 12/16 | 2/4 |
| 新检索首次对应版本 | 15/16 | 4/4 |
| 修正后同题回归 | 16/16 | 4/4 |

首次失败见 [rag-evaluation.json](rag-evaluation.json)，修正后见 [rag-evaluation-final.json](rag-evaluation-final.json)。留出题已用于修正，后续不能继续称为独立留出成绩。结果同时受语料扩展、实体筛选和排序影响，不能把全部提升归因于 BM25。指标不证明答案准确率或教学收益。

## 尚未验证

没有外部独立标注的多轮语义评测、真实玩家学习迁移实验、胜率或留存实验、延迟分位数、完整费用统计，以及多用户并发、跨设备和 Windows 全流程验证。程序校验能证明状态、阶段与引用契约，不能证明所有自然语言解释正确。
