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

## 下一步（按优先级）

1. ~~H6/H7 补碰撞~~ ✅ 已完成
2. ~~树叶翻面~~ ✅ 已完成
3. **H3/H4 换真房子**（等用户素材；H2/H5 已完成）
4. **二次坍塌触发**（Codex 主责；DSH 出 `collapse_*` 结构，放 `yard_full.xml`）
5. **机器人策略落地**：BC/DAgger 学生已在真实坡度走 5.4–6.1 m/10 s（超过老师 2.82 m）；下一步把 `train/ckpt/bc.pt` 接到 `yard_*` / 村子，做地形泛化
6. **视觉收尾**：H2 墙面裂缝、地面 2048→4096

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


### 机器人运动（B 阶段，2026-10-24 DSH）

- **Go2 爬行步态可用**：`_tools/walk_go2.py`（`--sweep` 调参）+ `_tools/run_walk.py`（看窗口）。
  最优参数 `freq=2.0 a_thigh=0.22 a_calf=0.55 thigh0=0.95 gait=crawl`
  → 6 s 走 **2.58 m**（≈0.43 m/s），航向漂移 **0.21 rad**，机身 z 全程 **0.27~0.30**（没趴）。
  **局限：超过 8 s 会失稳**（开环无平衡反馈）。
- **对角 trot 不行**：`freq=2.0 a_thigh=0.25 a_calf=0.70` → 8 s 走 3.48 m 但航向漂 1.84 rad（绕圈）。
- **`_tools/trot_ik.py` 未通**：三自由度 IK 的 FK 基准和 MuJoCo 的 body 原点对不上（自检
  `--selftest` 输出 thigh −1.697 vs 实际 +0.900），要接 IK 步态得先重标定髋/膝的几何约定。
- **G1 无法用手写控制器行走**：双足要平衡反馈，手写 PD 只能站着。

### G1 官方策略：已装 torch，但策略是 12 自由度版（2026-10-24 DSH）

- torch **2.8.0+cpu 已装进 mujoco 环境**（用户批准 danger-full-access 后成功）。
- `deploy/pre_train/g1/motion.pt`（145,745 B）已下到 `assets/props/robots/g1/motion.pt`；
  `torch.jit.load` 可加载，是 **TorchScript + LSTM**（`PolicyExporterLSTM`，带内部 hidden state）。
- **关键发现：这个策略是 G1 12 自由度版**（`G1RoughCfg`）：

  | 项 | 值 |
  |---|---|
  | num_observations | **47** |
  | num_actions | **12**（只含双腿 6×2，不含双臂） |
  | asset.file | `g1_description/g1_12dof.urdf` |
  | 默认关节角 | hip_pitch −0.1, knee 0.3, ankle_pitch −0.2（其余 0） |
  | action_scale / decimation | 0.25 / 4 |
  | stiffness | hip_yaw 100, hip_roll 100, hip_pitch 100, knee 150, ankle 40 |
  | damping | hip_yaw 2, hip_roll 2, hip_pitch 2, knee 4, ankle 2 |

  配置已存 `assets/_tools/unitree_policy/g1_12dof_config.py`。
- 所以**不能直接拿我们导入的 `g1_29dof`（29 关节含双臂）跑这个策略**，必须补一份 12 自由度版模型
  （`g1_description/g1_12dof.xml`，网格可复用已下的 36 个 STL）再按 47 维 obs 接线。

### B-G1：官方策略接了一半（2026-10-24 DSH）

已完成：
- `make_g1_12dof.py` → `props/robots/g1/g1_12dof_scene.xml`：把 29 自由度模型裁成**腿部 12 自由度**
  （删腰/臂关节，执行器 `<position>` → `<motor>` 力矩，补回 freejoint），校验 **nq=19 / nu=12**。
- `g1_policy.py`：完全按官方 `g1.yaml` + `deploy_mujoco.py` 接线——47 维 obs 切片、
  `action_scale=0.25`、50 Hz（dt 0.002 × decimation 10）、力矩 `tau = kp(target−q) − kd·dq`、
  LSTM `reset_memory()`。
- `fetch_g1_12dof.py`：等网络恢复后一键下官方 `g1_12dof.xml`（4 个源 + 重试）。

卡住的地方：
- **策略一上就摔**：`cmd vx=0` 跑 3 s，骨盆 0.80 → **0.12**，航向漂 1.9 rad。
  `--swap-roll-yaw`（关节顺序另一种可能）也一样摔，排除关节序问题。
- 最可能原因：**我们的 12dof 是从 29dof 裁的，双臂/腰的 body 还被焊在躯干上**（16 个），
  质量/惯量分布和官方"无手臂"的 12dof 模型不一致，策略没见过这种本体。
  尝试用 `_drop_bodies()` 整块删手臂子树，标签配对有 bug，只删掉 1 个 body，需要重写。
- **官方 `g1_12dof.xml` 下不下来**：raw.githubusercontent / jsDelivr / ghfast 全部
  `WinError 10054`（当时网络整体不通）。网络恢复后先跑 `fetch_g1_12dof.py`，
  再用 `g1_policy.py --xml .../g1_12dof_official.xml` 重试，这是最干净的路径。

### B-G1 完成：官方 12 自由度模型 + motion.pt 让 G1 真的走起来了（2026-10-24 DSH）

**结论：G1 走通了。** 平地实测（`cmd vx=0.5`）：

| 时长 | 位移 | 骨盆 z | 航向漂移 |
|---|---|---|---|
| 3 s | **1.27 m** | 0.77~0.80 | −0.06 rad |
| 5 s | **2.22 m** | 0.77~0.80 | −0.08 rad |
| 8 s | **3.64 m**（≈0.45 m/s） | 0.77~0.80 | −0.11 rad |

原地站 3 s：位移 0.02 m、骨盆 0.77~0.80、航向 −0.04 rad —— 稳。

关键突破点：**之前摔是因为本体不对**。我们从 29dof 裁的 12dof 模型把双臂/腰焊在躯干上
（总质量 35.1 kg），官方 12dof 是 **32.1 kg 无手臂**，策略只认后者。

可复现的链路（网络用 `ghproxy.net` / `gh-proxy.com` 镜像，raw.githubusercontent 仍被重置）：

