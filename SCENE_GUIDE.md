# 野外救灾 MuJoCo 场景指南

这份文档回答三个问题：场景现在有什么、它是怎么一步步生成的、每个文件/参数是做什么的。

## 1. 当前场景

- 场景文件：`assets/demo_v29.xml`（v28 环境 + P0 上的 Go2 与 G1，固定基座展示）
- 规模：670 body / 1154 geom / 13 相机 / 10 site，约 4.62 M 三角面
- 入口：`run_scene.py`（交互窗口）、`outdoor_scene.py`（优先加载 v29，缺失时回退程序化场景）
- 解释器：`C:/Users/18967/anaconda3/envs/mujoco/python.exe`（MuJoCo 3.3.2）

## 2. 文件地图

| 路径 | 作用 |
|---|---|
| `run_scene.py` | 加载 `demo_v27.xml`，预跑 2500 步让瓦砾落定，再打开 MuJoCo viewer |
| `outdoor_scene.py` | 场景启动入口；v27 不存在时回退到程序化户外场景 |
| `assets/demo_v27.xml` | 最终 MJCF 场景（地形 + 道路 + 建筑 + 植被 + 道具 + 相机 + site） |
| `assets/buildings.json` | 村落布局配置：7 栋房、主路折线、封路点、堆积锥 |
| `assets/_tools/` | 全部生成、导入、后处理工具（下节逐个说明） |
| `assets/props/imported/` | 真实扫描模型：H1/H2/H5/H6/H7、枫树、草块等 |
| `assets/props/` | Poly Haven 道具：岩石、树桩、枯枝、报废车、隔离墩、轮胎 |
| `assets/terrain/` | 汶川 DEM 高度图和平滑/整平后的 PNG |
| `assets/tex/` | 地面、砖墙、混凝土等贴图 |
| `assets/generated/` | 烘焙地面贴图等生成物 |
| `AGENTS.md` | 两个代理的交接记忆：当前状态、踩坑、下一步 |
| `ASSETS.md` / `assets/README.md` | 素材来源、授权和详细说明 |

## 3. 场景由什么组成

| 部分 | 内容 | 说明 |
|---|---|---|
| 地形 | 汶川真实 DEM，200 m 见方，落差 66.5 m | `hfield` + 烘焙地面贴图；房子 footprint 用局部整平 |
| 道路 | 主路 4.2 m + 7 条入户支路 3.0 m + 岔口补丁 | 全部烘进 2048² 地面贴图，不是独立 3D 路面 |
| 建筑 | H1 砖房废墟、H2 木屋、H5 木屋、H6 混凝土塌楼、H7 塌墙 | 真实模型 + 不可见碰撞墙（门洞可通行） |
| 占位房 | H3、H4 | 程序化方盒房，等真实素材替换 |
| 植被 | 30 棵真实枫树（CC-BY 双面）、118 棵程序化针叶、45 簇草、24 块岩石 | 枫树用 Sketchfab 扫描件，针叶为几何体 |
| 道具 | 报废盖布车、水泥隔离墩、旧轮胎、树桩、枯枝 | Poly Haven CC0 扫描件 |
| 封路 | 3 处共 35 块瓦砾 | 制造 UGV 绕行/清理场景 |
| 堆积锥 | H1 26 块、H6 22 块 | 从墙根向外呈锥形铺开，模拟真实倒塌堆积 |
| 相机 | `wide` / `close` / `village` / `top` / `cam_H1`…`cam_H7` | 12 个视角 |
| 标记点 | `site_H1`…`site_H7`、`site_P0` | `group=3`，不渲染但坐标可供任务分配读取 |

## 4. 生成链（核心）

场景不是手写一个 XML，而是按固定顺序由脚本生成。换任何素材或布局，都建议按这个顺序重跑：

