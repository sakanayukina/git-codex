# AGENTS.md

「Codex + DeepSeek Harness」共享的交接文件。两个代理不共享会话记忆，切换时先读本文件，干完一段更新「当前状态」与「下一步」。

## 工作区地图

- **仿真场景**：`assets/demo_v19.xml`（340 body / 895 geom / 48 mesh / 34 tex / 12 相机 / 8 site；原始 66.5 m 山势 + 房子 footprint 局部整平 + 6 m 平滑过渡；已去掉额外台地和混凝土基座；`demo_v7.xml` 为原版对照；素材 **152 MB**，gitignore 不入库）
- **生成链**：`build_scene.py`(地形+道具) → `tune.py`(材质曝光) → `scatter.py`(植被/废墟) → `village.py`(村落，base = `demo_v5.xml`) → `slim_rocks.py`(石头瘦身)
- **导入链**：`convert_multi.py`(glTF/GLB 按材质拆分、减面、只保留指定材质) → `import_gltf.py` / `import_building.py` → `fix_obj_faces.py`(OBJ 体检) → `prune_imported.py`(删转换中间文件)
- **场景辅助**：`bake_ground.py`(把路烘进地面贴图)、`roadgen.py`(3D 路面，当前未用)、`render_scene.py`、`preview_parts.py`、`cleanup.py`
- 其他：`papers/`、`skills/paper-reader`、`PerpetualCalendar.java`、`scripts/extract_papers.py`

## 环境

| 用途 | 解释器 |
|---|---|
| 仿真、加载/渲染 MJCF | `C:/Users/18967/anaconda3/envs/mujoco/python.exe`（MuJoCo 3.3.2） |
| 生成场景、图片处理（PIL/requests） | `C:/Users/18967/anaconda3/python.exe` |

`village.py` / `scatter.py` / `build_scene.py` / `bake_ground.py` 依赖 PIL，**必须用 base python**；`render_scene.py`、`slim_rocks.py` 用 mujoco 环境。

## 现在有什么

**场景**（`assets/demo_v19.xml`，局部整平 + 去基座版；`demo_v7.xml` 为原版对照）
- 地形：汶川真实 DEM，200 m²，落差 66.5 m，`hfield` + 烘焙地面贴图（路长在地形上）
- 道路：主路 4.2 m + 7 条入户支路 3.0 m + 岔口补丁，全部烘进 2048² 地面贴图
- 建筑/废墟 7 个可搜索点：
  | 点 | 内容 | 面数 | 碰撞 |
  |---|---|---|---|
  | H1 | 真砖房废墟 `ruin_uk`（15 材质分件） | 22,631 | ✅ 不可见墙 + 1.3 m 门洞 |
  | H6 | 混凝土塌楼 `ruin2`（含瓦砾场） | 3,407 | ✅ 楼体 9.0×6.5×3.2 + 1.6 m 门洞（瓦砾不挡） |
  | H7 | 塌墙扫描件 `ruin_wall` | 90,817 | ✅ 12.2×0.9×2.2 实墙（无门） |
  | H2 | 木屋 `house2`（真实模型 + 1.4 m 门洞碰撞） | — | ✅ |
  | H3–H5 | 程序化占位房 | 各 ~200 | ❌ |
- 植被：30 棵真实枫树（CC-BY，双面）、118 棵程序化针叶树（本轮重建未跑 optimize_trees，仍为 118）、45 簇真实草、24 块岩石
- 道具：报废盖布车、水泥隔离墩、旧轮胎、树桩、枯枝
- 相机：`wide` / `close`(H1) / `village` / `top`(俯视) / `cam_H1`…`cam_H5`
- 标记：`<site name="site_H1">`…`site_H7`、`site_P0`（`group=3`，不渲染但坐标有效）

**工具链**：下载→转换→减面→入户→烘焙地面→渲染→瘦身→清理，全流程可一条命令重跑。

## 缺什么

