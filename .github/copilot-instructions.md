# Copilot / VS Code 工作约定

本仓库由 **Codex** 与 **DeepSeek Harness** 两个代理协作维护，二者不共享记忆。
**动手前先读 [AGENTS.md](../AGENTS.md)**（协作分工 + 进度与待办），素材相关先读 [ASSETS.md](../ASSETS.md)。

要点：

- 仓库内代码读写与执行 → **Codex 主责**；另一个代理只在最后复查（看 diff、找逻辑错误），**不要同时改同一批文件**。
- 一个大任务只有一个主责；干完一段就在 `AGENTS.md` 的「进度与待办」里补一条：做了什么、下一步是什么。
- Python 解释器：`C:/Users/18967/anaconda3/envs/mujoco/python.exe`（conda 环境 `mujoco`）。
- 仿真素材在 `assets/`（约 47 MB，**已被 `.gitignore` 排除，不要提交**）；`assets/README.md` 有来源、授权与踩坑记录。
