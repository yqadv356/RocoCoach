# 材料怎样提交和运行

建议提交一份PDF，并附GitHub仓库链接。面试官先读设计、难点和方案，需要复查时再看源码、Demo和验证证据。Word作为可编辑备份，不必和PDF一起重复阅读。

仓库：https://github.com/yqadv356/RocoCoach

## 提交内容

- PDF说明书：题目对齐、玩家流程、架构、Agent、RAG与上下文、实际难点、方案、验证和后续。
- 可运行Demo：仓库中的Streamlit项目，包含离线模式与真实模型配置示例。
- 验证说明：[提交前检查](FINAL_ACCEPTANCE.md)列出各功能怎样测、测到了什么；[原始证据](VALIDATION.md)按来源分开。
- 备份：Word和排除密钥、私人记录、依赖目录后的源码包。

不要把本机127.0.0.1当作公开演示链接发给面试官。当前提供本地可运行Demo，没有部署公共在线服务。

## Demo运行

需要Python 3.12、Node.js 24、pnpm 11。macOS/Linux操作：

```sh
git clone https://github.com/yqadv356/RocoCoach.git
cd RocoCoach
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python scripts/setup_battle.py
python -m streamlit run app.py --server.address 127.0.0.1
```

启动后在自己电脑打开 http://127.0.0.1:8501 。Windows未完整验证。无密钥时使用明确标记的规则演示，能体验对战与保存，但不代表真实LLM。

真实模型：复制.env.example为本地.env，填写账户可用的模型和密钥，参考[首页配置](../README.md)。项目实测千问兼容接口；调用有费用，密钥不要提交或发给他人。

## 五分钟验收

开始均衡训练，查看提示并自主选招；完成整局后查看复盘和下局目标；赛后追问某个已发生回合换招会怎样，展开实际工具记录；在聊天中请求进阶新局，并查看第1回合和实际保存反馈。再要求以后讲短一些，确认偏好变化且对局未重开。

规则演示与真实模型测试分开，网络失败时可查看仓库里的已保存合成证据，不冒称现场响应。程序回归可运行 `python -m pytest -q`。

## 提交文字参考

您好，现提交“基于LLM的智能AI Coach”项目RocoCoach。

本项目优先完成老师的教学流程：整局练习、回合前引导、自主决策、赛后证据复盘和下一局训练目标，军师与陪练融入统一聊天入口。PDF说明了设计取舍、实现难点、解决方案和验证结果；公开仓库提供可运行Demo、源码、安装说明与测试记录。

仓库：https://github.com/yqadv356/RocoCoach

建议先阅读PDF，需要复查时可按仓库说明运行Demo。项目复用公开对战引擎，未接入真实洛克王国接口；已实现内容和待验证边界在材料中分别说明。感谢审阅。
