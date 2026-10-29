# AGENTS.md

「Codex + DeepSeek Harness」共享的交接文件。两个代理不共享会话记忆，切换时先读本文件，干完一段更新「当前状态」与「下一步」。

## 工作区地图

- **展示场景**：`assets/demo_v32.xml`（**670 body / 1154 geom / 15 相机 / 10 site / 4.62 M 三角面**）= `demo_v28`（598 body / 3.81 M，纯环境）+ H1 门前的 **Go2 + G1**（固定基座出图；相机 `cam_robots` / `cam_hero` / `cam_hero2`）；v30 移机器人到 H1 门前、v31 校正道具比例、v32 最新。
- **验证场景（新）**：`assets/yard_{flat,stairs,full}.xml`（三档难度：纯平地 / 台阶 / 台阶+碎石+Perlin；每份都含 H1 房子 + Go2；`full` 是 45 body / 143 geom）；生成器 `_tools/yard.py --tier`，自检 `_tools/check_yard.py`，出图 `_tools/render_yard.py`
- **场景结构说明**：根目录 `SCENE_GUIDE.md`（文件地图、生成链、每步作用、修改方法、已知问题）
- **生成链**：`build_scene.py`(地形+道具) → `tune.py`(材质曝光) → `scatter.py`(植被/废墟) → `village.py`(村落，base = `demo_v5.xml`) → `slim_rocks.py`(石头瘦身)
- **导入链**：`convert_multi.py`(glTF/GLB 按材质拆分、减面、只保留指定材质) → `import_gltf.py` / `import_building.py` → `fix_obj_faces.py`(OBJ 体检) → `prune_imported.py`(删转换中间文件) → `decimate_obj.py`(单个 OBJ 减面)
- **场景辅助**：`bake_ground.py`(把路烘进地面贴图)、`polish.py`(树/草/瓦砾/天空/地面)、`seam_ring.py`(房子边缘接缝碎石)、`layout_check.py`(压路/重叠体检)、`check_floating.py`(瓦砾悬空体检)、`render_scene.py`、`preview_parts.py`、`cleanup.py`
- **地形采样**：`_tools/terrain.py`（`HfieldSampler` 用于 demo，row 0=-Y；`FloatDEMSampler` 用于 `terrain/dem_float.npz`，row 0=+Y；统一 `height(x,y)`）
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

# 村子展示（默认 Go2 + G1 持续行走；每 8 s 自动复位）
cd C:\Users\18967\Desktop\git
& $mjpy run_scene.py                 # 打开双机器人持续演示窗口
& $mjpy run_scene.py --static --headless  # 原静态场景加载自检

# 机器狗 Go2（URDF 导入版，独立场景）
& $mjpy run_go2.py                   # 打开窗口，home 姿态站住
& $mjpy run_go2.py --headless --sim 2   # 无窗口：跑 2 s 物理并汇报机身高度
& $mjpy run_go2.py --sim 5           # 先跑 5 s 再开窗口

# 人形 G1（官方 g1_29dof.xml + STL 导入版，独立场景）
& $mjpy run_g1.py                    # fixed 基座版：站着不动，当场景 NPC 用
& $mjpy run_g1.py --free             # 带 freejoint：没有平衡控制器会摔（正常现象）
& $mjpy run_g1.py --headless --sim 1 # 无窗口自检

# 通用（不用写脚本，直接看任意 MJCF）
& $mjpy -m mujoco.viewer --mjcf=assets/yard_flat.xml   # 另有 yard_stairs / yard_full

# 验证场景 yard（30 m 小院：0.15 m 台阶 / 碎石阵 / Perlin 起伏 / H1 房子 / Go2）
& $py  assets/_tools/yard.py         # 重新生成（**必须 base python**）
& $mjpy -m mujoco.viewer --mjcf=assets/yard_flat.xml
& $mjpy assets/_tools/render_yard.py # 出图（自由相机取景）

