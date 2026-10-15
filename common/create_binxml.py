import geopandas as gpd
import xml.etree.ElementTree as ET
import os
import struct
import numpy as np

def create_xml(shp_path,xml_path,bin_path,n,data,progress_callback=None):
    try:
        #检查文件是否存在
        if not os.path.exists(xml_path):
            # 如果文件不存在，创建一个新的空文件
            with open(xml_path, 'w') as file:
                # file.write('<?xml version="1.0" encoding="UTF-8"?>\n')
                file.write('hello')
                print("xml_File created successfully!")
        else :
            print("xml_File exist!")


        # 读取 shapefile
        gdf = gpd.read_file(shp_path)

        get_bin(shp_path, bin_path)
        total_steps = len(gdf) + 4  # 迭代步骤数加上几个固定步骤
        current_step = 0
         # 创建根元素
        root = ET.Element("ISO11783_TaskData", attrib={
            "ManagementSoftwareManufacturer": "MyEasyFarm",
            "VersionMajor": "3",
            "VersionMinor": "3",
            "ManagementSoftwareVersion": "2.1",
            "DataTransferOrigin": "1"
        })

        TSK = ET.SubElement(root, "TSK", attrib={
            "B": "TeeJet test_Test_Nanjing",
            "G": "1",
            "A": "TSK1",
            "E": "PFD1",
            "H": "4"
         })
        # 更新进度
        current_step += 1
        if progress_callback:
            progress_callback(int(current_step / total_steps * 100))
        # DLT子元素
        ET.SubElement(TSK, "DLT", attrib={"A": "dfff", "B": "31"})
        ET.SubElement(TSK, "DLT", attrib={"A": "00a1", "B": "8", "G": "1"})

        # 当前grade有4个等级，因此设置四个TZN（处理带）
        PLN = [None] * (n+1)
        TZN = ET.SubElement(TSK, "TZN",attrib={"A": '1', "B": "Zero Treatment Zone"})
        PDV = ET.SubElement(TZN, "PDV", attrib={"A": "0001", "B": '0', "E": "VPN1", "C": "PDT252345"})
        for i in range(4):
            TZN = ET.SubElement(TSK, "TZN",
                                attrib={"A": str(i + 2), "B": str(int(data[i])/10000)})
            PDV = ET.SubElement(TZN, "PDV", attrib={"A": "0001", "B": str(data[i]), "E": "VPN1","C": "PDT252345"})
            # 更新进度
            current_step += 1
            if progress_callback:
                progress_callback(int(current_step / total_steps * 100))


        grd_data = extract_grd_to_list(shp_path)
        attrib_keys = ["A", "B", "C", "D", "E", "F", "G", "I"]
        if len(grd_data) != len(attrib_keys):
            raise ValueError("列表长度与GRD属性数量不匹配")

        # 创建GRD元素并设置属性
        grd_attrib = dict(zip(attrib_keys, grd_data))
        grd_element = ET.SubElement(TSK, "GRD", attrib=grd_attrib)
        # 更新进度
        current_step += 1
        if progress_callback:
            progress_callback(int(current_step / total_steps * 100))
        pfd = ET.SubElement(root, "PFD", attrib={"C": "TeeJet test","D": "201600", "A": "PFD1", "F": "FRM9008","E": "CTR6969"})
        pln = ET.SubElement(pfd, "PLN", attrib={"A": "1"})
        lsg = ET.SubElement(pln, "LSG", attrib={"A": "1"})
        # 更新进度
        current_step += 1
        if progress_callback:
            progress_callback(int(current_step / total_steps * 100))
        # 边界点坐标
        gdf1 = gpd.read_file(shp_path)

        # 获取地理范围（bounding box），返回一个包含 [min_x, min_y, max_x, max_y] 的列表
        bounds = gdf1.total_bounds

        # 提取四个点的坐标，按照左上、右上、右下、左下、左上的顺序
        left_top = (round(bounds[0], 6), round(bounds[3], 6))  # (min_x, max_y)
        right_top = (round(bounds[2], 6), round(bounds[3], 6))  # (max_x, max_y)
        right_bottom = (round(bounds[2], 6), round(bounds[1], 6))  # (max_x, min_y)
        left_bottom = (round(bounds[0], 6), round(bounds[1], 6))  # (min_x, min_y)

        # 将四个点的坐标存储在列表中
        corner_coordinates = [left_top, right_top, right_bottom, left_bottom, left_top]
        rounded_coords = [(round(x, 6), round(y, 6)) for x, y in corner_coordinates]
        for lon, lat in rounded_coords:
            ET.SubElement(lsg,"PNT",attrib={"A": "2", "D": str(lon), "C": str(lat)})

        # 其他实体
        ET.SubElement(root, "CTR", attrib={"C": "Ping", "B": "Zhang","I": "China","J": "008613567250621","M": "hellomorkin@163.com","A": "CTR6969"})
        ET.SubElement(root, "FRM", attrib={ "I": "CTR6969","B": "Test_Nanjing", "C": "农机所", "F": "南京","H": "China","A": "FRM9008"})
        # 更新进度
        current_step += 1
        if progress_callback:
            progress_callback(int(current_step / total_steps * 100))
        cld = ET.SubElement(root, "CLD", attrib={"B": "0", "A": "CLD1"})
        for i in range(n):
            j = (i +1)* 3
            ET.SubElement(cld,"CRG",attrib={"A":str(data[i]),"B":str(data[i]),"C":str(j)})
            # 更新进度
            current_step += 1
            if progress_callback:
                progress_callback(int(current_step / total_steps * 100))

        ET.SubElement(root, "VPN", attrib={"B": "0", "C": "0.000100000","D": "2","E": "L/ha","A": "VPN1", "F": "CLD1"})
        ET.SubElement(root, "PDT", attrib={"B": "Nitrogen solution (39%)","E": "0001","A": "PDT252345"})
        # 创建XML树并保存为文件
        tree = ET.ElementTree(root)
        tree.write(xml_path, encoding="utf-8", xml_declaration=True)
        # 完成进度
        if progress_callback:
            progress_callback(100)
        return True
    except Exception as e:
        print(f"Error creating XML: {e}")
        # 如果发生错误，返回False
        return False