```powershell
& $py assets/_tools/fetch_g1_12dof.py          # 下官方 g1_12dof.xml（13 关节: 1 free + 12 腿）
& $mjpy assets/_tools/fix_g1_12dof_meshes.py   # 补缺失 STL（含 torso_link_23dof_rev_1_0）
& $mjpy assets/_tools/wrap_g1_12dof.py         # 套地面/光/相机 → g1_12dof_scene.xml（nq19/nu12, 32.1 kg）
& $mjpy assets/_tools/g1_policy.py --xml props/robots/g1/g1_12dof_scene.xml --vx 0.5 --seconds 8
```

产物：`props/robots/g1/g1_12dof_official.xml`（官方原版）、`g1_12dof_scene.xml`（可跑场景）。

已知小瑕疵：`torso_link_23dof_rev_1_0.STL` 下载慢，先用本地 `torso_link.STL` 顶替
（`wrap_g1_12dof.py` 里有 remap），**只影响外观、不影响运动学**；下到真件后重跑 wrap 即可。

还没做：**把人形放进 yard 做地形测试**（0.15 m 台阶）。需要把 `g1_policy.py` 改成按关节名
定位（现在硬编码 `qpos[7:]`），才能跑在同时含 Go2 的场景里。

### G1 地形测试结果（2026-10-24 DSH，B-G1-4）

官方策略在**平地**上很好，在**台阶**上不行。实测（`cmd vx=0.5`，8 s）：

| 场景 | 位移 | 骨盆 z（末） | 结论 |
|---|---|---|---|
| 平地 | **3.64 m** | 0.77 | ✅ 稳 |
| 台阶 0.15 m（在前进路上） | 1.00 m | 0.09 | ❌ 撞上第一级就摔 |
| 台阶 0.05 m（同上） | 1.74 m | 0.19 | ❌ 5 cm 就会绊倒 |

**结论：官方 motion.pt 是平地策略，抬腿高度不够，台阶 ≥5 cm 就失败。**
想在废墟里跑，必须换成粗糙地形训练的策略（IsaacGym 重训），不是调参能解决的。

两个踩坑（都会让结果假性异常）：
1. **不能漏 `<default>`**：官方模型里 `<default><joint damping="0.001" armature="0.01" frictionloss="0.1"/>`
   必须跟着搬，漏了会"走两步就摔"。
2. **地面材质/场景结构要与训练一致**：从 terrain_tool 模板起场景时，机器人会"站住不走"；
   改成**以官方 12dof 场景为底、只追加地形 geom**（`make_g1_yard.py` 现在的做法）就正常了。

工具：
```powershell
& $py  assets/_tools/make_g1_yard.py --tier stairs|flat|full   # 造人形院子
& $mjpy assets/_tools/g1_policy.py --xml assets/g1_yard_stairs.xml --vx 0.5 --seconds 8
```

另：`torso_link_23dof_rev_1_0.STL`（7.6 MB）已下到 `props/robots/g1/meshes/`，
外观恢复正常（之前临时用 `torso_link.STL` 顶替）。

### G1 抬腿能力曲线（2026-10-24 DSH，`make_g1_yard.py --step-h`）

平地起跑 `vx=0.5`、8 s，只让台阶出现在前进路上（悬空台阶挪到 y=4 避免重叠）：

| 台阶高 | 位移 | 骨盆 z（末） | 结果 |
|---|---|---|---|
| 0 m（平地） | 3.64 m | 0.77 | ✅ |
| **0.02 m** | **3.05 m** | **0.90**（爬到台阶上） | ✅ 能上 |
| 0.05 m | 1.42 m | 0.13 | ❌ 摔 |
| 0.15 m | 1.25 m | 0.13 | ❌ 摔 |

**结论：官方策略的抬腿上限约 2–3 cm**（0.02 m 稳过，0.05 m 就倒）。
0.10 m 那档生成时 `terrain_tool` 报重名 geom 错误（`Element name '', id 7`），跳过未测。

### 地形编码缺陷（DSH 实测，待与 Codex 协同修）

**问题**：`village` 的地形是 8 位灰度 hfield，`size="100 100 66.5 0.01"` + `dem_wenchuan_flat.png`（128×128）：
- 网格：200 m / 128 格 = **1.56 m 一格**
- 量化：66.5 m / 255 级 = **0.26 m 假台阶**，沿网格正交排列

**影响**：真实山地是连续坡面，没有 26 cm 竖直跳变。任何机器人在这个地形上测出的"走不动/摔"都混入了编码伪影，
结论不可用。这不是"任务要求平坦"，是**数据表示的问题**。

**建议方案**：地形从 hfield 换成 **trimesh**（三角网，float 精度，坡面连续），保留全部真实起伏与坡度。

**需要 Codex 确认/配合的点**：
1. 生成链里谁读写 hfield：`build_scene.py`（写 hfield + 地面贴图）、`flatten_sites.py`（整平 footprint）、
   `polish.py` 的 `terrain_fn()`（按 hfield PNG 采样高度）、`seam_ring.py` / `reground_props.py` / `fix_grounding.py`
   都依赖 `terrain_fn`。**换 trimesh 后这些采样函数必须同步改**（改成直接对 float 高度场插值）。
2. 是否保留一份 **float 高度场真值**（如 `terrain/dem_float.npz`），供地形采样子系统共读，避免再走 8 位回环。
3. 换 trimesh 后三角面会涨：128×128 → 建议 200×200 顶点（约 8 万面），需要确认是否接受（当前场景 3.81 M）。
4. 若短期不换编码，请**明确标注**：所有机器人实验只在 `assets/yard_*.xml` / `assets/train/` 里做，
   不要用 `demo_v2x.xml` 出机器人结论（那里的台阶是假的）。

**DSH 已有的机器人侧结论（供参考）**：
- 合成起伏地形（hfield，5/10/20 cm 连续起伏）：开源 Go2 策略 10 s 走 4 m+ 不摔
- 真实村子地形（26 cm 量化台阶 + 10–30° 陡坡）：同样策略**原地不走**（不摔但也不动）
- 即：假台阶 + 陡坡都超出该策略分布；修编码只能解决前者，后者要靠在该坡度上微调

**DSH 新增资产（Codex 重建 village 后需要重跑，不要手改）**：
- `assets/train/`（训练环境 + PPO + 评测 + 开源策略接入）
- `assets/village_walk.xml`：`demo_v28` + 可走 Go2（作者 Go2HV 惯量 + 我方外观网格），由 merge 脚本生成
- `assets/train/ref/mjcf/`：参考模型的场景变体（含 `visual_100.xml`）


### DEM float 真值与 trimesh 训练分支（DSH 已完成本轮交付）

按商定方案执行：**展示场景 demo_v32 保留 hfield 碰撞不动**，float / trimesh 只服务训练与实验分支。

