# AGENTS.md

「Codex + DeepSeek Harness」共享的交接文件。两个代理不共享会话记忆，切换时先读本文件，干完一段更新「当前状态」与「下一步」。

## 工作区地图

- **仿真场景**：`assets/demo_v27.xml`（598 body / 1037 geom / 12 相机 / 8 site；**3.81 M 三角面**；整平过渡带 **11 m**；H2 footprint 地形整平到 9.40 m，body z 9.38（diff -0.02，完全贴地）；基座 0、悬空瓦砾 0；堆积锥 48 + 接缝碎石 187；`demo_v7.xml` 为原版对照）
- **场景结构说明**：根目录 `SCENE_GUIDE.md`（文件地图、生成链、每步作用、修改方法、已知问题）
- **生成链**：`build_scene.py`(地形+道具) → `tune.py`(材质曝光) → `scatter.py`(植被/废墟) → `village.py`(村落，base = `demo_v5.xml`) → `slim_rocks.py`(石头瘦身)
- **导入链**：`convert_multi.py`(glTF/GLB 按材质拆分、减面、只保留指定材质) → `import_gltf.py` / `import_building.py` → `fix_obj_faces.py`(OBJ 体检) → `prune_imported.py`(删转换中间文件) → `decimate_obj.py`(单个 OBJ 减面)
- **场景辅助**：`bake_ground.py`(把路烘进地面贴图)、`polish.py`(树/草/瓦砾/天空/地面)、`seam_ring.py`(房子边缘接缝碎石)、`layout_check.py`(压路/重叠体检)、`check_floating.py`(瓦砾悬空体检)、`render_scene.py`、`preview_parts.py`、`cleanup.py`
- 其他：`papers/`、`skills/paper-reader`、`PerpetualCalendar.java`、`scripts/extract_papers.py`

## 环境

| 用途 | 解释器 |
|---|---|
| 仿真、加载/渲染 MJCF | `C:/Users/18967/anaconda3/envs/mujoco/python.exe`（MuJoCo 3.3.2） |
| 生成场景、图片处理（PIL/requests） | `C:/Users/18967/anaconda3/python.exe` |

`village.py` / `scatter.py` / `build_scene.py` / `bake_ground.py` 依赖 PIL，**必须用 base python**；`render_scene.py`、`slim_rocks.py` 用 mujoco 环境。

## 怎么跑（给人和 Codex 都看）

```powershell
$py     = "C:/Users/18967/anaconda3/python.exe"          # PIL/requests
$mjpy   = "C:/Users/18967/anaconda3/envs/mujoco/python.exe"   # 仿真/渲染

# 村子（交互窗口，默认 demo_v27.xml）
cd C:\Users\18967\Desktop\git
& $mjpy run_scene.py                 # 打开被动窗口
& $mjpy run_scene.py --headless      # 只加载自检

# 机器狗 Go2（URDF 导入版，独立场景）
& $mjpy run_go2.py                   # 打开窗口，home 姿态站住
& $mjpy run_go2.py --headless --sim 2   # 无窗口：跑 2 s 物理并汇报机身高度
& $mjpy run_go2.py --sim 5           # 先跑 5 s 再开窗口

# 通用（不用写脚本，直接看任意 MJCF）
& $mjpy -m mujoco.viewer --mjcf=assets/props/robots/go2_urdf/go2_scene.xml

# 出图（不弹窗）
& $mjpy assets/_tools/render_scene.py assets/demo_v27.xml out.png 1100 650 2500 2
```

> `run_go2.py` 会先 `mj_resetDataKeyframe(..., 0)` 用 home 姿态起步；
> 直接 `python -m mujoco.viewer` 打开 go2_scene.xml 时用的是 qpos0（腿伸直零位），
> 站着会塌一点，属正常，不是模型坏。


## 现在有什么

**场景**（`assets/demo_v27.xml`，band 11 + H2 地形整平版；`demo_v7.xml` 为原版对照）
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
| **H3/H4 的民房废墟模型** | 现在还是方盒占位房，论文图里一眼假 | 用户找素材（6–10 m 宽、有门窗、≤25 万面、glTF） |
| **机器人本体** | ✅ 已导入：`props/robots/go2_urdf/go2_scene.xml`（unitree_ros URDF → MuJoCo，nq=19 / 12 位置电机 / kp=100 站 0.271 m / 20.8 万面） | DSH 已完成；还差"放进 demo_v27 村子"这一步 |
| **二次坍塌触发** | 场景是静态的，没有动态事件 | Codex 主责（DSH 出可塌结构）；触发器框架 `_tools/collapse_trigger.py` 已就绪，等 v8 的 `collapse_*` 结构接入 |
| **地面细节** | 2048² 覆盖 200 m，草偏糊 | 升 4096 可解（25 MB） |
| **动态物体物理** | 废墟块是静态的，不会二次塌落 | 需把部分块改成 free joint |
| **H2 墙面绿色裂缝** | 扫描件本身的洞，减面后变大，能看穿到草地 | 提高减面上限重导或 `fix_obj_faces.py` 补洞 |

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
3. **H3/H4 换真房子**（等用户素材；H2/H5 已完成）
4. **二次坍塌 + 机器人**（Codex 主责，DSH 复查）