```text
build_scene.py（地形+基础道具）
  → tune.py（材质/曝光）
  → scatter.py（植被/废墟）
  → village.py（村落布局，读 buildings.json）
  → slim_rocks.py（石头瘦身）
  → optimize_trees.py（程序化树减量/收细）
  → flatten_sites.py --band 11（房子 footprint 局部整平）
  → reground_props.py（树/石/草按新地形贴地）
  → fix_grounding.py --no-platform（房子按地形落位，不加台地）
  → remove_plinths.py（删除混凝土基座）
  → polish.py --ground-tex --grass-count 60（地面/草/封路/堆积锥）
  → seam_ring.py --band 11（接缝碎石环）
```

各步骤作用：

| 脚本 | 作用 |
|---|---|
| `build_scene.py` | 读 DEM 生成 hfield，摆基础岩石/车辆/废墟，输出初版场景 |
| `tune.py` | 换混凝土材质、调地面颜色/重复度、主光强度和曝光 |
| `scatter.py` | 加密针叶树、岩石、草；生成半塌砖房和废墟块 |
| `village.py` | 按 `buildings.json` 摆 7 栋房、道路、集结点、site、碰撞盒；会清掉村内/路上的树 |
| `slim_rocks.py` | 控制岩石面数（否则场景面数会从 3.8 M 涨到 8 M 以上） |
| `optimize_trees.py` | `--keep 90 --slender 0.72`：程序化树减量并收细轮廓 |
| `flatten_sites.py` | `--band 11`：在房子 footprint 内整平 hfield，边缘 11 m smoothstep 过渡 |
| `reground_props.py` | 地形变化后，用射线把树/石/草重新贴到地面 |
| `fix_grounding.py` | 按房子 footprint 最高地面落位；`--no-platform` 表示不再加土色台地 |
| `remove_plinths.py` | 删除 village.py 给房子加的混凝土基座（`plinth_*` / 旧位置兜底） |
| `polish.py` | 最终地面纹理、草量、封路瓦砾、H1/H6 堆积锥 |
| `seam_ring.py` | 在整平区边缘（footprint + band）撒接缝碎石，`--band` 必须等于 flatten 的 band |

换真实模型时还会用到导入链：

```text
convert_multi.py（glTF/GLB 按材质拆分、减面、过滤材质）
  → import_gltf.py / import_building.py（转成 MuJoCo 可读 OBJ + PNG）
  → fix_obj_faces.py（修 OBJ 面索引）
  → prune_imported.py（清理转换中间文件）
```

辅助脚本：`add_collision.py`（补不可见碰撞墙）、`double_side.py`（枫叶双面）、`bake_ground.py`（道路烘进地面）、`check_floating.py`（悬空检查）、`check_refs.py`（引用检查）、`layout_check.py`（压路/重叠检查）、`decimate_obj.py`（减面）、`collapse_trigger.py`（二次坍塌触发器框架）。

## 5. XML 是怎么组织的

`demo_v29.xml` 是标准 MJCF：

- `<asset>`：hfield 地形、texture 贴图、material 材质、mesh 模型（每栋真实房子的分件都在这里）
- `<worldbody>`：地面、太阳光、房子 body、道具 body、植被 body、camera、site
- `<equality>`：weld 约束（目前主要用于未来可塌结构；`collapse_trigger.py` 按它解锁）
- `<visual>` / `<statistic>` / `<option>`：渲染、相机初始范围、时间步和重力

每个建筑是一个 `<body name="H1">`，内部挂若干 `<geom type="mesh">`；碰撞墙是单独的 body（`H1_collision` 等），不可见但参与物理。

## 6. 怎么运行

村子（交互窗口，默认 `demo_v29.xml`）：

```powershell
C:\Users\18967\anaconda3\envs\mujoco\python.exe C:\Users\18967\Desktop\git\run_scene.py
```

无窗口自检：加上 `--headless`。

机器狗 Go2（独立场景，home 姿态起步）：

```powershell
C:\Users\18967\anaconda3\envs\mujoco\python.exe C:\Users\18967\Desktop\git\run_go2.py
```

独立场景是 `assets/props/robots/go2_urdf/go2_scene.xml`（`run_go2.py`）；v29 里已把 Go2 + G1 以固定基座放进 P0（相机 `cam_robots`）。`run_go2.py --headless --sim 2` 可自检。