1. **float 高度场真值**：`terrain/dem_float.npz`
   - 由 `_tools/export_dem_float.py` 重新从 Terrarium（16 位编码）取源，**不是** 8-bit PNG 转 float
   - 49×49 格 / 200.5 m（源数据原生 4.1 m/px，已是 Terrarium 上限 z=15）
   - 海拔 866.4–932.7 m，落差 **66.2 m**（与 8 位版 66.5 m 一致）
   - 字段：`z`(float32) / `extent` / `htype` / `lat` / `lon` / `zoom`；row 0 = +Y，与 `polish.terrain_fn` 约定一致
   - **踩坑**：`fetch_dem.fetch_tile()` 把 `TILE_CACHE` 当全局用，但它定义在 `fetch_dem.main()` 里，
     从外部模块调用会 `NameError`。DSH 在自己的脚本里补了 `fetch_dem.TILE_CACHE = ...`；
     建议把 `TILE_CACHE` 提到模块级，供长期复用。
2. **trimesh 训练分支**：`train/_terrain/dem_patch.obj` + `dem_patch.xml`
   - 80 m × 80 m，2 m 网格，41×41 顶点，**3,200 三角面**
   - 落差 23.6 m；坡度 **中位 9.5° / p95 25.6°**（全域统计为 10.6° / 31.3°，同量级）
   - 射线验证：连续坡面，无量化台阶
3. **采样脚本**（`flatten_sites` / `reground_props` / `fix_grounding` / `seam_ring` / `polish`）：
   等 Codex 的 `terrain.py` 统一 API 落地后再切到 npz；DSH 侧已给出 npz 字段约定。

**风险提示**：trimesh 未接入任何展示场景；`demo_v32` 的 hfield 碰撞保持原样，村子不受影响。

### 重要更正：hfield 不是"竖直台阶"，是"假斜坡"（DSH 实测 2026-10-26）

沿村子 hfield 以 0.1 m 步长采样高度场（`python -c` 用 `polish.terrain_fn`）：

| 位置 | 0.1 m 内最大高差 | 平均高差 | 折算 1.56 m 格间高差 |
|---|---|---|---|
| y = −18 | 0.033 m | 0.006 m | 约 0.52 m |
| y = −14 | 0.017 m | 0.004 m | 约 0.26 m |

**结论**：MuJoCo 的 hfield 是**线性插值**的连续曲面，8 位量化不会产生竖直台阶，而是把高度差
摊成 1.56 m 宽的斜坡（0.26 m / 1.56 m ≈ 9.5°）。所以之前"26 cm 假台阶"的说法在机制上不准确：

- 真实障碍 = **真实坡度**（中位 10.6°，p95 31.3°）
- 量化带来的额外影响 = 叠加约 9.5° 的锯齿状假斜坡（粗糙度），不是台阶

**对训练的含义**：
- hfield 本身**可以**当碰撞体（连续、稳定），不必为了碰撞去换 trimesh；trimesh 的凸包问题反而更麻烦
- 真正要解决的是**让策略见过 10–30° 的坡**：用 `terrain/dem_float.npz` 生成高分辨率 hfield
  （如 256×256 覆盖 200 m，或局部 80 m 用 256×256），再微调/训练
- 我之前合成地形的"5/10/20 cm 起伏"实际坡度只有几度，所以机器人能走；村子是 10–30°，所以走不动——
  **两者不是同一个难度量级**



### 训练环境对齐进展（DSH，2026-10-26 至今）

**已完成的可复现链路**（同一策略在 env 里速度 0.05 → 0.9 m/s，但仍在 0.9 s 摔倒）：

| 修复 | 内容 |
|---|---|
| 奖励用相对高度 | `dz = z − ground(x,y)`，否则起伏地形判定全错 |
| 地面高度用射线 | `mj_ray` 只查 `group=1`（地面），避免打到机器人自身 |
| 动作不截到 ±1 | 参考实现是 ±100，真尺度由 `action_scale=0.25` 决定 |
| 随机出生点 | 80 m 范围随机落点 + 贴地 |
| 作者模型可选 | `DSH_MODEL=author` 用 Go2HV 惯量（已验证能走的那个本体） |
| 平面开关 | `DSH_GROUND=plane` 便于隔离地形因素 |

**仍未解决**：同一策略在 `run_ref.py`（作者场景）走 4 m/10 s，在 `env.py` 里 0.8 m/0.9 s 就摔。
已排除：模型惯量、默认角、kp/kd、dt、decimation、求解器、摩擦、动作裁剪、控制相位（warmup）、地形（平面同样摔）。

**下一步（一条命令就能定位）**：逐帧记录两边的 `target / ctrl / obs`（固定出生点、平面地面），
diff 第一处分歧。建议下次会话第一件事做这个。

**给 Codex 的提醒**：`assets/train/env.py` 目前**不能**作为可信训练环境使用；
`assets/train/run_ref.py` 是当前唯一验证过“策略能走 10 秒”的运行器。



### 行为克隆成功：自己的网络学会在真实坡度上走（DSH 2026-10-26）

**结论：`train/bc.py` 蒸馏开源策略后，我们自己的 ActorCritic（MLP 45→12）在真实 DEM 地形上能走。**

流程：
1. 用 `env_ref.py`（已验证循环）跑开源策略，采集 `obs→action` 16 envs × 800 步
2. 监督训练 ActorCritic 回归其动作（120 epoch，MSE 0.51 → **0.110**）
3. 在真实地形（80 m / 128² / 落差 23.6 m / 坡度中位 9.5°）上评估

| 种子 | 位移 | 平均速度 | 存活步数 | 结果 |
|---|---|---|---|---|
| 0 | 1.55 m | 0.27 m/s | 275 | 摔 |
| 1 | 2.30 m | 0.29 | 377 | 摔 |
| 2 | 1.50 m | 0.38 | 195 | 摔 |
| 3 | 1.46 m | 0.42 | 153 | 摔 |
| 4 | 1.41 m | 0.17 | 328 | 摔 |
| **5** | **3.23 m** | **0.27** | **500（全程）** | ✅ **没摔** |

对比：从零 PPO 训 600 万步只能挪 0.33 m；**BC 用 12.8k 样本 + 120 epoch（约 6 分钟）就到 1.4–3.2 m**。

**教训**：四足步态用 BC 初始化比从零 RL 快一个数量级以上；而 PPO 在奖励不够强时会**把 BC 学到的步态洗掉**退回站立
（实测 1200 轮 PPO 微调后位移从 1.6 m 掉回 0.25 m）。

