# 野外救灾场景素材包（assets/）

给 `outdoor_scene.py` / `outdoor_rescue_demo.py` 这类 MuJoCo 仿真用的**真实素材**：真地形高程 + Poly Haven 实测扫描道具 + 程序化废墟。
全部免费可商用素材（CC0），转换脚本在本目录 `_tools/`，可一条命令重生成或换区域。

**不要提交进 git**：本目录约 47 MB，`assets/.gitignore` 已把整目录排除，只有这个 README 和 `.gitignore` 值得版本化。

## 目录

```
assets/
├─ terrain/                      真实地形高程（MuJoCo hfield）
│  ├─ dem_wenchuan_200m.png      128×128，200 m 见方，落差 66.5 m
│  ├─ dem_wenchuan_400m.png      200×200，400 m 见方，落差 92.1 m
│  └─ *.png.txt                  该图的经纬度/高程范围/原生分辨率
├─ props/                        实测扫描道具（OBJ + MTL + PNG 贴图）
│  ├─ rocks/      boulder_01, rock_07, rock_moss_set_01
│  ├─ debris/     tree_stump_01, bark_debris_01
│  ├─ ground/     grass_medium_01, moss_01
│  └─ vehicles/   covered_car, concrete_road_barrier, old_tyre
├─ tex/                          地面贴图（可平铺）
│  └─ leafy_grass / grass_ground / forest_floor × 1024²
├─ demo_rescue_scene.xml         拼好的完整场景（地形+树+石块+废墟+车，可直接跑）
├─ _tools/                       下载/转换/生成脚本
└─ _preview_scene.png / _preview_close.png   渲染预览
```

## 素材来源与授权

| 素材 | 来源 | 授权 | 说明 |
|---|---|---|---|
| `props/*`, `tex/*` | [Poly Haven](https://polyhaven.com) | **CC0**（可商用、免署名） | 真照片扫描，原始 8K 贴图，这里降到 1K 控体积 |
| `terrain/*` | AWS Open Data `elevation-tiles-prod`（Terrarium）。坐标 31.055°N, 103.483°E——**汶川/映秀**山区 | 公开数据，SRTM 等公共 DEM 派生 | 30 m 级全球覆盖，无需账号 |
| 树、废墟箱体 | 脚本程序化生成 | 无第三方版权 | 见下方「为什么树是程序化的」 |

## 关键坑（踩过的，别再踩）

1. **MuJoCo 不认 glTF**。Poly Haven 只提供 glTF/FBX/Blend，所以 `fetch_ph_model.py` 自己把 glTF 展平成 OBJ（Z-up、米制、uv 保留），贴图转 PNG。直接用官方下载会卡在格式上。
2. **hfield 的 4 个 size 必须全为正数**。`size="x y z base"` 里 `base=0` 会报 `size parameter is not positive`，给 `0.01`。实际高度 = `base + 像素值/255 × z`。
3. **hfield PNG 的第 0 行是 +Y（北）**，不是 -Y。实测结论：列索引 ←→ x，行索引 ←→ −y。搞反了树会浮在半空（这个坑踩过，见一次渲染图里"悬空的树"）。
4. **hfield 只吃 8 位灰度**。MuJoCo 会把 16 位 PNG 压回 8 位（实测 `distinct values` 仍是 256），所以落差 66 m 会有 0.26 m 的等高线台阶。`fetch_dem.py` 里加了抖动（dither）打散，代价是 ±0.13 m 的高频噪声。
5. **Terrarium 最高只到 z15**（约 4.1 m/像素，纬度 31°）。想要 1 m 精度得换 Copernicus GLO-30 / USGS 3DEP 的 GeoTIFF，那就需要 GDAL/rasterio。
6. **树的照片扫描在 MuJoCo 里没法用**：`fir_tree_01` 有 **698 万三角面 / 18.9 m 高**，直接导入卡死；用顶点聚类降到 5 万面后枝叶糊成一坨灰团（贴图还在，但形体没了）。所以场景里的针叶树是程序化生成的（圆柱树干 + 4 层椭球树冠，每棵 5 个几何体），要写实渲染请回 Blender 用原始 glTF。

## 怎么用

**看效果**（需要 `mujoco` conda 环境）：

```powershell
cd C:\Users\18967\Desktop\git\assets
& C:/Users/18967/anaconda3/envs/mujoco/python.exe _tools/render_scene.py demo_rescue_scene.xml out.png 1200 700 2500 0
# 参数：场景 输出图 宽 高 仿真步数 相机编号(0=wide, 1=close)
```

交互式看：

```powershell
& C:/Users/18967/anaconda3/envs/mujoco/python.exe -c "import mujoco, mujoco.viewer; m=mujoco.MjModel.from_xml_path('demo_rescue_scene.xml'); d=mujoco.MjData(m); mujoco.viewer.launch(m,d)"
```

**在自己场景里引用**：

```xml
<asset>
  <hfield name="terrain" file="terrain/dem_wenchuan_200m.png"
          size="100 100 66.5 0.01"/>          <!-- 200 m 见方、落差 66.5 m -->
  <texture name="rock_t" type="2d" file="props/rocks/boulder_01/boulder_01_1k_diffuse.png"/>
  <material name="rock_m" texture="rock_t"/>
  <mesh name="boulder" file="props/rocks/boulder_01/boulder_01_1k.obj"/>
</asset>
<worldbody>
  <geom type="hfield" hfield="terrain"/>
  <body pos="0 0 1"><geom type="mesh" mesh="boulder" material="rock_m"/></body>
</worldbody>
```

坐标和尺度：全部米制、Z-up、模型底面在 body 原点。石块最大 1.8 m，车 4.4 m 长，符合真实尺度。

## 换一块地方 / 换落差

```powershell
$py = "C:/Users/18967/anaconda3/envs/mujoco/python.exe"   # 也可以用 anaconda3\python.exe
# 示例：带滑坡的山区，500 m 见方
& $py _tools/fetch_dem.py --lat 31.10 --lon 103.55 --half 250 --px 200 --out ..\terrain\my_site.png
& $py _tools/build_scene.py --terrain terrain/my_site.png --extent 500 --relief 120 --out my_scene.xml
```

`--half` 是半宽（米），`--px` 是输出分辨率；`--relief` 要填 DEM 输出的 `relief` 值（`.png.txt` 里有），否则地形会被竖向拉伸或压扁。

## 重新生成某个道具

```powershell
& $py _tools\fetch_ph_model.py --id rock_moss_set_01 --res 1k --out ..\props\rocks
# --max-tris 40000 可对重扫描做顶点聚类降面（只适合石头这类实心物体，不适合树）
```

## 已知不足 / 下一步

- 树木是低模替代品，写实渲染需回 Blender 用 Poly Haven 原始 glTF。
- 废墟是 90 个混凝土块 + 3 块楼板（程序化），没有真实建筑结构；要"半塌楼房"得自己拼梁柱或找扫描模型。
- 车辆只有 1 辆报废车（`covered_car`）+ 水泥隔离墩 + 旧轮胎；缺救护车/消防车/工程车——Poly Haven 没有，Sketchfab 的 CC0 车辆需要登录才能下载，属手工活。
- 地面贴图靠 hfield 的归一化 UV，重复感明显；要精细得换贴图分块（4×4 mosaic）或改 mesh 地面。
