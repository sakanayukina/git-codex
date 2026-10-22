# ASSETS.md — 场景素材索引

野外救灾仿真用的真实素材都在 `assets/`（约 47 MB，`.gitignore` 排除，不入库）。
**详细说明、授权、踩坑记录 → [assets/README.md](assets/README.md)**；本文件只做索引，方便在 VS Code 里一眼看到。

## 有什么

| 路径 | 内容 | 关键参数 |
|---|---|---|
| `assets/terrain/dem_wenchuan_200m.png` | 汶川真实 DEM → MuJoCo hfield | 128×128，200 m 见方，落差 **66.5 m**，`size="100 100 66.5 0.01"` |
| `assets/terrain/dem_wenchuan_400m.png` | 同上，更大范围 | 200×200，400 m 见方，落差 **92.1 m**，`size="200 200 92.1 0.01"` |
| `assets/props/rocks/` | boulder_01 / rock_07 / rock_moss_set_01 | OBJ+MTL+PNG，米制，1.8–8 m |
| `assets/props/debris/` | tree_stump_01 / bark_debris_01 | 倒木、枯枝碎屑 |
| `assets/props/vehicles/` | covered_car / concrete_road_barrier / old_tyre | 报废盖布车 4.4 m 长 |
| `assets/props/ground/` | grass_medium_01 / moss_01 | 草丛贴片 |
| `assets/tex/` | leafy_grass / grass_ground / forest_floor | 1024²，可平铺地面贴图 |
| `assets/props/imported/maple/` | Sketchfab 枫树（bark + leaf 两材质拆分） | **CC-BY**，需署名：*"Maple Tree" by Atrodler, CC BY 4.0, via Sketchfab* |
| `assets/demo_rescue_scene.xml` | 拼好的完整场景 | 190 body / 278 geom / 2 相机，直接可跑 |
| `assets/_preview_scene.png`、`_preview_close.png` | 渲染预览 | 1200×700 / 900×600 |
| `assets/_tools/` | 下载/转换/生成脚本 | fetch_dem / fetch_ph_model / fetch_texture / build_scene / render_scene / preview |

**授权**：Poly Haven 与地面贴图全部 **CC0**（可商用免署名）；地形是 AWS Open Data 公开 DEM；树木与废墟箱体为程序化生成，无第三方版权。

## 三条最常用命令

```powershell
cd C:\Users\18967\Desktop\git\assets
$py = "C:/Users/18967/anaconda3/envs/mujoco/python.exe"

# 1) 渲染预览（场景 输出 宽 高 仿真步数 相机0=wide/1=close）
& $py _tools\render_scene.py demo_rescue_scene.xml out.png 1200 700 2500 0

# 2) 换一块地方（半宽 250 m，起伏 120 m）
& $py _tools\fetch_dem.py --lat 31.10 --lon 103.55 --half 250 --px 200 --out ..\terrain\my_site.png
& $py _tools\build_scene.py --terrain terrain/my_site.png --extent 500 --relief 120 --out my_scene.xml

# 3) 下载一个新道具（Poly Haven id，CC0）
& $py _tools\fetch_ph_model.py --id rock_moss_set_01 --res 1k --out ..\props\rocks
```

## 在 MJCF 里怎么引

```xml
<asset>
  <hfield name="terrain" file="assets/terrain/dem_wenchuan_200m.png"
          size="100 100 66.5 0.01"/>
  <texture name="rock_t" type="2d" file="assets/props/rocks/boulder_01/boulder_01_1k_diffuse.png"/>
  <material name="rock_m" texture="rock_t"/>
  <mesh name="boulder" file="assets/props/rocks/boulder_01/boulder_01_1k.obj"/>
</asset>
```

## 五条硬约束（踩过，别重复）

1. MuJoCo **不读 glTF**——Poly Haven 只提供 glTF/FBX，必须走 `fetch_ph_model.py` 转换。
2. `hfield` 的 `size` 四个数字**全须为正**，`base=0` 会报 `size parameter is not positive`，填 `0.01`。
3. hfield PNG **第 0 行 = +Y（北）**，行索引对应 −y；搞反了所有物体浮空。
4. MuJoCo 把 16 位 PNG 压成 8 位，大落差必有等高线台阶，只能靠抖动掩盖。
5. Terrarium DEM 最高 z15（约 4.1 m/px）；照片扫描树（`fir_tree_01` 698 万面）在 MuJoCo 里不可用，场景树是程序化生成的。

## 待接入

`assets/demo_rescue_scene.xml` 尚未接进 `outdoor_scene.py` / `outdoor_rescue_demo.py`（仓库代码改动，Codex 主责，DSH 只提供素材与参数）。
缺口：救护车/消防车/工程车、真实半塌建筑（Poly Haven 无，需 Sketchfab 登录手工下载）。
