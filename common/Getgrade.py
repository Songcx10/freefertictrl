import os
import rasterio
import numpy as np
from PyQt5.QtGui import QColor
from qgis._core import QgsVectorLayer, QgsProject, QgsSymbol, QgsCategorizedSymbolRenderer, QgsRendererCategory, \
    QgsGradientColorRamp, QgsRasterLayer
from rasterio.warp import reproject, calculate_default_transform,Resampling
from shapely.geometry import Polygon
import geopandas as gpd
import pandas as pd
from pyproj import CRS, Transformer
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

def ndvi_grid_to_shp2(tif_path, shp_path, N_meters):
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
                    avg_ndvi = np.mean(grid_values)  # 平均值
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


def clip_shp_with_polygon_and_show(grid_shp_path, shp_path):
    """
    根据传入的多边形Shapefile对长势分析结果的Shapefile进行裁剪，并显示在QGIS界面中。

    :param grid_shp_path: 完整的长势分析结果图（包含网格和grade属性）。
    :param shp_path: 用于裁剪的多边形Shapefile路径（封闭多边形）。
    :return: 返回裁剪后的Shapefile路径。
    """
    gdf_polygon = gpd.read_file(shp_path)
    if gdf_polygon.empty:
        raise ValueError("裁剪用的Shapefile为空。")

    polygons = [geom for geom in gdf_polygon.geometry]
    if not polygons:
        raise ValueError("裁剪用的Shapefile中没有几何图形。")

     # 裁剪长势分析结果Shapefile
    gdf_grid = gpd.read_file(grid_shp_path)
    if gdf_grid.empty:
        raise ValueError("长势分析结果的Shapefile为空。")

        # 创建一个新列 'grade_new'，初始值为原 'grade' 值
    gdf_grid['grade_new'] = gdf_grid['grade']

    # 遍历每个网格，判断是否与多边形相交
    for idx, row in gdf_grid.iterrows():
        if row.geometry.intersects(gdf_polygon.unary_union):
            # 如果相交，保留原 grade 值（无需修改）
            pass
        else:
                # 如果不相交，设置 grade=4
            gdf_grid.at[idx, 'grade_new'] = 0

        # 删除原 'grade' 列，并重命名 'grade_new' 为 'grade'
    gdf_grid.drop(columns=['grade'], inplace=True)
    gdf_grid.rename(columns={'grade_new': 'grade'}, inplace=True)

    # 保存裁剪后的Shapefile
    # clipped_shp_path = grid_shp_path.replace('.shp', '_clipped.shp')
    gdf_grid.to_file(grid_shp_path, driver='ESRI Shapefile')

    shp_name = os.path.splitext(os.path.basename(grid_shp_path))[0]
        # 加载裁剪后的Shapefile到QGIS中
    clipped_layer = QgsVectorLayer(grid_shp_path, shp_name, "ogr")
    if not clipped_layer.isValid():
        print("裁剪后的图层无效")
    else:
        QgsProject.instance().addMapLayer(clipped_layer)

        # 设置渐变色
        gradient_ramp = QgsGradientColorRamp(QColor(255, 255, 255), QColor(0, 102, 0))  # 定义渐变色
        renderer = QgsCategorizedSymbolRenderer('grade', [])  # 使用 'grade' 字段

        for grade in range(5):  # 0, 1, 2, 3
            color = gradient_ramp.color(grade / 5.0)  # 根据比例获取渐变色
            symbol = QgsSymbol.defaultSymbol(clipped_layer.geometryType())
            symbol.setColor(color)
            category = QgsRendererCategory(str(grade), symbol, str(grade))
            renderer.addCategory(category)

        clipped_layer.setRenderer(renderer)
        clipped_layer.triggerRepaint()


