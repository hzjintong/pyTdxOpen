import struct
import os


class TdxFinancialReader:
    def __init__(self, base_path):
        """
        :param base_path: 通达信财务数据存放目录 (例如 'd:/new_hxzq_hc/vipdoc/cw/')
        """
        self.base_path = base_path
        self.header_format = "<3h1H3L"
        self.item_format = "<6s1c1L"
        self.data_format = "<584f"  # 根据说明，包含584个浮点数字段

    def _get_file_list(self, start_year, end_year):
        """根据年份生成需要读取的文件名列表"""
        quarters = ["0331", "0630", "0930", "1231"]
        target_files = []
        for year in range(start_year, end_year + 1):
            for q in quarters:
                filename = f"gpcw{year}{q}.dat"
                full_path = os.path.join(self.base_path, filename)
                if os.path.exists(full_path):
                    target_files.append((f"{year}-{q}", full_path))
        return target_files

    def read_single_file(self, file_path, stock_code):
        """在单个文件中查找指定股票的财务数据"""
        try:
            with open(file_path, 'rb') as f:
                header_size = struct.calcsize(self.header_format)
                stock_item_size = struct.calcsize(self.item_format)

                # 读取头部信息
                header_data = f.read(header_size)
                header = struct.unpack(self.header_format, header_data)
                max_count = header[3]

                # 遍历索引区寻找匹配的代码
                for i in range(max_count):
                    f.seek(header_size + i * stock_item_size)
                    item_data = f.read(stock_item_size)
                    code_bytes, _, offset = struct.unpack(self.item_format, item_data)

                    if code_bytes.decode().strip() == stock_code:
                        # 定位并读取584个财务字段
                        f.seek(offset)
                        info_data = f.read(struct.calcsize(self.data_format))
                        return struct.unpack(self.data_format, info_data)
                return None
        except Exception as e:
            print(f"解析文件 {os.path.basename(file_path)} 出错: {e}")
            return None

    def query(self, stock_code, start_year, end_year, field_indices):
        """
        查询入口
        :param stock_code: 股票代码 如 '000001'
        :param start_year: 起始年份 如 2021
        :param end_year: 结束年份 如 2022
        :param field_indices: 想要读取的字段编号列表 (对应说明书里的序号，从1开始)
        """
        print(f"正在查询股票: {stock_code} | 时间段: {start_year} - {end_year}")
        print("-" * 80)

        # 获取所有相关季度文件
        files = self._get_file_list(start_year, end_year)

        results = []
        for period, path in files:
            data = self.read_single_file(path, stock_code)
            if data:
                # 提取指定字段 (说明书序号从1开始，Python索引从0开始)
                selected_values = {idx: data[idx - 1] for idx in field_indices}
                results.append((period, selected_values))

        # 打印结果
        if not results:
            print("未找到相关数据。")
            return

        # 打印表头
        header_str = f"{'季度':<10}"
        for idx in field_indices:
            header_str += f" | 字段{idx:<6}"
        print(header_str)
        print("-" * 80)

        for period, vals in results:
            row = f"{period:<10}"
            for idx in field_indices:
                val = vals[idx]
                # 格式化输出：如果是很大的值（金额）用常规显示，如果是比率则保留两位小数
                if abs(val) > 1000000:
                    row += f" | {val:>10.0f}"
                else:
                    row += f" | {val:>10.2f}"
            print(row)


# =================使用示例=================
if __name__ == '__main__':
    # 1. 设置财务文件所在的路径
    CW_DIR = r"d:\new_hxzq_hc\vipdoc\cw"

    reader = TdxFinancialReader(CW_DIR)

    # 2. 定义你想查看的字段序号 (参考字段说明.txt)
    # 例如：1-基本每股收益, 4-每股净资产, 11-应收账款, 95-净利润
    my_fields = [1, 4, 11, 95]

    # 3. 执行查询 (股票代码, 开始年份, 结束年份, 字段列表)
    reader.query("000526", 2018, 2019, my_fields)