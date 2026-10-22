# ASSETS.md — 场景素材索引

当前场景：**`assets/demo_v6.xml`**（535 body / 1307 geom / 10 相机）。素材约 **82 MB**，全部 gitignore，不入库。
详细踩坑与命令见 [assets/README.md](assets/README.md)；分工与下一步见 [AGENTS.md](AGENTS.md)。

## 目录

| 路径 | 内容 | 关键参数 |
|---|---|---|
| `assets/terrain/dem_wenchuan_200m.png` | 汶川真实 DEM → hfield | 128²，200 m²，落差 **66.5 m**，`size="100 100 66.5 0.01"` |
| `assets/terrain/dem_wenchuan_400m.png` | 大范围版 | 200²，400 m²，落差 92.1 m |
| `assets/props/imported/ruin_uk/` | **H1 真实废墟**（Sketchfab，22,631 面，15 分件 + 1 张 2K 图集） | 归一化到 高 7 m |
| `assets/props/imported/maple/` | **枫树**（bark 5,939 + leaf 6,488 面） | 归一化到 高 12 m |
| `assets/props/rocks/` | boulder_01 / rock_07 / rock_moss_set_01 | 6 万面级，**当前面数大头** |
| `assets/props/vehicles/` | covered_car / concrete_road_barrier / old_tyre | 米制 |
| `assets/props/debris/`、`ground/` | 树桩、枯枝、草皮、苔藓 | 草皮太扁，未铺 |
| `assets/tex/` | leafy_grass（地面）、forest_floor（土路）、concrete_floor（楼板）、brick_wall_001（墙） | 1024² |
| `assets/_tools/` | 生成/导入/渲染/清理脚本 | 见 AGENTS.md 的链路 |

## 授权

| 素材 | 授权 | 署名要求 |
|---|---|---|
| Poly Haven（Rocks/Debris/Vehicles/Tex） | CC0 | 无需 |
| 地形 DEM（AWS Terrarium） | 公开数据 | 建议注明来源 |
| 枫树 | **CC-BY 4.0** | *"Maple Tree" by Atrodler, via Sketchfab* |
| 废墟（collapsed_uk_terraced_house） | 见原页面 license.txt | **发表前确认并署名** |

## 常用命令

```powershell
$py  = "C:/Users/18967/anaconda3/python.exe"          # 生成场景（要 PIL）
$mj  = "C:/Users/18967/anaconda3/envs/mujoco/python.exe"  # 仿真/渲染

cd C:\Users\18967\Desktop\git\assets
& $py _tools\village.py --out demo_v6.xml            # 重新生成村落
& $mj _tools\render_scene.py demo_v6.xml out.png 1200 700 2500 4   # 4=cam_H1
& $py _tools\cleanup.py --apply                      # 清临时图与缓存
& $py _tools\convert_multi.py --src <scene.gltf> --name <名> --target-height 8
& $py _tools\fix_obj_faces.py                        # 导入后先体检 OBJ
```

## 五条硬约束

1. MuJoCo **不读 glTF**，也不支持 Draco → 必须转 OBJ。
2. `hfield` 的 `size` 四个数必须全为正（`base=0` 报错）；PNG 第 0 行是 **+Y**。
3. 薄片/叶片 mesh 必须 `inertia="shell"`，否则报 `mesh volume is too small`。
4. MuJoCo 3.3.2 **没有 PBR**：只认 albedo + specular/shininess，别为 normal/roughness 花钱。
5. 场景当前 **8.59 M 三角面**（石头占 6.3 M），加素材前先考虑预算。

## 待办

- H2/H5 换真实废墟：把模型放 `assets/props/imported/<名>/`，改 `buildings.json` 的 `model`（支持目录）
- 岩石瘦身：122 个高模石头 → 40 个，目标总量 ~2.5 M 面
