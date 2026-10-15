import rasterio
from PyQt5.QtGui import QColor
from qgis._core import QgsVectorLayer, QgsGradientColorRamp, QgsCategorizedSymbolRenderer, QgsSymbol, \
    QgsRendererCategory, QgsProject
from rasterio.warp import calculate_default_transform, reproject, Resampling
import numpy as np
import geopandas as gpd
from shapely.geometry import Polygon, Point
from pyproj import CRS, Transformer
import os
def classify_ndvi(ndvi):
    # 根据NDVI值分等级，示例分法：
    # 0-0.2 -> 1 (极低)
    # 0.2-0.4 -> 2 (低)
    # 0.4-0.6 -> 3 (中)
    # 0.6-1 -> 4 (高)
    if ndvi < 0.1:
        return 0
    elif ndvi<0.2:
        return 1
    elif ndvi < 0.4:
        return 2
    elif ndvi < 0.6:
        return 3
    else:
        return 4

def is_projected(crs):
    # 判断是否是投影坐标系（单位为米等），而不是地理坐标系（单位为度）
    return CRS(crs).is_projected

def ndvi_grid_to_shp(tif_path, shp_path, N_meters):
    # 1. 读取NDVI栅格数据，坐标系EPSG:4326
    with rasterio.open(tif_path) as src:
        ndvi = src.read(1)
        src_crs = src.crs
        src_transform = src.transform
        width = src.width
        height = src.height
        bounds = src.bounds

    if is_projected(src_crs):
        print("输入文件已为投影坐标系，跳过重投影")
        ndvi_proj = ndvi
        transform_proj = src_transform
        proj_crs = src_crs
        width_proj = width
        height_proj = height
    else:
        print("输入文件为地理坐标系，正在转换为投影坐标系")

        lon_center = (bounds.left + bounds.right) / 2
        lat_center = (bounds.top + bounds.bottom) / 2

        utm_zone = int((lon_center + 180) / 6) + 1
        is_northern = lat_center >= 0
        utm_crs = CRS.from_dict({
            'proj': 'utm',
            'zone': utm_zone,
            'datum': 'WGS84',
            'units': 'm',
            'south': not is_northern
        })

        transform_proj, width_proj, height_proj = calculate_default_transform(
            src_crs, utm_crs, width, height, *bounds)
        ndvi_proj = np.empty((height_proj, width_proj), dtype=ndvi.dtype)

        with rasterio.open(tif_path) as src:
            reproject(
                source=rasterio.band(src, 1),
                destination=ndvi_proj,
                src_transform=src.transform,
                src_crs=src.crs,
                dst_transform=transform_proj,
                dst_crs=utm_crs,
                resampling=Resampling.nearest
            )
        proj_crs = utm_crs

    # 网格划分
    xmin, ymin = transform_proj * (0, height_proj)
    xmax, ymax = transform_proj * (width_proj, 0)

    x_coords = np.arange(xmin, xmax, N_meters)
    y_coords = np.arange(ymin, ymax, N_meters)

    polygons = []
    grades = []
    rows = []
    cols = []

    def coords_to_pixel(x, y):
        col, row = ~transform_proj * (x, y)
        return int(row), int(col)

    for i, y in enumerate(y_coords):
        for j, x in enumerate(x_coords):
            poly = Polygon([
                (x, y),
                (x + N_meters, y),
                (x + N_meters, y + N_meters),
                (x, y + N_meters)
            ])
            cx, cy = poly.centroid.x, poly.centroid.y
            row, col = coords_to_pixel(cx, cy)

            if 0 <= row < ndvi_proj.shape[0] and 0 <= col < ndvi_proj.shape[1]:
                # 获取该网格内所有像素点的NDVI值并取绝对值
                grid_values = []
                for r in range(row, row + N_meters):
                    for c in range(col, col + N_meters):
                        ndvi_val = ndvi_proj[r, c]
                        if np.isnan(ndvi_val) or ndvi_val < -1 or ndvi_val > 1:
                            continue
                        # NDVI 小于 0 的像素点设为 0
                        ndvi_val = max(ndvi_val, 0)
                        grid_values.append(ndvi_val)

                # 计算网格内所有像素点的平均值
                if grid_values:
                    avg_ndvi = np.mean(grid_values)#平均值
                    # median_ndvi = np.median(grid_values)

                else:
                    avg_ndvi = 0
                    # median_ndvi = 0

                # 根据平均的NDVI值进行分类
                grade = classify_ndvi(avg_ndvi)
            else:
                grade = 0
            polygons.append(poly)
            grades.append(grade)
            rows.append(i)
            cols.append(j)

    gdf = gpd.GeoDataFrame({
        'grade': grades,
        'i': rows,
        'j': cols,
        'geometry': polygons
    }, crs=proj_crs)

    gdf.to_file(shp_path)

    # 9. 重新投影回EPSG:4326并保存一个新的shp文件（可选）
    gdf_4326 = gdf.to_crs(epsg=4326)
    # gdf_4326.to_file(shp_path.replace('.shp', '_WGS84.shp'))
    shp_name = os.path.splitext(os.path.basename(shp_path))[0]
    gdf_4326.to_file(shp_path, driver='ESRI Shapefile')
    layer = QgsVectorLayer(shp_path, shp_name, 'ogr')
    # 检查图层是否有效
    if not layer.isValid():
        print("图层无效")
    else:
        # 将图层添加到当前QGIS项目中
        QgsProject.instance().addMapLayer(layer)

        # 设置渐变色
        gradient_ramp = QgsGradientColorRamp(QColor(255, 255, 255), QColor(0, 102, 0))  # 从淡黄到深绿
        renderer = QgsCategorizedSymbolRenderer('grade', [])

        for grade in range(5):  # 0, 1, 2, 3
            color = gradient_ramp.color(grade / 5.0)  # 根据比例获取渐变色
            symbol = QgsSymbol.defaultSymbol(layer.geometryType())
            symbol.setColor(color)
            category = QgsRendererCategory(str(grade), symbol, str(grade))  # grade 转换为字符串
            renderer.addCategory(category)

        layer.setRenderer(renderer)
        layer.triggerRepaint()


if __name__ == "__main__":
    tif_input =r'E:\models\build_shp\test_ndvi\output_NDVI.tif'
    N = 5
    shp_output = "output_grid.shp"
    ndvi_grid_to_shp(tif_input, N, shp_output)
