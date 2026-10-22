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
  - **DSH 刚接入真实枫树**：Sketchfab "Maple Tree" by Atrodler（**CC-BY，论文里必须署名**），12,427 面，按材质拆成 `maple_sugar_maple_bark.obj` + `maple_sugar_maple_leaf.obj`，`village.py` 随机种 30 棵混在针叶林里。已知不足：近看树叶发白点（单面片 + 法线朝上），要更好需翻面/复制双面几何。
  - 根目录 `maple_tree.zip` 被占用删不掉（浏览器/杀软持有句柄），用户手动删即可，**别提交**。
  - **村落布局已就绪（v6）**：`assets/demo_v6.xml` = 5 栋房（H1 主塌 / H2、H5 半损 / H3、H4 完好）+ 土路 ribbon 网格 + 集结点 P0 + 西北坡加密林；每栋房有 `<site name="site_H*">` 标记，任务分配算法直接读坐标。相机：`village`（村口）、`top`（俯视，可当论文布局图）。
  - **房子是插槽**：改 `assets/buildings.json` 的 `model` 字段就能换真实模型（放 `assets/props/buildings/<名>/<名>.obj` + `_diffuse.png`），跑 `assets/_tools/village.py` 重生成。`model_house()` 目前是纯视觉（`contype=0`），要参与物理需补简化 box 代理。
  - 当前 `assets/buildings.json` 的 5 栋房 `model` 均为空，仍是程序化占位房；下一步可用 Poly Haven CC0 建筑立面或 Sketchfab CC0 废墟替换。
  - 道路：`assets/_tools/roadgen.py` 把折线重采样成 ribbon 网格（OBJ+UV，贴地 0.05 m）；踩坑：OBJ 面索引必须从 1 开始，否则 MuJoCo 报 `could not parse OBJ file`。
  - `build_scene.py` 的 `--ground-tex` 默认值已由 Codex 改为 `leafy_grass`；`forest_floor` 贴图仍保留在 `assets/tex/`。
  - **复查发现（给 Codex）**：`build_scene.py` 把 `--ground-tex` 默认值改成 `forest_floor` 后，全场景偏沙黄（那张贴图是干枯落叶土），配合暖色主光（diffuse 1.0 0.87 0.70）像沙漠，不像川西林地。已验证：换 `leafy_grass` + 绿色 rgba 立刻变回草地。另：废墟/楼板原本是纯白 rgba，无贴图时过曝成白纸片，可用 `_tools/tune.py` 换成混凝土贴图。
  - 已产出对照：`assets/demo_v2.xml`（混凝土 + 降曝）、`demo_v4.xml`（再换绿地面）、**`demo_v5.xml`（加密植被 + 程序化半塌砖房 + 房屋专用相机 `house`）**；渲染图 `_now_wide.png` / `_v2_wide.png` / `_v4_wide.png` / `_v5_wide.png` / `_v5_house.png`；脚本 `_tools/tune.py`（材质/曝光）、`_tools/scatter.py`（加密 + 建房）。
  - 房子做法（`scatter.py::house`）：8.4×6.2 m、墙高 3 m，砖墙贴图 + 混凝土楼板；南北墙留窗洞/门洞，东墙塌一段、西墙剩半截，两块楼板斜搭在墙上，室内外各堆碎块。**仍是"方盒拼接"，结构对、细节假**；要更像需要真扫描建筑模型。
  - 草的问题：`props/ground/grass_medium_01` 是扁平扫描草皮（5.6×0.33×0.34 m），铺多了侧看像"灰刺"，已从场景撤掉。MuJoCo 无 GPU 实例化、无 alpha 剪裁，几何草只能靠 Blender 散布后合并成单一 mesh，或干脆用地面贴图。
  - 二次坍塌触发逻辑与救援机器人接入尚未做（`outdoor_rescue_demo.py` 仍是早期程序化场景）。
  - 复查 Codex 的提交：`e6a27ba`（修 .gitignore）、`1eccf2f`（导入 MuJoCo 脚本/论文/AGENTS.md）。DSH 尚未逐行复查这两个 commit，下一步可做。
  - 仓库卫生：Codex 已修好根目录 `.gitignore`（补齐 `.env.*`、`*.log`、`MUJOCO_LOG.TXT`、`__pycache__/`、`.vscode/` 等），DSH 复查通过；磁盘上的 `debug.log`、`MUJOCO_LOG.TXT`、`__pycache__/` 仍在，但已被忽略，可选清理。
  - 脚本、papers、`AGENTS.md` 现已由 Codex 在 `1eccf2f` 入库（`git ls-files` 22 个文件），未跟踪风险解除。