> 生成顺序：`village.py` → `slim_rocks.py --keep 24 --drop-grass --apply --in-place`
> → `optimize_trees.py`（Codex 的树优化）→ 如需碰撞：`add_collision.py --xml demo_v7.xml --apply`
> → 局部整平：`flatten_sites.py --band 11`（**过渡带 11 m**，6 m 会留明显坡折）→ `reground_props.py`
> → `fix_grounding.py --no-platform` → `remove_plinths.py` → `polish.py --ground-tex --grass-count 60`
> → `seam_ring.py --band 11`（碎石要跟着 band 走）

## 给 Codex 的请求（DSH 已实测，待并入你的链路）

1. **`flatten_sites.py` 请固定用 `--band 11`**（原默认 6 m）。实测 6 m 时房子边缘有一圈明显的坡折
   + 亮度突变，像"摆在圆托盘上"；11 m 的 smoothstep 过渡明显更自然。参数已经是现成的，不用改代码。
   如果以后要更缓，试 12–14 m，但整平面积会跟着变大。
2. 跑完 `flatten_sites.py` 之后，`seam_ring.py` 的 `--band` 要和它保持一致，
   否则接缝碎石会压错位置（碎石环半径 = footprint + band ± 1.5 m）。
3. **`SCENE_GUIDE.md` 请补一行入口**：机器狗用 `run_go2.py`（不是 `run_scene.py`），
   场景是 `assets/props/robots/go2_urdf/go2_scene.xml`，独立于 `demo_v27.xml`。
   目前狗还没并进村子，等合并后入口再统一。

## 历史

- 2026-10-20 分工确立
- 2026-10-22 素材包 → 真实 DEM → 加密植被 → 真枫树 → 真废墟 H1/H6/H7 → 石头瘦身 → 道路烘焙；修掉 OBJ 面索引 bug（44 万坏面）、GLB 内嵌贴图、hfield texrepeat
- 2026-10-22 Codex 树优化 v7：程序化树 142→90、半径收细 0.72，入口切到 demo_v7.xml，新增 `_tools/optimize_trees.py`
- 2026-10-22 Codex 二次坍塌触发器：`_tools/collapse_trigger.py` 按 `collapse_<group>_<index>` + 同名 weld 扫描，按组/时间置 `data.eq_active=0`；自包含测试验证 t=1 s 释放后 z 2.0→0.2
- 2026-10-23 Codex 降山势：relief 66.5→35 m、sigma=5 平滑、房子用土色台地、215 个树/石/草重新贴地，场景切到 demo_v14.xml
- 2026-10-23 Codex 局部整平：恢复原始 66.5 m 山势，只在房子 footprint 整平（3 m 过渡带），215 个道具重新贴地，场景切到 demo_v16.xml
- 2026-10-23 Codex 局部整平 + 去基座：过渡带 6 m smoothstep、房子不再加台地、删除 village.py 自带混凝土基座，场景切到 demo_v19.xml
- 2026-10-23 DSH d437147：修基座命名/平台、瓦砾移到 polish.py 消除悬空、H1/H6 堆积锥，产出 demo_v23.xml；Codex 切入口并清理中间版本
- 2026-10-23 DSH 0eb60f8/c069853：接缝碎石环（187 块，混凝土色）+ 岩石低模化 14,844→2,320 面（4.16 M → 3.81 M），产出 demo_v24.xml
- 2026-10-23 DSH 8f36da1 之后：`flatten_sites.py --band` 6→**11 m**，接缝坡折明显变缓；`seam_ring.py --band 11` 同步，产出 demo_v25.xml（面数不变 3.81 M）
- 2026-10-23 Codex：`flatten_sites.py` 默认 band 对齐 11 m，入口切到 demo_v25.xml，清理 v8~v24 中间版本与旧预览图
- 2026-10-23 Codex：H2 木屋 z 9.38→9.03（悬空/嵌入各 0.35 m），入口切到 demo_v26.xml，清理 v25 中间版本
- 2026-10-23 Codex：直接整平 H2 footprint 地形（考虑 yaw，band 11），H2 body z 9.03→9.38，diff -0.02 完全贴地，入口切到 demo_v27.xml
- 2026-10-23 Codex：新增根目录 `SCENE_GUIDE.md`，整理场景结构、生成链、脚本作用与修改方法
- 2026-10-24 DSH 8957533：**Go2 URDF 导入 MuJoCo** —— 新增 `dae2obj.py`(COLLADA→OBJ，含节点矩阵)、`fetch_go2_urdf.py`(下载 unitree_ros 描述)、`import_go2_urdf.py`(一键：转网格→改写 URDF→导出 MJCF→加 freejoint/12 位置电机/home 姿态)、`check_go2.py`(站立测试+渲染)。产物 `props/robots/go2_urdf/go2_scene.xml`：nq=19 / nu=12 / 16.28 kg / 20.8 万面 / 静置 2 s 站 0.271 m