| 缺 | 影响 | 谁来补 |
|---|---|---|
| **H5 的民房废墟模型** | 现在还是方盒占位房，论文图里一眼假 | 用户找素材（6–10 m 宽、有门窗、≤25 万面、glTF） |
| **机器人本体** | 场景里没有机器人 | 用户老师那边有模型 |
| **二次坍塌触发** | 场景是静态的，没有动态事件 | Codex 主责（DSH 出可塌结构）；触发器框架 `_tools/collapse_trigger.py` 已就绪，等 v8 的 `collapse_*` 结构接入 |
| **地面细节** | 2048² 覆盖 200 m，草偏糊 | 升 4096 可解（25 MB） |
| **动态物体物理** | 废墟块是静态的，不会二次塌落 | 需把部分块改成 free joint |

## 关键结论（踩过的坑）

1. **MuJoCo 不读 glTF**、也不支持 Draco → 必须转 OBJ。
2. **hfield**：`size` 四个数全须为正（base≥0.01）；PNG 第 0 行 = +Y；只吃 8 位灰度。
3. **hfield 的 `texrepeat` 按“米”计**：1:1 覆盖 200 m 要填 `1/200 = 0.005`，填 `1 1` 等于每米铺一次（路会缩成噪声）。
4. **MuJoCo 3.3.2 没有 PBR**：metallic/roughness/normal layer 编译通过但渲染像素差为 0，只认 albedo + specular/shininess。
5. **薄片 mesh 必须 `inertia="shell"`**，否则 `mesh volume is too small`。
6. **OBJ 面索引从 1 开始**，不能写 `f a/b/c`（会被当成一个顶点的 v/vt/vn）。
7. **照片扫描树进不了 MuJoCo**（698 万面，降面成灰团）；扫描件（墙、石头）可以减面。
8. **GLB 的贴图可能内嵌在 bufferView 里**，不抽出来就是灰模。
9. **多材质共用一张图集**：导出必须去重（曾 90 MB → 4.3 MB）。
10. **`site` 会渲染成球** → `group="3"`；相机要避开门洞，否则近景全灰。
11. **GBK 控制台**：脚本里写 `²` 会抛 UnicodeEncodeError，被 try/except 吞掉后静默失败。
12. **贴地道路网格会抖/锯齿** → 改烘进地面贴图；但别忘了删旧网格，否则它盖在上面。

## 下一步（按优先级）

1. ~~H6/H7 补碰撞~~ ✅ 已完成（`add_collision.py`，H6 楼体+门洞、H7 实墙，射线验证通过）
2. ~~树叶翻面~~ ✅ 已完成（`double_side.py`，枫叶 6,488→12,976 面，场景 2.78 M）
3. **H5 换真房子**（等用户素材；H2 已完成）
4. **二次坍塌 + 机器人**（Codex 主责，DSH 复查）

> 生成顺序：`village.py` → `slim_rocks.py --keep 24 --drop-grass --apply --in-place`
> → `optimize_trees.py`（Codex 的树优化）→ 如需碰撞：`add_collision.py --xml demo_v7.xml --apply`
> → 局部整平：`flatten_sites.py`（footprint + 6 m 平滑过渡）→ `reground_props.py` → `fix_grounding.py --no-platform` → `remove_plinths.py`

## 历史

- 2026-10-20 分工确立
- 2026-10-22 素材包 → 真实 DEM → 加密植被 → 真枫树 → 真废墟 H1/H6/H7 → 石头瘦身 → 道路烘焙；修掉 OBJ 面索引 bug（44 万坏面）、GLB 内嵌贴图、hfield texrepeat
- 2026-10-22 Codex 树优化 v7：程序化树 142→90、半径收细 0.72，入口切到 demo_v7.xml，新增 `_tools/optimize_trees.py`
- 2026-10-22 Codex 二次坍塌触发器：`_tools/collapse_trigger.py` 按 `collapse_<group>_<index>` + 同名 weld 扫描，按组/时间置 `data.eq_active=0`；自包含测试验证 t=1 s 释放后 z 2.0→0.2
- 2026-10-23 Codex 降山势：relief 66.5→35 m、sigma=5 平滑、房子用土色台地、215 个树/石/草重新贴地，场景切到 demo_v14.xml
- 2026-10-23 Codex 局部整平：恢复原始 66.5 m 山势，只在房子 footprint 整平（3 m 过渡带），215 个道具重新贴地，场景切到 demo_v16.xml
- 2026-10-23 Codex 局部整平 + 去基座：过渡带 6 m smoothstep、房子不再加台地、删除 village.py 自带混凝土基座，场景切到 demo_v19.xml