# 出图（不弹窗）
& $mjpy assets/_tools/render_scene.py assets/demo_v32.xml out.png 1100 650 2500 2
```

> `run_go2.py` 会先 `mj_resetDataKeyframe(..., 0)` 用 home 姿态起步；
> 直接 `python -m mujoco.viewer` 打开 go2_scene.xml 时用的是 qpos0（腿伸直零位），
> 站着会塌一点，属正常，不是模型坏。


## 现在有什么

**场景**（`assets/demo_v32.xml`，670 body / 1154 geom / 15 相机；含 H1 门前 Go2 + G1；`demo_v28.xml` 为纯环境对照）
- 地形：汶川真实 DEM，200 m²，落差 66.5 m，`hfield` + 烘焙地面贴图（路长在地形上）
- 道路：主路 4.2 m + 7 条入户支路 3.0 m + 岔口补丁，全部烘进 2048² 地面贴图
- 建筑/废墟 7 个可搜索点：
  | 点 | 内容 | 面数 | 碰撞 |
  |---|---|---|---|
  | H1 | 真砖房废墟 `ruin_uk`（15 材质分件） | 22,631 | ✅ 不可见墙 + 1.3 m 门洞 |
  | H6 | 混凝土塌楼 `ruin2`（含瓦砾场） | 3,407 | ✅ 楼体 9.0×6.5×3.2 + 1.6 m 门洞（瓦砾不挡） |
  | H7 | 塌墙扫描件 `ruin_wall` | 90,817 | ✅ 12.2×0.9×2.2 实墙（无门） |
  | H2 | 木屋 `house2`（真实模型 + 1.4 m 门洞碰撞） | — | ✅ |
  | H5 | 木屋 `h5a`（真实模型 + 1.3 m 门洞碰撞） | — | ✅ |
  | H3–H4 | 程序化占位房 | 各 ~200 | ❌ |
- 植被：30 棵真实枫树（CC-BY，双面）、118 棵程序化针叶树（本轮重建未跑 optimize_trees，仍为 118）、45 簇真实草、24 块岩石
- 道具：报废盖布车、水泥隔离墩、旧轮胎、树桩、枯枝
- 相机：`wide` / `close`(H1) / `village` / `top`(俯视) / `cam_H1`…`cam_H7` / `cam_robots` / `cam_hero` / `cam_hero2`
- 标记：`<site name="site_H1">`…`site_H7`、`site_P0`（`group=3`，不渲染但坐标有效）

**工具链**：下载→转换→减面→入户→烘焙地面→渲染→瘦身→清理，全流程可一条命令重跑。

## 缺什么

| 缺 | 影响 | 谁来补 |
|---|---|---|
| **H3/H4 的民房废墟模型** | 现在还是方盒占位房，论文图里一眼假 | 用户找素材（6–10 m 宽、有门窗、≤25 万面、glTF） |
| **机器人本体** | ✅ Go2：`props/robots/go2_urdf/go2_scene.xml`（URDF 导入，nq=19 / 12 电机 / 16.28 kg / 20.8 万面）。✅ G1：`props/robots/g1/g1_scene.xml`（官方 MJCF+STL，nq=29 / 29 电机 / 35.1 kg / 59.8 万面 / 脚底 z=0.0004 m） | ✅ 已放进 demo_v32（H1 门前，固定基座）；行走验证用 yard |
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
13. **DEM hfield 有 0.26 m 的隐形台阶**：66.5 m 落差 ÷ 8 位灰度 255 级 = 0.26 m/级，且沿网格正交排列。
    用 demo_v32 测机器人通过性会被这个量化伪影污染 → 机器人验证一律用 `yard_flat.xml`（0.15 m 显式台阶）。
14. **H1 之前一直是灰模**：`ruin_uk` 的 15 个 material 只有 `rgba`（没接图集），因为老资产没有
    `manifest.json`。已在 `village.py` 加"共享 `<name>_atlas_N.png` 兜底"，`yard.py` 里已验证有效；
    **demo_v27 要重跑生成链才会变**。

## 下一步（按优先级，2026-10-29 更新）

**论文核心（最优先，尚未开始）**

1. **等导师定算法后，往 `Dispatcher` 插座里插**（LLM / DRL / 聚类 / 拍卖）——
   接口、代价矩阵、指标、基线都已就绪，换算法只需新增一个类并改一行配置。
2. **执行层**：把分配结果（agent→任务序列）接到 `waypoint_nav.py --astar` 真正跑一遍，
   得到「仿真里真实的完成时间/里程」，替换当前的「模型估算」指标。
3. ~~G1 航点导航~~ ✅ 已支持 `--robot g1`（见当前能力）；G1 只能走 ≤8° 路线，给 G1 分配任务时必须在代价层过滤。

`A* 路径 → 多航点实走` 已打通：Go2 从 `(1,-20)` 到 H1 的 A* 路径
16.0 m / 5 航点 / 41 s 到达路径终点，实走 14.4 m；详细记录见历史文档。

**平台补完（次优先）**

4. **二次坍塌触发**（Codex 主责；`collapse_*` 结构进 `yard_full.xml`）。
5. **H3/H4 换真房子**（等用户素材；H2/H5 已完成）。
6. **视觉收尾**：H2 墙面裂缝、地面 2048→4096。

**不再优先**：步态训练 —— 长时「不摔」已由开源教师策略和 G1 官方策略满足，见「当前能力」一节。

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
3. **`SCENE_GUIDE.md` 请补一行入口**（✅ Codex 已补，见 §6）：机器狗用 `run_go2.py`（不是 `run_scene.py`），
   场景是 `assets/props/robots/go2_urdf/go2_scene.xml`，独立于 `demo_v32.xml`。
   目前狗还没并进村子，等合并后入口再统一。

### 2026-10-24 新增请求（yard 那一轮之后）

4. **【已完成】重建 `demo_v27` → `demo_v28`**：`village.py` 已修好"H1 材质缺图集"的 bug（老资产 `ruin_uk` 没有
   `manifest.json`，素材只有共享 `ruin_uk_atlas_0.png`），但**现有 demo_v27.xml 里 H1 还是灰模**，
   必须按上面那条生成链重跑一次才会贴上砖墙。DSH 随时可以跑，**只要确认你那侧没有并发改 `demo_*.xml`**；
   跑完的验收：`grep 'bld0_0_mat' demo_v28.xml` 应带 `texture=`，且三角面仍 ≈3.8 M。
5. **【已完成】`SCENE_GUIDE.md` 增加"验证场景"一节**：三档 `assets/yard_{flat,stairs,full}.xml`、
   生成器 `_tools/yard.py --tier`、自检 `_tools/check_yard.py`、出图 `_tools/render_yard.py`。
   并写清一条纪律：**机器人运动验证只用 yard，不要用 demo_v27**（DEM 8 位量化 = 每级 0.26 m 隐形台阶）。
6. **【注意，别手改】`assets/props/robots/go2_urdf/go2_robot.xml` 是 `yard.py` 每次自动生成的**
   （从 `go2_scene.xml` 抽出的"只有机器人"片段，去掉了 floor/light/camera/option/visual）。
   要改机器人本体请改 `go2_scene.xml` 或 `import_go2_urdf.py`，再跑一次 `yard.py`。
7. **【交接点】二次坍塌若要和机器人联动**（机器人靠近才塌），建议把可塌结构放进 `yard_full.xml`
   而不是 `demo_v27.xml`：yard 地面是解析几何，接触稳定、可复现；demo 的 hfield 有 0.26 m 量化噪声，
   塌落初始条件会不可控。`collapse_trigger.py` 的 `collapse_<group>_<index>` 命名直接沿用即可。
8. **【已知事实，供你决策】宇树官方预训练策略只有 G1/H1/H1-2，没有 Go2**：
   `unitree_rl_gym/deploy/pre_train/` 下是 `g1/motion.pt`（142 KB）、`h1/`、`h1_2/`。
   且这些 config 的 `terrain.mesh_type` 都是 `'plane'` → **官方策略是平地训练的**，
   在崎岖地形上不要预期它能跑，得先在 `yard_flat.xml` 上验证。

## 当前能力（数字速查，2026-10-29）

| 能力 | 结果 | 谁测的 |
|---|---|---|
| Go2 长时行走（村子地形 + 610 代理） | **180 s 不摔**（旧测：被障碍堵在 6 m） | DSH |
| **长距离行走**（A\* 绕障 + 航点串走） | **86.8 m / 220.6 s，17/17 航点，不摔** | DSH |
| Go2 纯地形均速 | **0.41 m/s**（3 s 走 1.24 m） | DSH |
| G1 长时行走 | **180 s 不摔**，均速 0.03 m/s | DSH |
| 双机同场（同一 mjModel，dt 0.002×10） | Go2 **5.10 m** / G1 **4.69 m** / 12 s，间距 5.34 m，均不摔 | Codex+DSH |
| 双 Go2 真实碰撞 | 撞上互相挡住/推开（机器人2 被推 0.02 m），非穿模 | DSH |
| 航点导航（Go2 教师 + 闭环转向） | 13 m 目标 **32.8 s 到达**（0.37 m/s） | DSH |
| 更远目标（16–24 m） | ❌ 6–14 m 处被障碍挡住 | DSH |
| Go2 学生 `bc.pt` 连续爬坡 | 边界 **5–10°**（10° 翻倒） | DSH |
| **G1 航点导航**（`--robot g1`） | H6 路线 **31.08 m / 94.9 s / 8/8 航点不摔**（最大坡 8.1°） | DSH |
| **G1 能力边界** | 12° 路线在 **约 33 m 处必摔**（与速度无关，位置性失败） | DSH |
| **A\* 绕障规划**（`train/nav_grid.py`） | **7/7 站点可规划**，路径 15–93 m，持续坡度 5.9–21.4° | DSH |
| **A\* 路径实走**（Go2 → H1） | 规划 16.0 m / 5 航点，**41 s 到达**，实走 14.4 m，距 H1 参考中心 7.0 m | Codex |
| **长距离实走**（Go2 → H2） | **实走 86.84 m / 220.6 s / 17 个航点全过**，0.39 m/s，不摔 | DSH |
| **任务分配层**（`train/mission.py`） | 3 个分配器可切换；marginal 比 greedy 省 **20%** 里程 | DSH |
| 任务分配 / 指标层 | ✅ 接口 + 3 基线 + 4 指标已就绪（算法待定） | — |

**关键口径**：长时「不摔」已解决；卡点是**被障碍挡住**，属规划层职责，不是运动层。

## 详细历史

所有按时间记录的工程细节（二分实验、训练曲线、踩坑过程）见 **`docs/AGENTS_HISTORY.md`**。

> **协作约定**：新完成一段工作 → 详细过程追加到 `docs/AGENTS_HISTORY.md`；
> 本文件只更新「现在有什么 / 下一步 / 当前能力」的摘要。
> 主文件超过 15 KB 会被系统截断，接手方会看不到最新内容。

## 废弃场景

旧 `village_walk*` 已移到 `assets/_archive/`；当前入口用 `village_walk_final.xml`，
归档明细见历史文档。
