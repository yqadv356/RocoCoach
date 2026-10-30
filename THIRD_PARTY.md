# 第三方组件与复用边界

核查与安装日期：2026-10-29。以下版本是实际安装的 npm 发布包，不是直接依赖可变化的 GitHub 主分支。

| 组件 | 版本 / 发布关联提交 | 本项目使用内容 | 许可证记录 |
| --- | --- | --- | --- |
| [Pokémon Showdown](https://github.com/smogon/pokemon-showdown) | 0.11.11 / 739a5e1fee432ad80ff7136d70cca993be358b59 | Battle 回合结算、RandomPlayerAI、Dex 技能/属性资料 | MIT；原文见 docs/licenses/pokemon-showdown-LICENSE.txt |
| [Smogon Damage Calculator](https://github.com/smogon/damage-calc) | 0.12.0 / d7a69cf40616057ef40faf7623df7a628e58b535 | Pokemon/Move 对象与 calculate 伤害区间 | MIT；原文见 docs/licenses/smogon-calc-LICENSE.txt |

作者署名与完整许可文本保留在 [Showdown 许可](docs/licenses/pokemon-showdown-LICENSE.txt) 和 [计算器许可](docs/licenses/smogon-calc-LICENSE.txt)。间接依赖及完整性校验值见 engine/pnpm-lock.yaml，各包保留自己的许可文件。node_modules 不进入 Git。

我们没有编写伤害公式、命中结算、状态异常规则、胜负判定或随机对手策略；调用现成组件实现这些能力。新增部分是 Python/Node 接口、固定教学场景、直接伤害排序展示、技能讲解页面、可重放历史、导出与集成测试。

军师的排序规则由我们新增：伤害区间均值乘标称命中率。它不是复制来的完整智能教练。老师页面复用技能事实与描述，我们新增展示和学习任务；它不是现成 LLM 教学代理。陪练则直接调用上游 RandomPlayerAI。

本轮未复制 poke-env、PokeLLMon、PokéChamp、洛克沙盘或 WQNF/langgraph 的实现。PokéChamp 所读 LICENSE 包含额外署名要求与日本地区限制，并非仅凭包元数据即可概括的标准 MIT 文本；PokeLLMon 本轮未查到根目录许可证，因此均未作为直接复用代码。

宝可梦名称和规则用于说明教学原型。第三方软件许可不应被表述为对所有游戏 IP 的授权。本项目没有导入官方美术、音频或洛克王国游戏资源，也不冒充官方产品。

中文名称复用：从[PokeAPI仓库CSV](https://github.com/PokeAPI/pokeapi/tree/master/data/v2/csv)筛选47项简体中文名称，缓存于data/zh_catalog.json，条目保留来源。完整BSD许可见docs/licenses/pokeapi-LICENSE.txt；本地显示翻译，不将其用于替代规则引擎。没有下载美术或音频。

RAG资料导出复用同一固定Showdown Dex，不导入其他游戏IP素材。26条语料保留原始事实、来源版本和条目哈希；原有Showdown MIT许可继续保留。BM25为本项目小型实现，参考Lucene公开公式说明，不包含或运行Lucene代码；未新增依赖。

## 掌机界面资源（2026-10-30）

实际复用[RPGUI](https://github.com/RonenNess/RPGUI)提交048859e6e1a73bd8f5615555609db098beba4e9c的灰色像素边框、按钮和剑图标。上游dist/LICENSE.txt为**zlib许可**，原文与文件校验表保存在assets/vendor/rpgui/LICENSE.txt、manifest.json；README注明默认主题图形为Buch（Michele Bucelli）的公有领域作品。handheld.css已修改用于Streamlit，并标注修改来源。未引入其JS/外部字体。新增场景CSS与宠物SVG示意图由本项目编写，不把它们宣传为官方精灵图或上游现成资产。调研但未使用Showdown客户端、NES.css和Kenney，完整取舍见docs/GAME_UI_RESEARCH.md。

## 洛洛原创教练形象（2026-10-30）

rococoach/mascot.py中的笔记精灵由本项目以SVG像素格编写，handheld.css增加四种事件状态的轻动画。未复制Codex内置宠物、美术或状态同步接口，不改变上述第三方许可，也不声称获得任何官方宠物资产授权。此次为网页表现层预览，没有接入桌面宠物服务。
