# AGENTS.md

这是「Codex + DeepSeek Harness」共享的交接文件。两个代理不共享会话记忆，切换代理时请先读本文件，并在干完一段后更新「进度与待办」，避免让对方重新讲一遍上下文。

## 工作区地图

- 机器人 / 仿真（Python + MuJoCo，conda 环境 `mujoco`）：`outdoor_scene.py`、`outdoor_rescue_demo.py`、`rescue_collapse_demo.py`、`car.py`、`terrain.png`
- 论文阅读（LLM / 异构多机器人）：`papers/`，配套 skill 在 `skills/paper-reader`
- Java 课程作业：`PerpetualCalendar.java`
- 其他：`README.md`、`scripts/extract_papers.py`

## 环境约定

- Python 解释器：`C:/Users/18967/anaconda3/envs/mujoco/python.exe`（conda 环境 `mujoco`）
- Codex 当前模型：DeepSeek（`deepseek-v4-pro`，配置见 `~/.codex/config.toml`）

## 协作约定

1. 一个任务由一个代理主责；另一个代理只在最后复查改动（看 diff、找逻辑错误），不要同时修改同一批文件。
2. 每个代理干完一段，在「进度与待办」里补一条：做了什么、下一步是什么。
3. 切换代理时先读本文件。

## 进度与待办

- 待办：
  - 等 Codex 提交或给出 diff 范围后做逐行复查（当前 `3cc5c47` 之后无已跟踪改动，暂时没有 diff 可看）。
  - 仓库卫生（建议 Codex 主责，DSH 只复查）：仓库根目录的忽略文件叫 `gitignore`（缺少前导点），因此只写了 `.env` 的规则并未生效；`debug.log`、`MUJOCO_LOG.TXT`、`__pycache__/`、`.vscode/` 也没被忽略。
  - 脚本、papers、`AGENTS.md` 全部处于未跟踪状态，存在丢失风险，建议分批 `git add` 提交。
- 进行中：
- 已完成：
  - 2026-10-20 DSH 接手：已读本文件并确认分工（Codex 主责仓库内代码读写与执行；DSH 主责复查 Codex 改动、Office/自动化、Codex 不擅长的活）。现状核查：`git ls-files` 只跟踪 `README.md` 与 `skills/paper-reader/*`，`3cc5c47` 之后所有脚本、papers、`AGENTS.md` 均为未跟踪（`??`），当前没有「Codex 的 diff」可复查。环境已核实：`mujoco` 环境可用（Python 3.9.25 / mujoco 3.3.2 / numpy 2.0.2）。下一步：等 Codex 提交或给出 diff 范围后做逐行复查；DSH 的会话工作区仍指向 `default-workspace`，写仓库文件需每次审批。
  - 2026-10-20 DSH 确认定位（第二轮）：DSH 定位 = ①复查 Codex 改动/找 bug ②Office、浏览器/电脑自动化、DSH 插件 ③Codex 不擅长的活；同一任务单主责，另一方程只复查、不并行改同批文件。环境更新：DSH 当前工作目录已是仓库根 `C:\Users\18967\Desktop\git`，文件策略 `workspace-write`，改仓库内文件不再需要逐次审批（此前那条「指向 default-workspace」已过时）。已把仓库卫生问题与「无 diff 可复查」写入上方待办。下一步：等 Codex 的提交/diff 或用户指派 DSH 主责的任务。
