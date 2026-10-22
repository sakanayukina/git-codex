# git-codex

MuJoCo 野外救灾仿真 + 论文阅读 + Java 作业的共用工作区。

## 先看这几个文件

| 文件 | 作用 |
|---|---|
| [AGENTS.md](AGENTS.md) | **协作交接文件**：分工、当前状态、关键结论、下一步。接手先读 |
| [ASSETS.md](ASSETS.md) | 场景素材索引：文件清单、授权、常用命令、硬约束 |
| [assets/README.md](assets/README.md) | 素材详解与踩坑记录（glTF 转换、hfield、树的面数） |

## 环境

| 用途 | 解释器 |
|---|---|
| 仿真、渲染 | `C:/Users/18967/anaconda3/envs/mujoco/python.exe`（MuJoCo 3.3.2） |
| 生成场景、图片处理 | `C:/Users/18967/anaconda3/python.exe`（带 PIL/requests） |

## 目录

- 场景入口：`outdoor_scene.py` / `run_scene.py`（加载 `assets/demo_v6.xml`，缺失时回退程序化场景）
- 场景生成：`assets/_tools/`（见 AGENTS.md 的生成链）
- 素材：`assets/`（约 82 MB，已 gitignore，不入库）
- 论文：`papers/` + `skills/paper-reader`
- 其他：`PerpetualCalendar.java`、`scripts/extract_papers.py`

```powershell
# 看一眼现在的场景
& "C:/Users/18967/anaconda3/envs/mujoco/python.exe" run_scene.py
```
