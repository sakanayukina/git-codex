# AGENTS.md

「Codex + DeepSeek Harness」共享的交接文件。两个代理不共享会话记忆，切换时先读本文件，干完一段更新「当前状态」与「下一步」。

## 工作区地图

- **仿真场景**：`assets/demo_v6.xml`（当前场景，535 body / 1307 geom / 10 相机，约 82 MB 素材，gitignore 不入库）
- **生成链**：`assets/_tools/` — `build_scene.py`(拼地形) → `tune.py`(材质) → `scatter.py`(植被/废墟) → `village.py`(村落, base 是 `demo_v5.xml`)，`roadgen.py` 生成土路网格
- **导入链**：`convert_multi.py`(glTF/GLB 按材质拆分) → `import_gltf.py` / `import_building.py`(建筑) → `fix_obj_faces.py`(OBJ 体检)
- **渲染/清理**：`render_scene.py`、`preview_parts.py`、`cleanup.py`
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

- **场景**：汶川 DEM 地形（200 m² / 落差 66.5 m）+ 5 栋房（H1 真实废墟，H2–H5 程序化）+ 土路 + 24 块岩石 + 92 棵程序化针叶树 + 30 棵 Sketchfab 枫树 + 90 块废墟 + 车辆（**2.50 M 三角面**）
- **H1 = `collapsed_uk_terraced_house`**（22,631 面，15 材质分件、1 张 2K 图集），有不可见碰撞外壳（留 1.3 m 门洞），相机 `cam_H1`…`cam_H5` + `close`
- **已解决**：石头瘦身（_tools/slim_rocks.py，140→24 个 + 删掉 75 个扁平草皮，**8.61 M → 2.50 M**）
- **未解决**：① 树叶近看发白点（单面片）；② 废墟是英式排屋，风格与川西砖房不完全一致
- **待素材**：H2/H5 的真实废墟模型（≤25 万面、glTF）

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

1. ~~岩石瘦身~~ 已完成：slim_rocks.py --keep 24 --drop-grass --apply --in-place
2. **H2/H5 换真房子**（用户找素材，DSH 接入）：`buildings.json` 的 `model` 支持目录
3. **二次坍塌触发 + 机器人接入**（Codex 主责，DSH 复查）：DSH 出可塌结构与 `site_*` 命名规范

## 历史（一行一天）

- 2026-10-20 分工确立；仓库从 2 个 commit 扩到脚本/论文入库
- 2026-10-22 素材包 → 真实 DEM → 加密植被 → 真实枫树 → 真实废墟 H1；修掉 OBJ 面索引 bug（44 万面坏面）