产物：`train/bc.py`、`train/ckpt/bc.pt`（当前最好）、`train/ckpt/bc_v1.pt`（第一版）。



### DAgger 突破：自己的网络在真实坡度上稳定行走 5.4–6.1 m（DSH 2026-10-26）

在 BC 基础上做 2 轮 DAgger（学生自己走→老师给标签→重训），结果**全面超过老师**：

| 种子 | 位移 | 平均速度 | 存活 | 结果 |
|---|---|---|---|---|
| 0 | 5.53 m | 0.54 m/s | 500（全程） | ✅ 不摔 |
| 1 | 5.73 | 0.57 | 500 | ✅ |
| 2 | 5.64 | 0.56 | 500 | ✅ |
| 3 | 6.09 | 0.60 | 500 | ✅ |
| 4 | 5.40 | 0.54 | 500 | ✅ |
| 5 | 5.47 | 0.55 | 500 | ✅ |

- 地形：真实 DEM，80 m，落差 23.6 m，坡度中位 9.5° / p95 25.6°
- 老师（开源 TorchScript）在同一地形上是 2.82 m / 10 s；**学生 5.4–6.1 m**，因为 DAgger 让学生覆盖了老师会摔的状态
- MSE 0.80 → 0.0795

**可复现命令**：

```powershell
cd assets/train
$env:DSH_MODEL="author"; $env:DSH_ENV="ref"
$env:DSH_TERRAIN_PNG="$PWD\_terrain\dem80_128.png"
$env:DSH_HFIELD_HALF="40"; $env:DSH_RELIEF="23.64"; $env:DSH_RELIEF_SCALE="1.0"
& $mjpy dagger.py --rounds 2 --envs 24 --steps 350 --epochs 50   # 约 6 分钟
& $mjpy eval.py --ckpt ckpt/bc.pt --n 6
```

产物：`train/dagger.py`、`train/ckpt/bc.pt`（当前最佳）、`train/ckpt/bc_before_dagger.pt`（DAgger 前）。

**结论：步态不是 RL 从零练出来的，是"蒸馏 + DAgger"学出来的；PPO 微调必须在奖励调好之后再做。**



### 村子落地测试：训练后的策略在村口站住不动（DSH 2026-10-27）

把 `train/ckpt/bc.pt`（在 80 m 真实 DEM 上走 5.4–6.1 m 的那个学生）放进 `assets/village_walk.xml`：

| 出生点 | 地面高 | 位移 | vx | 结果 |
|---|---|---|---|---|
| (12, −18) H1 门前 | 5.49 | 0.21 m | 0.00 | 站住（不摔，倾角 cos 0.87） |
| (15, −14) H1 台地 | 5.49 | 0.04 m | −0.01 | 站住（cos 1.00） |
| (10, −12) | — | 0.19 m | −0.02 | 站住 |
| (18, −12) | — | 0.09 m | 0.01 | 站住 |

**结论：村子地形仍在策略分布之外。** 与老师（开源策略）在村子里的表现一致（也是站住），
说明不是我们蒸馏/DAgger 的问题，而是**村子这一份 hfield 的难度更高**：

| | 训练地形 | 村子地形 |
|---|---|---|
| 覆盖 / 分辨率 | 80 m / 128²（0.62 m/格） | 200 m / 128²（1.56 m/格） |
| 量化造成的假坡度 | **8.4°** | **9.5°** |
| 真实坡度 | 中位 9.5° / p95 25.6° | 中位 10.6° / p95 31.3° |
| 训练时见过 | ✅ | ❌ |

**两个可选方向**：
1. **把训练地形改成 200 m / 256²**（量化 0.09 m → 假坡 3.3°），更接近村子实际，再重训一轮 BC+DAgger（约 10 分钟）；
2. 或接受现状：策略用于「和训练同分布的地形」，村子只做静态展示。

**工具**：`train/village_walk_test.py --at X Y [--shots 2,5]`，用 `polish.terrain_fn` 取地面高度避免射线打到机器人。



### 按村子参数重训 Go2：在「村子同款地形」上 6/6 稳定行走（DSH 2026-10-27）

训练地形换成 **与村子同一张 hfield**（`terrain/dem_wenchuan_flat.png`，200 m / 128² / 落差 66.5 m），
BC(100 epoch) + DAgger(2 轮) 重训后评估：

| 种子 | 位移 | 平均速度 | 存活 | 结果 |
|---|---|---|---|---|
| 0 | 3.21 m | 0.18 | 500 | ✅ |
| 1 | 2.73 | 0.13 | 500 | ✅ |
| 2 | 3.66 | 0.20 | 500 | ✅ |
| 3 | 3.77 | 0.24 | 500 | ✅ |
| 4 | 3.32 | 0.14 | 500 | ✅ |
| 5 | 3.47 | 0.18 | 500 | ✅ |

**即：在用户真实 DEM（村子同款）地形上，Go2 6/6 都能走 2.7–3.8 m 不摔。**
渲染证据：`train/shots/terrain_k250.png`（`render_walk.py` 生成）。

**但把同一策略放进 `assets/village_walk.xml` 仍然站住**（8 个出生点全部 0.04–0.9 m）。
已排除：接触设置（cone/impratio 已按训练覆盖）、出生高度（改用只认 hfield 的射线，5.48 正确）、出生点（open spots 也站住）。

剩余怀疑（下一轮第一件事）：
1. **village_walk.xml 里机器人周围有不可见碰撞体**（H1 门洞墙、接缝碎石、道具）挡住去路 → 打印 `d.ncon` 与接触 geom 名
2. **模型装配差异**：village_walk 用 `go2_visual`（带 mesh 外观 geom）而训练用 `go2_nomesh`
3. 村子 `<option cone="elliptic" impratio="10" timestep="0.002">` 与训练不同（测过覆盖，但仍需确认 `flag`）

**结论口径**：*Go2 已能在「我的地形（真实 DEM）」上行走*；**村子展示场景**还需要一次装配对齐。



### 关键定位：Go2 在村子地形上确实能走（DSH 2026-10-27 本轮）

**新证据**：`assets/village_go2_plain.xml` = 村子同款 hfield（200 m / 128² / 66.5 m）+ 带外观的 Go2（无村子道具）。

| 场景 | 位移 | vx | 结果 |
|---|---|---|---|
| `village_go2_plain.xml`（纯地形） | **3.89 m / 10 s** | 0.25 m/s | ✅ 不摔 |
| 渲染（`render_walk.py`，k=400） | 2.64 m | — | ✅（`shots/terrain_k250.png`） |
| `village_walk.xml`（地形 + 全部村子道具/建筑） | 0.04–0.9 m | ~0 | ❌ 站住/倾倒 |

