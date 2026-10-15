import os
import rasterio
import numpy as np
import matplotlib.pyplot as plt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QMessageBox
from matplotlib.colors import LinearSegmentedColormap
from qgis._core import QgsVectorLayer, QgsProject, QgsSymbol, QgsCategorizedSymbolRenderer, QgsRendererCategory, \
    QgsGradientColorRamp, QgsRasterLayer
from qgis.utils import iface
from rasterio.warp import reproject, calculate_default_transform,Resampling
from shapely.geometry import Polygon
import geopandas as gpd
import pandas as pd
tif_path2= '20240310_index_ndvi.tif'
tif_path=r'E:\models\test_ndvi\output_123\output_NDVI.tif'
def check_crs_and_convert(tif_path):
    """检查tif文件的CRS，如果不是EPSG:4326或EPSG:4327，则弹窗提醒用户并转换坐标系"""

    with rasterio.open(tif_path) as src:
        current_crs = src.crs.to_string()

    # 判断坐标系是否为 EPSG:4326 或 EPSG:4327
    if current_crs not in ['EPSG:4326', 'EPSG:4327']:
        # 弹窗提醒用户坐标系不正确
        reply = QMessageBox.warning(
            iface.mainWindow(), '警告',
            f'当前文件的坐标系为 {current_crs}，不是EPSG:4326或EPSG:4327。\n'
            '请点击确定后自动进行坐标系转换。',
            QMessageBox.Ok
        )

        if reply == QMessageBox.Ok:
            # 用户点击确定后进行坐标系转换
            return convert_to_epsg4326(tif_path)
    else:
        return tif_path

def convert_to_epsg4326(tif_path):
    dst_crs = 'EPSG:4326'

    with rasterio.open(tif_path) as src:
        transform, width, height = calculate_default_transform(
            src.crs, dst_crs, src.width, src.height, *src.bounds)

        kwargs = src.meta.copy()
        kwargs.update({
            'crs': dst_crs,
            'transform': transform,
            'width': width,
            'height': height
        })
        new_tif_path = tif_path.replace('.tif', '_reprojected.tif')
        with rasterio.open(new_tif_path, 'w', **kwargs) as dst:
            for i in range(1, src.count + 1):
                reproject(
                    source=rasterio.band(src, i),
                    destination=rasterio.band(dst, i),
                    src_transform=src.transform,
                    src_crs=src.crs,
                    dst_transform=transform,
                    dst_crs=dst_crs,
                    resampling=Resampling.nearest
                )
        # 将转换后的tif文件加载到QGIS项目中
    raster_layer = QgsRasterLayer(new_tif_path, os.path.basename(new_tif_path))
    if raster_layer.isValid():
        QgsProject.instance().addMapLayer(raster_layer)
        QMessageBox.information(
            iface.mainWindow(), '转换完成',
            f'坐标系转换完成，并已成功加载转换后的文件: {new_tif_path}，请选择该文件进行长势分析',
            QMessageBox.Ok
        )
    else:
        QMessageBox.warning(
            iface.mainWindow(), '加载失败',
            f'转换后的文件 {new_tif_path} 加载到QGIS失败。',
            QMessageBox.Ok
        )

def get_ndvi2(tif_path,shp_path,n):
    tif_path = check_crs_and_convert(tif_path)  # 检查和转换坐标系
    # 读取NDVI图像并获取地理边界
    with rasterio.open(tif_path) as src:
        bounds = src.bounds
        width = src.width
        height = src.height
        transform = src.transform
        data = src.read(1)  # 假设NDVI数据在第一个波段
    # print(data)
    width = data.shape[1]
    height = data.shape[0]
    lon_min = bounds.left
    lon_max = bounds.right
    lat_min = bounds.bottom
    lat_max = bounds.top
    results=[]
    # print(transform[0],transform[1],transform[2],transform[3],transform[4],transform[5])

    # 网格大小
    grid_size = n*10
    grid_size2 = grid_size *0.13854 * 10

    # 计算x和y方向上的网格数目
    num_grid_x = int(np.ceil((lon_max - lon_min) / (grid_size * transform[0])))
    num_grid_y = int(np.ceil((lat_max - lat_min) / (grid_size2 * -transform[4])))

    # 创建GeoDataFrame存储网格
    grid_data = []
    for i in range(num_grid_x):
        for j in range(num_grid_y):
            # 计算网格边界
            left = lon_min + i * grid_size * transform[0]  # 纬度
            right = left + grid_size * transform[0]
            bottom = lat_min + j * grid_size2 * -transform[4]  # 经度
            top = bottom + grid_size2 * -transform[4]
            # 计算中心点
            center_x = (left + right) / 2
            center_y = (bottom + top) / 2
            lon_factor = (center_x - lon_min) / (lon_max - lon_min)
            lat_factor = (lat_max - center_y) / (lat_max - lat_min)
            # 将比例因子转换为索引值
            col_index = int(lon_factor * (width - 1))
            row_index = int(lat_factor * (height - 1))
            # 提取对应索引位置的ndvi值
            growth = data[row_index, col_index]
            # growth = np.mean(grid_data)
            if growth < 0.25:
                grade = '0'
            elif growth < 0.5:
                grade = '1'
            elif growth < 0.75:
                grade = '2'
            else:
                grade = '3'
            results.append({
                'geometry': Polygon([(left, bottom), (right, bottom), (right, top), (left, top)]),
                'i': i,  # 新增行号记录
                'j': j,  # 新增列号记录
                'growth': growth,
                'grade': grade
            })

    # 转换为GeoDataFrame
    gdf = gpd.GeoDataFrame(results, columns=['geometry', 'i', 'j','growth','grade'])
    gdf.to_file(shp_path, driver='ESRI Shapefile')


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
            gdf_grid.at[idx, 'grade_new'] = 4

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

    # return clipped_shp_path
