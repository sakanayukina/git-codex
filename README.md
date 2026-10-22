# git-codex

MuJoCo 机器人 / 野外救灾仿真 + 论文阅读 + Java 作业的共用工作区。

## 先看这几个文件

| 文件 | 作用 |
|---|---|
| [AGENTS.md](AGENTS.md) | **协作交接文件**：Codex 与 DeepSeek Harness 的分工、进度与待办。任何代理/人接手先读这个 |
| [ASSETS.md](ASSETS.md) | 仿真素材索引：真实地形 DEM、岩石/废墟/车辆扫描件、生成脚本与用法 |
| [assets/README.md](assets/README.md) | 素材详解：来源、CC0 授权、踩过的坑（glTF 转换、hfield 方向/精度、树的面数） |

## 环境

- Python：`C:/Users/18967/anaconda3/envs/mujoco/python.exe`（conda 环境 `mujoco`，MuJoCo 3.3.2）
- 另有 anaconda base 环境带 PIL/requests，处理图片与贴图时用它

## 目录

- 仿真：`outdoor_scene.py`、`outdoor_rescue_demo.py`、`rescue_collapse_demo.py`、`car.py`
- 素材：`assets/`（约 47 MB，已 gitignore，不入库）
- 论文：`papers/` + `skills/paper-reader`
- 其他：`PerpetualCalendar.java`、`scripts/extract_papers.py`