**结论：问题不在策略、不在 hfield，而在 `village_walk.xml` 的村子道具/碰撞体**——
机器人周围有碰撞 geom（H1 不可见墙、接缝碎石、草/石、瓦砾），出生即被夹住或绊倒。
用 87 个体素点扫描“无遮挡点”后仍然站住/倾倒，说明道具碰撞分布很密。

**下一步（下一轮）**：
1. 给 `village_walk.xml` 里的**非地形 geom 关掉碰撞**（`contype=0`，或只保留 H1/H6 墙体），做成“可行走村子”
2. 或在 `village_go2_plain.xml` 上加**只用于外观的** props（contype=0）+ 一条土路贴图 → 既是村子又不会挡住
3. G1 侧：`assets/g1_terrain_plain.xml` 已生成（官方 12dof + 村子地形），但 `g1_policy.py` 依赖 keyframe，
   地形场景没有 keyframe → 出生位置不对（z 0.88、位移 0）。需要写一个“按地形贴地出生”的 G1 运行器，
   再接 DAgger（官方策略抬腿上限 2–3 cm，直接跑陡坡必摔）。

**当前可交付口径**：机器狗 Go2 已能在「用户真实 DEM 地形」上稳定行走（3.9 m / 10 s，6/6 不摔）；
村子展示场景还需一次“道具碰撞降级”；人形 G1 尚需贴地出生 + 地形策略。



### G1 也在地形上走起来了（DSH 2026-10-27 本轮）

给 `_tools/g1_policy.py` 加了 `--at X Y`：地形场景没有 keyframe 时，按 hfield 射线贴地出生（骨盆 +0.78 m）。

```powershell
& $mjpy assets/_tools/g1_policy.py --xml assets/g1_terrain_plain.xml --vx 0.5 --seconds 8 --at 15 -14
# 结果：位移 3.64 m / 8 s（x 15 → 18.64），骨盆 z 6.24~6.26（地形 5.48 + 0.77），航向 −0.10 rad
```

| 机器人 | 场景 | 结果 |
|---|---|---|
| **Go2** | 村子地形纯场景 `village_go2_plain.xml` | **3.89 m / 10 s（0.25 m/s）不摔** |
| **G1** | 村子地形（H1 台地，平整区）`g1_terrain_plain.xml` | **3.64 m / 8 s，骨盆 0.77 m 稳定，航向 −0.10 rad** |

**口径**：
- Go2：能在真实 DEM 起伏地形上走（含 9.5° 量化假坡与 10–26° 真实坡）
- G1：能在**地形上的平整区**走（官方策略抬腿上限 2–3 cm，坡面/台阶仍不行）

**尚未完成**：① `village_walk.xml`（带全部道具）里 Go2 仍被碰撞体挡住，需要道具碰撞降级；
② G1 在坡面上走需要像 Go2 那样做“蒸馏 + DAgger”（官方策略只适应平地）。



### 村子可走场景：锁定为「地形 + 机器人」（DSH 2026-10-27 第 2 轮）

本轮继续排查“同一策略在纯地形能走、放进村子站住”的原因，做了 5 组对照：

| 场景 | 改动 | 结果 |
|---|---|---|
| `village_go2_plain.xml` | 只有 hfield + 机器人 | ✅ 3.44–3.89 m |
| `village_walk2.xml` | 运行时把 1096 个 geom 的碰撞全关 | ❌ 0.22 m |
| `village_walk3.xml` | 文本注入 `contype=0`（保留地形） | ❌ 0.04 m |
| `village_walk5.xml` | 再把 93 个 `freejoint` 去掉（塌块变静态） | ❌ 0.04 m |
| **`village_walk4.xml`** | **去掉 600 个非机器人 body，只留地形 + 机器人** | ✅ **3.89 m / 10 s（0.25 m/s）** |

**已排除**：碰撞体（关到只剩 28 个）、质量（清零无变化）、积分器/cone/impratio、执行器限制（ctrlrange/gear 相同）、
机器人质量与惯量（15.21 kg 完全一致）、观测（同状态下 obs 最大差 **0.000**）、摩擦（相同）。

**结论**：模型里那 600 个额外 body（村子道具/塌块）本身就会让这台机器人“走不动”，即使它们不参与碰撞。
最可能是 MuJoCo 求解器在这些 body 存在时的数值行为差异（ncon/约束排序），具体机制未进一步追。
**工程结论：可行走的村子场景 = `assets/village_walk4.xml`（真实村子 hfield + 机器人）。**

**两台机器人现状（本轮验收）**：
| 机器人 | 场景 | 结果 |
|---|---|---|
| Go2 | `village_walk4.xml` | 3.89 m / 10 s，0.25 m/s，不摔 |
| G1 | `g1_terrain_plain.xml` @ H1 台地 | 3.64 m / 8 s，骨盆 0.77 m 稳定 |

**下一轮**：往 `village_walk4` 里**逐个加回**村子的可视 props（每次加一类，验证能走），
目标是“看着是村子、机器人还能走”的场景；以及 G1 的坡面 DAgger。



### 第 3 轮：二分定位与结论收敛（DSH 2026-10-27）

继续二分“为什么村子场景走不动”：

| 实验 | 结果 |
|---|---|
| `village_walk4`（地形 + 机器人，14 body） | ✅ 3.44–3.89 m |
| `village_walk4` + 600 个空 body（无 geom） | ✅ 3.44 m（**body 数量本身不是原因**） |
| `village_walk4` 改用村子物理（impratio=10 / elliptic / dt 0.002 × 10） | ✅ 3.13 m（**物理设置不是原因**） |
| `village_walk5`（611 body，道具碰撞全关） | ❌ 0.04 m |
| 只留 H 建筑（12 body，碰撞关） | ❌ 0.04 m |
| 只留 树/枫树（120 body，碰撞关） | ❌ 0.04 m |
| 只留 grass / chunk（碰撞关） | ❌ 0.04 m |

**结论**：只要模型里存在**带 geom 的村子 body**（哪怕碰撞全关、哪怕只剩一类），
这台机器人就走不动；而**空 body 加 600 个也没事**。说明问题出在“带实例化 mesh 的 body/geom”
参与了某个全局过程（最可能 `mj_collision` 的 geom 配对/空间排序或 `mj_forward` 里的几何量计算），
具体机制未能在本轮定位。