def get_bin(shp_path,bin_path):
    gdf = gpd.read_file(shp_path)
    grades = gdf['grade'].tolist()
    for index, row in gdf.iterrows():
        grade = row['grade']
        print(grade)
    # 定义grade到数值的映射
    grade_mapping = {
        0: 1,
        1: 2,
        2: 3,
        3: 4,
        4: 5
    }
    # 转换grade为整数
    grade_values = []
    for grade in grades:
        if grade in grade_mapping:
            grade_values.append(grade_mapping[grade])
        else:
            grade_values.append(-1)  # 未知或无效grade

    with open(bin_path, 'wb') as f:
        for val in grade_values:
            print(val)
            f.write(struct.pack('B', val))  # 每个grade值存储为4字节的整数B H I


def extract_grd_to_list(shp_path):
    """从SHP文件中提取GRD参数，返回有序列表"""
    gdf = gpd.read_file(shp_path)
    row = gdf['j'].max()-gdf['j'].min()+1
    col = gdf['i'].max()-gdf['i'].min()+1
    # 校验几何类型
    if not all(gdf.geometry.type == 'Polygon'):
        raise ValueError("SHP文件必须包含多边形几何")

    # 提取所有边界并计算参数
    all_bounds = np.array([geom.bounds for geom in gdf.geometry])  # (minx, miny, maxx, maxy)
    min_lon = np.min(all_bounds[:, 0])  # B: 最小经度
    max_lat = np.min(all_bounds[:, 3])  # A: 最小纬度
    first_cell = all_bounds[0]
    lat_step = abs(first_cell[1] - first_cell[3])  # C: 纬度步长（取绝对值）
    lon_step = abs(first_cell[2] - first_cell[0])  # D: 经度步长

    # 按属性顺序生成列表 [A, B, C, D, E, F, G, I]
    grd_list = [
        f"{max_lat:.9f}",  # A
        f"{min_lon:.9f}",  # B
        f"{lat_step:.15f}",  # C
        f"{lon_step:.15f}",  # D
        str(row),  # E行
        str(col),  # F列
        "GRD00001",  # G（示例ID，可自定义生成逻辑）
        "1"  # I
    ]
    return grd_list

if  __name__ == '__main__':
    data = [10000, 20000, 30000, 40000]  # 示例数据
    # shp_file = 'shp_file/grid.shp'
    shp_path = r'E:\QGIStest\kun_0317_30m\0307_30m_index_ndvi_grade.shp'
    xml_path = r'E:\QGIStest\kun_0317_30m\TASKDATA.xml'
    bin_path = r'E:\QGIStest\kun_0317_30m\GRD00001.BIN'
    result = create_xml(shp_path, xml_path,bin_path, 4, data)

    if result:
        print("XML 文件生成成功")
    else:
        print("XML 文件生成失败")

