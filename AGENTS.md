# AGENTS.md

「Codex + DeepSeek Harness」共享的交接文件。两个代理不共享会话记忆，切换时先读本文件，干完一段更新「当前状态」与「下一步」。

## 工作区地图

- **仿真场景**：`assets/demo_v6.xml`（当前场景，344 body / 1108 geom / 10 相机 / 2.59 M 三角面，素材约 82 MB，gitignore 不入库）
- **生成链**：`assets/_tools/` — `build_scene.py`(拼地形) → `tune.py`(材质) → `scatter.py`(植被/废墟) → `village.py`(村落, base 是 `demo_v5.xml`)，`roadgen.py` 生成土路网格
- **导入链**：`convert_multi.py`(glTF/GLB 按材质拆分) → `import_gltf.py` / `import_building.py`(建筑) → `fix_obj_faces.py`(OBJ 体检)
- **渲染/清理**：`render_scene.py`、`preview_parts.py`、`cleanup.py`、`slim_rocks.py`（石头瘦身）、`bake_ground.py`（路烘进地面贴图）
- 其他：`papers/`（LLM/异构多机器人）、`skills/paper-reader`、`PerpetualCalendar.java`、`scripts/extract_papers.py`

## 环境

| 用途 | 解释器 |
|---|---|
| 仿真、加载/渲染 MJCF | `C:/Users/18967/anaconda3/envs/mujoco/python.exe`（MuJoCo 3.3.2） |
| 生成场景、图片处理（PIL/requests） | `C:/Users/18967/anaconda3/python.exe` |

`village.py` / `scatter.py` / `build_scene.py` 依赖 PIL，**必须用 base python 跑**；`render_scene.py` 必须用 mujoco 环境。

## 协作约定

1. 一个任务一个主责；另一方只复查（看 diff、找逻辑错误），不同时改同一批文件。
2. 干完一段就更新本文件。
3. 素材（`assets/props` 等）不入库，只有脚本、`buildings.json`、README 进 git。

## 当前状态（2026-10-22）

- **场景**：汶川 DEM 地形（200 m² / 落差 66.5 m）+ **7 个可搜索点**（H1 真实砖房废墟、H6 混凝土塌楼、H7 塌墙扫描件、H2–H5 占位房）+ 烘焙地面（主路 + 5 条入户支路）+ 24 块岩石 + 92 棵程序化针叶树 + 30 棵 Sketchfab 枫树 + 车辆（**2.59 M 三角面**，344 body / 1108 geom / 10 相机）
- **H1 = `collapsed_uk_terraced_house`**（22,631 面，15 材质分件、1 张 2K 图集），有不可见碰撞外壳（留 1.3 m 门洞）；H6 = `ruined_building.glb`（3,407 面，含瓦砾场）；H7 = `free_ruined_wall_3d_scan.glb`（670k→90k 面，塌墙）
- **已解决**：石头瘦身（8.61 M → 2.50 M）；道路改为烘焙进地面贴图（不再抖动）；GLB 内嵌贴图提取；扫描件减面 `--max-tris`
- **未解决**：① 树叶近看发白点（单面片）；② H2–H5 仍是程序化占位房；③ H6/H7 没碰撞
- **待素材（暂缓，用户先不找）**：H2/H5 的民房尺度废墟（6–10 m 宽、有门窗、≤25 万面）
- **用不上的素材**：`snowy_mountain_road_scene.zip`（雪山公路 kit）——雪地/标线季节不符；里面 ROAD_POLE 是「一排电线杆」跨度 35 m、CLIFF 的 zmin = −11 m（属于雪景已摆好的布景件，不是干净单体），已抽到 `props/imported/road_props/` 但**未入场景**
- 仓库根目录还有 `ruined_building.glb`、`free_ruined_wall_3d_scan.glb`、`snowy_mountain_road_scene.zip`，已转进 `props/imported/`，可删

## 给 Codex 的提醒

- `village.py` 每次重建都会把石头加回来 → 必须接着跑 `slim_rocks.py --keep 24 --drop-grass --apply --in-place`，否则三角面从 2.59 M 涨回 8.6 M
- 场景加载：`mujoco.MjModel.from_xml_path("assets/demo_v6.xml")`；入口 `outdoor_scene.py` / `run_scene.py` 已指向它
- 相机：`wide` / `close`(H1) / `village` / `top`(俯视) / `cam_H1`…`cam_H5`
- 可搜索点坐标读 `<site name="site_H1">`…`site_H7`、`site_P0`（`group=3`，不渲染）

## 关键结论（踩过的坑，别重复）

1. **MuJoCo 不读 glTF**，也不支持 Draco → 必须转 OBJ；`assets/_tools/fetch_ph_model.py` 可复用。
2. **hfield**：`size` 四个数必须全为正（`base=0` 报错，用 0.01）；PNG **第 0 行 = +Y**（行↔−y，搞反物体浮空）；只吃 8 位灰度，大落差靠抖动掩盖。
3. **MuJoCo 3.3.2 没有 PBR**：`metallic/roughness/<layer role="normal">` 能编译但渲染像素差为 0，只认 albedo + specular/shininess。别再找 PBR 套件。
4. **薄片 mesh 必须 `inertia="shell"`**，否则报 `mesh volume is too small`（树叶/草/栅栏都属此类）。
5. **OBJ 面索引从 1 开始**，且不能写 `f a/b/c`（会被当成一个顶点的 v/vt/vn）；生成器已修，历史文件用 `fix_obj_faces.py --fix` 修复过 44 万面。
6. **照片扫描树进不了 MuJoCo**（698 万面，降面后成灰团）；用低模 glTF（枫树 12.4k 面）才行。
7. **薄/a 透明面**：MuJoCo 无 alpha 裁剪，带 alpha 的贴图要合成到背景色再转 RGB。
8. **多材质模型**：一个图集常被十几个材质共用，导出时必须去重（曾 90 MB 变 4.3 MB）。
9. **相机/标记**：`site` 渲染成球很出戏 → `group="3"`；相机要避开门洞/墙体，否则近景全灰。
10. 连续创建 `mujoco.Renderer` 不 `close()` 会因 GL 上下文泄漏导致后续全黑。

## 下一步

1. **道路 v3 收尾**（DSH）：已改成烘焙贴图（不再抖动），但入户支路太淡、缺宽度变化与路缘、车辙不明显
2. **H2/H5 换真房子**：用户已暂缓（找到 6–10 m 宽、有门窗的民房废墟再说），`buildings.json` 的 `model` 已支持目录
3. **二次坍塌触发 + 机器人接入**（Codex 主责，DSH 复查）：DSH 出可塌结构与 `site_*` 命名规范

> 生成顺序：`village.py` 每次重建都会把石头加回来，跑完必须再执行
> `slim_rocks.py --keep 24 --drop-grass --apply --in-place`。

## 历史（一行一天）

- 2026-10-20 分工确立；仓库从 2 个 commit 扩到脚本/论文入库
- 2026-10-22 素材包 → 真实 DEM → 加密植被 → 真实枫树 → 真实废墟 H1；修掉 OBJ 面索引 bug（44 万面坏面）