Go2 爬行步态：`assets/_tools/run_walk.py`（约 6 s 走 2.58 m）。G1：`run_g1.py`（fixed 基座站立）。

窗口里左键旋转、右键平移、滚轮缩放。`outdoor_scene.py` 也能启动，逻辑相同但带程序化场景回退。

### 6.1 验证场景（yard，机器人专用）

**纪律：机器人站立/运动验证只用 yard，不要把 `demo_v29` 当运动场地。** `demo_v29` 是 200 m 真实山地展示场景，不是训练/验证地形。

yard 由 `assets/_tools/yard.py` 生成三档：

```powershell
C:\Users\18967\anaconda3\envs\mujoco\python.exe assets\_tools\yard.py --tier flat
C:\Users\18967\anaconda3\envs\mujoco\python.exe assets\_tools\yard.py --tier stairs
C:\Users\18967\anaconda3\envs\mujoco\python.exe assets\_tools\yard.py --tier full
```

- `yard_flat.xml`：平地，验证站立/基础步态
- `yard_stairs.xml`：台阶，验证越障
- `yard_full.xml`：完整小院（房子 + 地形）；后续可塌结构和机器人联动放这里

自检用 `assets/_tools/check_yard.py`。`go2_robot.xml` 由 `yard.py` 每次自动生成，**不要手动修改**。

## 7. 怎么改

| 想改什么 | 改哪里 | 怎么跑 |
|---|---|---|
| 换某栋房子 | `assets/buildings.json` 的 `model` 字段 | 导入链 → `village.py` → 后续链 |
| 调树的数量/粗细 | `optimize_trees.py --keep/--slender` | 重新生成场景 |
| 调整平过渡带 | `flatten_sites.py --band`（当前 11） | 同步 `seam_ring.py --band` |
| 调道路/封路 | `buildings.json` 的 `road` / `blockades` | `village.py` / `polish.py` |
| 调堆积锥 | `buildings.json` 的 `debris_cones` | `polish.py` |
| 加机器人 | Go2 已导入；验证用 yard，并进村子待定 | `yard.py` 或后续合并脚本 |
| 加二次坍塌 | DSH 产出 `collapse_*` body + 同名 weld | `collapse_trigger.py` 按组/时间解锁 |

## 8. 已知问题与下一步

| 问题 | 影响 | 下一步 |
|---|---|---|
| H2 墙面绿色裂缝 | 扫描件本身的洞，减面后变大，能看穿到草地 | 提高减面上限重导，或 `fix_obj_faces.py` 补洞 |
| 地面 2048² 覆盖 200 m | 草和土近看偏糊 | 可升 4096（约 25 MB），加载会慢一些 |
| H3/H4 还是占位房 | 论文图里一眼假 | 等真实 6–10 m 宽、≤25 万面的 glTF |
| 机器人仅静态展示 | v29 中 Go2/G1 焊死基座，不能行走；Go2 爬行步态可用 `run_walk.py`，G1 官方策略仅 12dof 平地 | 需要真机策略/训练再接 |
| 二次坍塌未接 | 场景是静态的 | 等 DSH 的 `collapse_*` 结构，触发器已就绪 |
| 官方策略限制 | 官方只提供 G1 平地策略，不能预期它在崎岖地形上能跑 | 需要训练则走 unitree_rl_gym 流程 |

## 9. 关键坑（改之前先看）

1. MuJoCo 不读 glTF/Draco，必须转 OBJ。
2. hfield 的 `size` 四个数都必须是正数（base 用 0.01）；PNG 行方向和世界 y 的关系要按项目里的映射来。
3. hfield 的 `texrepeat` 按米计：覆盖 200 m 应填 `0.005`。
4. MuJoCo 3.3.2 的 PBR（metallic/roughness/normal）不生效，只认 albedo + specular/shininess。
5. 薄片 mesh 要加 `inertia="shell"`，否则报 `mesh volume is too small`。
6. OBJ 面索引从 1 开始。
7. `site` 会渲染成球，必须 `group="3"`。
8. 生成链里 `--band` 必须两边一致（flatten 与 seam_ring）。
