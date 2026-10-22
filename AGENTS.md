# AGENTS.md

这是「Codex + DeepSeek Harness」共享的交接文件。两个代理不共享会话记忆，切换代理时请先读本文件，并在干完一段后更新「进度与待办」，避免让对方重新讲一遍上下文。

## 工作区地图

- 机器人 / 仿真（Python + MuJoCo，conda 环境 `mujoco`）：`outdoor_scene.py`、`outdoor_rescue_demo.py`、`rescue_collapse_demo.py`、`car.py`、`terrain.png`
- 仿真素材（真实地形/岩石/废墟/车辆贴图，约 47 MB，**已 gitignore，不入库**）：`assets/`，索引见根目录 `ASSETS.md`，详解见 `assets/README.md`，工具链在 `assets/_tools/`
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
  - 素材包遗留缺口：缺救护车/消防车/工程车与真实半塌建筑——Poly Haven 没有，Sketchfab 的 CC0 车辆要登录后手工下载；废墟目前是程序化方盒，不是真建筑结构。
  - `assets/demo_rescue_scene.xml` 还没接进 `outdoor_scene.py` / `outdoor_rescue_demo.py`（那属于仓库代码改动，建议 Codex 主责，DSH 只提供素材与参数）。
  - 复查 Codex 的提交：`e6a27ba`（修 .gitignore）、`1eccf2f`（导入 MuJoCo 脚本/论文/AGENTS.md）。DSH 尚未逐行复查这两个 commit，下一步可做。
  - 仓库卫生：Codex 已修好根目录 `.gitignore`（补齐 `.env.*`、`*.log`、`MUJOCO_LOG.TXT`、`__pycache__/`、`.vscode/` 等），DSH 复查通过；磁盘上的 `debug.log`、`MUJOCO_LOG.TXT`、`__pycache__/` 仍在，但已被忽略，可选清理。
  - 脚本、papers、`AGENTS.md` 现已由 Codex 在 `1eccf2f` 入库（`git ls-files` 22 个文件），未跟踪风险解除。
- 进行中：
- 已完成：
  - 2026-10-22 DSH 主责交付：野外救灾场景素材包 `assets/`（47 MB，自带 `assets/.gitignore` 排除，只有 README 值得入库）。内容：①真实地形 `terrain/dem_wenchuan_200m.png`、`_400m.png`——AWS Terrarium 公开 DEM，坐标 31.055°N/103.483°E（汶川），落差 66.5/92.1 m；②Poly Haven CC0 扫描道具 10 件（boulder_01、rock_07、rock_moss_set_01、tree_stump_01、bark_debris_01、grass_medium_01、moss_01、covered_car、concrete_road_barrier、old_tyre）+ 3 张可平铺地面贴图；③`demo_rescue_scene.xml`：hfield 地形 + 22 棵程序化针叶树 + 岩石/车/隔离墩 + 90 块废墟 + 3 块楼板，`render_scene.py` 渲过两版预览。工具链在 `assets/_tools/`（fetch_dem / fetch_ph_model / fetch_texture / build_scene / render_scene / preview）。
  - 2026-10-22 同日踩坑结论（重要，别再重复）：MuJoCo **不读 glTF**（Poly Haven 只有 glTF/FBX，故自写展平器）；`hfield size` 四个数必须全为正，`base=0` 直接报错，用 0.01；hfield PNG **第 0 行 = +Y**，行↔−y 搞反会让人物浮空；MuJoCo 把 16 位 PNG 压回 8 位，66 m 落差必然有台阶，靠抖动掩盖；Terrarium 最高 z15（约 4.1 m/px），要 1 m 得换 Copernicus/USGS GeoTIFF + GDAL；`fir_tree_01` 有 698 万面，降面后成灰团，**照片扫描树在 MuJoCo 里不可用**。
  - 2026-10-22 文档三层落地并提交：根 `README.md`（入口表）、`ASSETS.md`（素材索引与硬约束）、`assets/README.md`（详解）、`.github/copilot-instructions.md`（VS Code Copilot 自动加载的分工约定）；`assets/.gitignore` 只放行 README 与自身，47 MB 素材不入库。提交后工作区干净。
  - 2026-10-22 环境（网络）结论：PowerShell/curl/git 默认走 SChannel 全部报 `SEC_E_NO_CREDENTIALS`；可用通道 = anaconda `python.exe`（自带 PIL/requests/numpy）、`git -c http.sslBackend=openssl`；`raw.githubusercontent.com` 直连超时，走 `ghfast.top` 或 `cdn.jsdelivr.net`；`huggingface.co` DNS 失败，用 `hf-mirror.com`。
  - 2026-10-20 DSH 接手：已读本文件并确认分工（Codex 主责仓库内代码读写与执行；DSH 主责复查 Codex 改动、Office/自动化、Codex 不擅长的活）。现状核查：`git ls-files` 只跟踪 `README.md` 与 `skills/paper-reader/*`，`3cc5c47` 之后所有脚本、papers、`AGENTS.md` 均为未跟踪（`??`），当前没有「Codex 的 diff」可复查。环境已核实：`mujoco` 环境可用（Python 3.9.25 / mujoco 3.3.2 / numpy 2.0.2）。下一步：等 Codex 提交或给出 diff 范围后做逐行复查；DSH 的会话工作区仍指向 `default-workspace`，写仓库文件需每次审批。
  - 2026-10-20 DSH 确认定位（第二轮）：DSH 定位 = ①复查 Codex 改动/找 bug ②Office、浏览器/电脑自动化、DSH 插件 ③Codex 不擅长的活；同一任务单主责，另一方程只复查、不并行改同批文件。环境更新：DSH 当前工作目录已是仓库根 `C:\Users\18967\Desktop\git`，文件策略 `workspace-write`，改仓库内文件不再需要逐次审批（此前那条「指向 default-workspace」已过时）。已把仓库卫生问题与「无 diff 可复查」写入上方待办。下一步：等 Codex 的提交/diff 或用户指派 DSH 主责的任务。