- 进行中：
- 已完成：
  - 2026-10-22 **DSH 复查发现严重 bug 并修复**：`fetch_ph_model.py` 用 `np.savetxt(fmt="f %d/%d/%d")` 写面，把一行的**三个顶点索引**当成一个顶点的 `v/vt/vn`（写出 `f 132/130/111`），MuJoCo 读到的是退化面。受影响资产共 **442,644 个坏面**：`covered_car`、`concrete_road_barrier`、`old_tyre`、`bark_debris_01`、`tree_stump_01`、`grass_medium_01`、`moss_01`、公寓立面。已就地修复并改正生成器（逐面写 `f a/a b/b c/c`）；新增 `_tools/fix_obj_faces.py`（`--check` / `--fix`），以后下完模型先跑一遍。修复后 `covered_car` 才真的像盖着布的车。
  - 2026-10-22 新增 `_tools/import_building.py`：一条命令把下载来的建筑模型接进场景——自动找主 obj、量尺寸数面、jpg→png、按 `--target-height`/`--scale` 归一化、生成 `snippet.xml`；`--plot H2` 时直接写回 `buildings.json` 的 `model`/`model_scale`。`village.py` 已支持 `model_scale`。
  - 2026-10-22 Codex 接入：`outdoor_scene.py` / `run_scene.py` 已切到 `assets/demo_v6.xml`（504 body / 1268 geom / 5 相机），`outdoor_scene.py` 在文件不存在时回退到程序化场景；`build_scene.py` 的 `--ground-tex` 默认值改为 `leafy_grass`。两个入口 `--headless` 验证通过（未提交，待 DSH 复查）。
  - 2026-10-22 DSH 主责交付：野外救灾场景素材包 `assets/`（47 MB，自带 `assets/.gitignore` 排除，只有 README 值得入库）。内容：①真实地形 `terrain/dem_wenchuan_200m.png`、`_400m.png`——AWS Terrarium 公开 DEM，坐标 31.055°N/103.483°E（汶川），落差 66.5/92.1 m；②Poly Haven CC0 扫描道具 10 件（boulder_01、rock_07、rock_moss_set_01、tree_stump_01、bark_debris_01、grass_medium_01、moss_01、covered_car、concrete_road_barrier、old_tyre）+ 3 张可平铺地面贴图；③`demo_rescue_scene.xml`：hfield 地形 + 22 棵程序化针叶树 + 岩石/车/隔离墩 + 90 块废墟 + 3 块楼板，`render_scene.py` 渲过两版预览。工具链在 `assets/_tools/`（fetch_dem / fetch_ph_model / fetch_texture / build_scene / render_scene / preview）。
  - 2026-10-22 同日踩坑结论（重要，别再重复）：MuJoCo **不读 glTF**（Poly Haven 只有 glTF/FBX，故自写展平器）；`hfield size` 四个数必须全为正，`base=0` 直接报错，用 0.01；hfield PNG **第 0 行 = +Y**，行↔−y 搞反会让人物浮空；MuJoCo 把 16 位 PNG 压回 8 位，66 m 落差必然有台阶，靠抖动掩盖；Terrarium 最高 z15（约 4.1 m/px），要 1 m 得换 Copernicus/USGS GeoTIFF + GDAL；`fir_tree_01` 有 698 万面，降面后成灰团，**照片扫描树在 MuJoCo 里不可用**。
  - 2026-10-22 文档三层落地并提交：根 `README.md`（入口表）、`ASSETS.md`（素材索引与硬约束）、`assets/README.md`（详解）、`.github/copilot-instructions.md`（VS Code Copilot 自动加载的分工约定）；`assets/.gitignore` 只放行 README 与自身，47 MB 素材不入库。提交后工作区干净。
  - 2026-10-22 **实测：MuJoCo 3.3.2 没有 PBR 渲染**。`<material metallic= roughness=>` 与 `<layer role="normal|occlusion|roughness|metallic">` 都能编译、`mat_metallic/mat_roughness` 也进了模型，但渲染像素差**严格为 0**（贴法线图与不贴完全一样）；`specular/shininess` 只有 0.02 的均值差。可用光照手段只有：albedo 贴图、`specular/shininess`、`reflectance`（天空盒反射）、`castshadow`、`<visual><quality shadowsize>`、`fog/haze`、天空盒渐变。给用户做真实感的正确方向是**把 AO 烘焙进 albedo + 抬高贴图分辨率 + 阴影贴图 + 多光源**，不要再花时间找 PBR 套件。另注意：连续创建 `mujoco.Renderer` 不 `close()` 会因 GL 上下文泄漏让后续渲染全黑（曾被这个坑误导过一次）。
  - 2026-10-22 参考：论文场景取材（已存 `assets/_refs/`，被 gitignore）。PGTT(IROS 2026, arXiv:2510.18348) 的 MuJoCo 训练场景就是**灰色方块台阶 + 纯色背景**，没有植被与贴图；`Eterith/blender-mujoco-terrain` 提供 Blender 地形网格→MuJoCo hfield 的转换。
  - 2026-10-22 环境（网络）结论：PowerShell/curl/git 默认走 SChannel 全部报 `SEC_E_NO_CREDENTIALS`；可用通道 = anaconda `python.exe`（自带 PIL/requests/numpy）、`git -c http.sslBackend=openssl`；`raw.githubusercontent.com` 直连超时，走 `ghfast.top` 或 `cdn.jsdelivr.net`；`huggingface.co` DNS 失败，用 `hf-mirror.com`。
  - 2026-10-20 DSH 接手：已读本文件并确认分工（Codex 主责仓库内代码读写与执行；DSH 主责复查 Codex 改动、Office/自动化、Codex 不擅长的活）。现状核查：`git ls-files` 只跟踪 `README.md` 与 `skills/paper-reader/*`，`3cc5c47` 之后所有脚本、papers、`AGENTS.md` 均为未跟踪（`??`），当前没有「Codex 的 diff」可复查。环境已核实：`mujoco` 环境可用（Python 3.9.25 / mujoco 3.3.2 / numpy 2.0.2）。下一步：等 Codex 提交或给出 diff 范围后做逐行复查；DSH 的会话工作区仍指向 `default-workspace`，写仓库文件需每次审批。
  - 2026-10-20 DSH 确认定位（第二轮）：DSH 定位 = ①复查 Codex 改动/找 bug ②Office、浏览器/电脑自动化、DSH 插件 ③Codex 不擅长的活；同一任务单主责，另一方程只复查、不并行改同批文件。环境更新：DSH 当前工作目录已是仓库根 `C:\Users\18967\Desktop\git`，文件策略 `workspace-write`，改仓库内文件不再需要逐次审批（此前那条「指向 default-workspace」已过时）。已把仓库卫生问题与「无 diff 可复查」写入上方待办。下一步：等 Codex 的提交/diff 或用户指派 DSH 主责的任务。