**工程结论（可交付）**：可行走场景用 `assets/village_walk4.xml`（地形 + 机器人）。
若需要“村子外观”，建议把村子**烘焙地面贴图**挂到 `village_walk4` 的 hfield 上（下一步），而不是把 598 个 body 搬进来。



### 第 3 轮收尾：两台机器人都在「真实村子地形」上动起来了（DSH 2026-10-27）

**交付物**：`assets/village_walk4.xml`（真实村子 hfield + **村子烘焙地面贴图 `tex/ground_baked_hd.png`** + Go2）
与 `assets/g1_terrain_plain.xml`（同一份地形 + G1）。

| 机器人 | 场景 | 结果 | 证据 |
|---|---|---|---|
| **Go2** | `village_walk4.xml`（带地面贴图） | **3.89 m / 10 s，0.25 m/s，不摔** | `train/shots/village_t05.0.png`（能看到草地/土路） |
| **G1** | `g1_terrain_plain.xml` @ (15,−14) | **3.64 m / 8 s，骨盆 0.77 m，航向 −0.10 rad** | 控制台输出 |

复现：

```powershell
cd assets/train
& $mjpy village_walk_test.py --xml ../village_walk4.xml --seconds 10 --at 12 -18 --shots "2,5,8.5"
& $mjpy ../_tools/g1_policy.py --xml ../g1_terrain_plain.xml --vx 0.5 --seconds 8 --at 15 -14
```

**已知边界**：带 598 个道具 body 的完整 `demo_v32` 场景仍不能跑机器人（第 2/3 轮已二分，
现象与“带 geom 的 body 即使用一类、碰撞全关也让机器人不动”一致，机制未定位）。
展示用 `demo_v32`（静态出图），行走演示用 `village_walk4` / `g1_terrain_plain`（同一份地形）。



### 为什么 run_scene.py 里机器人不动（DSH 2026-10-27）

**结论：`run_scene.py` 打开的是 `demo_v32.xml`（展示场景），那里的机器人是固定基座 + 没有任何控制器，
它只做“被动播放物理”，所以永远不动（只会看到废墟落定）。**

`village_walk4.xml` 单独用 viewer 打开同样不会走——XML 只描述物理，**动起来靠的是策略闭环脚本**
每 0.02 s 计算力矩写入 `d.ctrl`。

**看机器人真的走起来，默认入口已经切到行走模式**：

```powershell
cd C:\Users\18967\Desktop\git\assets\train
& $mjpy watch_village_walk.py --follow          # Go2 在村子地形上走（交互窗口，相机跟随）
& $mjpy ../_tools/g1_policy.py --xml ../g1_terrain_plain.xml --vx 0.5 --seconds 8 --at 15 -14
# 无窗口自检：
& $mjpy watch_village_walk.py --headless --seconds 10   # 实测位移 3.97 m / 10 s
```

`watch_village_walk.py` 与 `run_scene.py` 的区别：前者每 0.02 s 调一次策略并写力矩，后者只 `mj_step`。

### run_scene.py 也能看机器人走了（`--walk`，DSH 2026-10-27）

**用法**：

```powershell
cd C:\Users\18967\Desktop\git
& $mjpy run_scene.py                   # 默认打开村子展示场景，Go2 + G1 行走，相机跟随
& $mjpy run_scene.py --static          # 只看原来的静态展示场景
& $mjpy run_scene.py --walk --no-follow # 相机固定视角
& $mjpy run_scene.py --walk --headless 5   # 不开窗口，报位移
& $mjpy run_scene.py --walk --shot 4       # 第 4 秒存图
```

**原理（重要）**：`demo_v32` 那 598 个道具 body 会让策略闭环失效（第 2/3 轮已二分，机制未定位），
所以采用“孪生场景 + 位姿镜像”：

1. Go2 物理在 `assets/village_walk4.xml` 跑 BC/DAgger 策略；
2. G1 物理在 `assets/g1_village_final.xml` 跑官方 `motion.pt` 平地策略；
3. 每帧把两台机器人的根部位置/姿态和 12 个腿部关节角写到 `demo_v32` 的 Go2/G1 展示模型，再 `mj_forward`；
4. viewer 渲染的始终是 `demo_v32`（完整村子外观）。

**实测**：`run_scene.py --walk --headless 5` → 展示模型里 Go2 位移 **2.30 m**、G1 位移 **2.22 m**；
`--shot 4` 出图 `shots/scene_walk_t4.0.png`（能看到 Go2 与 G1 同时在废墟前迈步）。

**局限**：G1 使用官方平地策略，只适合 H1 前平整区；遇到 2–3 cm 以上台阶仍会摔。

**入口调整（2026-10-27）**：`run_scene.py` 无参数时默认进入上述 Go2 + G1 行走模式；原静态展示必须显式加 `--static`。

### 穿模（穿地/穿墙）根因与修复（DSH 2026-10-27）

用户反馈“会走路但穿模”，定位到 3 个原因：

| # | 原因 | 证据 | 修复 |
|---|---|---|---|
| 1 | **孪生场景与展示场景用的不是同一张地形** | `demo_v32.xml` 的 hfield 是 `terrain/height_field_patch.png`，而物理孪生是 `terrain/dem_wenchuan_flat.png`；两者 hfield 数据最大差 **0.0392 → 2.608 m** | 新建 `assets/village_walk4_patch.xml`（改用 patch 地形），数据差 **0.000000**；`run_scene_walk.py` 的 PHYS 指向它 |
| 2 | **出生点落在 H1 废墟碰撞盒内** | H1 碰撞盒约 x 8.2–21.8 / y −20.3–−7.7；原出生 (12,−18) 在盒内，狗直接从墙里穿出去 | Go2 出生点改 **(0, −20)**（空地，走 3.58 m/8 s） |
| 3 | ~~**G1 的镜像循环未对齐，会塌**~~ | 已修正；G1 现在使用官方 12dof 模型，pelvis 正常约 0.77 m | **默认开启**；出生 `(0,−17.5)`，8 s 实走 2.59 m |

**使用方法**：

```powershell
cd C:\Users\18967\Desktop\git
& $mjpy run_scene.py                  # Go2 + G1 同区持续行走（默认）
& $mjpy run_scene.py --no-g1          # 只驱动 Go2
& $mjpy run_scene.py --no-demo-reset  # 关闭自动复位，用于真实翻倒测试
& $mjpy run_scene.py --reset-after 8  # 修改展示复位周期
& $mjpy run_scene.py --static         # 原静态展示
& $mjpy run_scene.py --walk --check 4 # 4 秒后报身高
& $mjpy run_scene.py --walk --shot 3  # 近景存图
```

**镜像方案的边界**：Go2 和 G1 现在都带 610 个村庄碰撞代理（建筑 28 + 石头 240 + 其它道具 342）；
其中 178 个是原先会穿模的接缝小石头。
Go2 使用 `(-12,−17)` 西侧通道，G1 使用 `(0,−17.5)` 车道，8 s 后间距约 **13.4 m**。
两台机器人仍各自在轻量物理场景中计算，再把位姿镜像到完整村子；展示层增加 1.5 m 最小间距保护，
异常接近时自动复位。它们目前仍不会互相产生真实物理接触力。

### 给物理孪生加碰撞代理（DSH 2026-10-28）

**问题**：镜像方案里展示场景的机器人没有碰撞，走向墙/石头会穿过去。

**做法**：`train/make_twin_proxies.py` 从 `demo_v32` 里提取
① 所有 `*_collision` 建筑碰撞体（box/cylinder）；② 行走区域（±45 m）内半径 > 1.2 m 的石头/瓦砾锥，
把它们作为**静态不可见几何**写进孪生场景，生成 `assets/village_walk_props.xml`（共 57 个代理）。

`run_scene_walk.py` 的 `PHYS` 已指向该文件；Go2 默认出生点 (0, −20)（空地）。

**实测**：

| 出生点 | 结果 |
|---|---|
| (0, −20) 空地 | 走 **3.58 m / 8 s**（无阻挡，正常行走） |
| (2, −10) 朝 H1 墙 | 只走 **1.31 m** 就停下（撞墙/石头，不再穿过去） |
| (6, −18) | **0.64–0.70 m** 停下（被代理挡住） |

**副作用与注意**：
- 石头代理是**球体近似**（半径 0.85×rbound），比真实石头略大，可能会“隔空”挡一下；
- 出生点如果落在代理内部，机器人会被弹飞（曾出现翻倒）→ 默认出生点固定用 (0, −20)；
- 相机默认框住两台；`--no-g1` 时只跟 Go2。

### 全量碰撞代理（DSH 2026-10-28 第二轮）

上一版只代理了「建筑碰撞体 + 半径>1.2 m 的大石头」，**小瓦砾/木板/短柱没有代理**，狗仍会穿过去。
本轮新增 `train/make_twin_proxies_all.py`：把 `demo_v32` 里除地形/机器人外、
**半径 ≥ 0.35 m 的所有实体 geom** 都做成不可见球代理（半径 = 0.5 × rbound）。

| 参数 | 代理数 | (0,−20) 行走 | (2,−10) 朝墙 |
|---|---|---|---|
| min_r 0.35 / scale 0.5（采用） | **640** | **3.58 m / 8 s** ✅ | **1.31 m 停下** ✅ |
| min_r 0.20 / scale 0.7（太密） | 674 | 0.43 m ❌ 被夹死 | — |

`run_scene_walk.py` 的 `PHYS` 现指向 `assets/village_walk_props_all.xml`。

**残余穿透实测**（MuJoCo 接触 `dist`，负=压入）：最深 **−0.020 m（2 cm）**、平均 −0.004 m，
属于 MuJoCo 软接触的正常量级，肉眼基本不可见。

**若仍看到穿模，需要用户指明**：是①狗腿/脚陷地、②狗身体穿石头/木板、③人形穿模、④房子穿模，
以及用的是哪条命令（`run_scene.py` / `--g1` / `--static` / `watch_village_walk.py`）。



### 石头穿模修复：按“石头”单独做更贴合的代理（DSH 2026-10-28 第三轮）

用户明确“石头穿模”。原因：之前全量代理对石头用的是 `0.5 × rbound` 的球，明显**小于**真实石头，
狗身体会压进石头外侧。

本轮新增 `train/make_twin_proxies_final.py`，分三类代理：

| 类型 | 规则 | 数量 |
|---|---|---|
| 建筑 | 所有 `*_collision` 的 box/cylinder 原样搬 | 28 |
| **石头** | body 名含 rock/boulder/slab/stone/stump/debris_cone，`0.9 × rbound` 球 | **62** |
| 其它道具 | 半径 ≥ 0.35，`0.5 × rbound` 球 | 489 |

产物 `assets/village_walk_final.xml`，`run_scene_walk.py` 的 `PHYS` 已指向它。

**实测**：

| 出生点 | 结果 |
|---|---|
| (0, −20) 空地 | 走 3.14 m / 8 s ✅ |
| (−6, −22) 石头区边 | 走 3.64 m / 8 s ✅ |
| (2, −10) 朝 H1 | 1.31 m 停下 ✅ |
| (5.4, −19.8) 石头正前方 2 m | 5.40→5.41 原地停（被石头代理挡住） |

**残余**：与建筑/石头代理的接触穿透 0.000（无深穿）；石头代理仍是球体（0.9×rbound），
扁平大石头用球会略大，但已不会“穿进去”。

### Go2 约 12 秒翻倒：已定位，不是碰撞代理（2026-10-28）

`run_scene.py --check N` 现在输出根节点位置、`up_z`、首次越过 0.9/0.5/0 倾角阈值的时间和接触体。

实测本次默认路线 `(0, -20)`：

| 时间 | 状态 |
|---|---|
| 10.00 s | `up_z=0.998`，正常直立 |
| 12.16 s | `up_z=0.874`，开始失衡 |
| 12.32 s | `up_z=0.492`，接近翻倒 |
| 12.64 s | `up_z<0`，完全倒置；接触只有 `world <-> FL_hip` |

对照组：不使用 640 个碰撞代理，直接跑原始 `assets/village_walk4.xml`，同样在 **11.9 s** 翻倒。

**结论**：翻倒不是最近新增的建筑/石头碰撞代理造成，也不是出生穿模。当前 `ckpt/bc.pt`
只验证了 10 秒级稳定行走（此前评测均为 500 步），约 12 秒后策略已超出已验证轨迹，
且它是无感知的速度跟踪策略，遇到地形或姿态误差后没有恢复能力。

**下一步（按优先级）**：
1. ~~展示场景先加安全策略：`up_z < 0.5` 或固定周期自动复位~~ ✅ 已实现：默认 8 s 复位，可用 `--no-demo-reset` 关闭。
2. 训练端把 episode 从 500 步延长到 1500–3000 步，并随机化出生点、初始姿态、外力扰动和 10–30° 局部坡度。
3. 增加跌倒恢复策略，或在 `up_z < 0.5` 时切到恢复控制器，而不是继续给前进速度指令。
4. 需要绕开石头时，再加入局部地形/障碍观测；当前策略没有视觉或障碍感知，不能靠调参数解决。

### 小石头穿模与场景悬空修复（2026-10-28）

**小石头穿模**：代理生成器原先只把 body 名含 rock/stone 等关键词的石头加入碰撞；
`seam_H*_*` 接缝小石头半径大多小于 0.35 m，被归入“小道具”后直接漏掉。

修复：

- `make_twin_proxies_final.py` 新增 `--seam-min-r`，默认 **0.15 m**；
- 所有 `seam_*` 小石头按 `0.9 × rbound` 建球代理；
- 新增 **178** 个接缝小石头代理；
- 当前代理合计 **610**：建筑 28 + 石头 240 + 其它道具 342；
- `village_walk_final.xml` 与 `g1_village_final.xml` 已同步重建。

加入小石头代理后，Go2 原出生 `(0,-20)` 距 `seam_H1_0` 过近，测试会立即失衡；
出生点已移到 **`(1,-20)`**。8 秒实测前进 **2.94 m**，`up_z=0.999`。

**场景悬空**：静态场景 `run_scene.py --static` 会预跑 2500 步让 93 个自由关节楼板/碎块落地；
行走模式此前跳过了该步骤。现在 `run_scene_walk.py` 默认也预跑 **2500** 步，然后只恢复
Go2/G1 展示关节，保留瓦砾落地后的姿态。稳定后扫描：高于地面 0.35 m 的场景物体为 **0 个**。

可用 `--settle-steps 0` 关闭启动落地；正常展示不要关闭。

### 双机器人穿模修复（2026-10-28）

原因：Go2 与 G1 的物理求解仍是两个独立场景，镜像到 `demo_v32` 后没有机器人间碰撞体；
原先两者的 8 秒路线会在同一处汇合，间距只剩约 0.7 m。

修复：

- Go2 出生点和路线移到西侧 `(-12,-17)`；
- G1 保持已验证稳定的 `(0,-17.5)` 车道；
- 8 秒实测：Go2 **3.19 m**、G1 **3.64 m**，两机间距 **13.38 m**；
- 新增 `--min-separation`，默认 **1.5 m**，异常接近时自动复位；
- 可用 `--go2-start X Y` / `--g1-start X Y` 调整两条车道；
- 相机只在启动时按双机间距自动取景，之后允许用户滚轮缩放。

### 双机器人同区展示：基础要求已完成（2026-10-28）

`run_scene.py` 无参数现在默认：

- 同时驱动 Go2 + G1；
- Go2 从 `(-12,-17)` 起步，G1 从 `(0,-17.5)` 起步；
- 相机跟随两台中点；
- 每 8 秒自动复位，或任一机器人 `up_z<0.5` 时立即复位；
- `--headless 18` 实测复位 2 次，最终仍直立；
- 8 秒同框实测：Go2 **3.19 m**，G1 **3.64 m**，间距 **13.38 m**。
- G1 物理场景已切到 `g1_village_final.xml`，包含 28 个建筑、240 个石头、342 个其它道具碰撞代理；
  `(0,-17.5)` 起步 8 秒实走 **2.59 m**，不再穿过村庄障碍。

这满足“在我的环境中看到机器人和机器狗行动”的展示要求，但**不等于长时自主可靠性**。科研级闭环仍缺：

1. 长时稳定策略：Go2 无复位时约 12 秒翻倒，训练 episode 仍偏短；
2. G1 粗糙地形策略：官方策略只适合平地/缓坡，2–3 cm 台阶就困难；
3. 障碍感知与路径规划：当前机器人没有视觉/局部地图，不能自主绕开石头和废墟；
4. 统一物理场景：两台机器人目前在各自轻量孪生中计算，再镜像进完整村子，不会互相碰撞；
5. 二次坍塌联动：触发器框架已有，但可塌结构与机器人感知/决策尚未连接；
6. 任务层：搜索点分配、路径规划、到达判定和救援行为还没有接入。

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
- 2026-10-24 Codex：H1 图集修复（15 个材质换 `ruin_uk_atlas_0`），产出 demo_v28.xml；SCENE_GUIDE 补 yard 验证场景与机器人纪律；入口切到 v28
- 2026-10-24 Codex：入口切到 demo_v29（670/1154，含 Go2+G1），SCENE_GUIDE 同步 v29 与 run_walk/run_g1，清理旧中间版本
- 2026-10-24 DSH f8617d8：**G1 人形导入 MuJoCo** —— 官方 `g1_description/g1_29dof.xml` 自带 MuJoCo 格式（36 个 STL + 29 个 motor + `<joint type="free">`），新增 `import_g1.py`：并行下网格(19.1 MB)→motor 改 position(kp=150)→加地面/光/相机→按真实最低顶点贴地；出 `g1_scene.xml`(固定基座，脚底 z=0.0004 m) 与 `g1_free.xml`(浮动基座，无控制器 2 s 内摔到 0.111 m，符合预期)；新增 `run_g1.py`、`check_g1.py`
- 2026-10-24 DSH：**验证场景 `yard_v1.xml`** —— 引入宇树 `terrain_tool`（BSD-3，见 `_tools/unitree_terrain/`，已打懒加载补丁：cv2/noise 缺失也能跑，PIL 兜底写高度图，并修了 `AddHeighFieldFromImage` 的 `255 - position` bug）。`_tools/yard.py` 生成 30 m 小院：台阶 6×0.15 m + 悬空台阶 gap 0.1 m + 碎石阵 8×8(0.5 m 块) + Perlin 起伏 ±0.2 m，注入 H1 房子（顺带修好它缺贴图的问题，改用共享图集）与 Go2；静止 0.8 s 后 base z=0.271 m 站住。文件整理：清掉一次性脚本，`render_yard.py` 保留为出图入口
- 2026-10-24 DSH 69e3d8c：float DEM 真值 `terrain/dem_float.npz`（49×49 / 200.5 m / 66.2 m 落差）+ trimesh 训练分支 `train/_terrain/dem_patch.xml`（80 m / 3200 面），展示场景 hfield 未动
- 2026-10-24 Codex：修 `fetch_dem.py` 的 `TILE_CACHE` 作用域（提到模块级）；新增 `_tools/terrain.py` 统一采样（HfieldSampler row0=-Y / FloatDEMSampler row0=+Y）；SCENE_GUIDE 明确 demo_v2x 不出机器人结论
