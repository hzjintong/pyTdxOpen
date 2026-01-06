from struct import unpack, calcsize
import os
import re
from datetime import datetime


class TDXFinancialDataParser:
    """通达信财务数据解析器"""

    def __init__(self, cw_dir, field_file="专业财务数据字段说明.txt"):
        """
        初始化解析器

        Args:
            cw_dir: 财务数据文件目录
            field_file: 字段说明文件路径
        """
        self.cw_dir = cw_dir
        self.field_names = {}
        self.field_descriptions = {}
        self.load_field_descriptions(field_file)

    def load_field_descriptions(self, field_file):
        """加载字段说明"""
        try:
            with open(field_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            current_section = None
            for line in lines:
                line = line.strip()
                if not line:
                    continue

                # 识别章节标题
                if line.startswith('-------------') and '----------------' in line:
                    section_match = re.match(r'-*(\D+)-*', line)
                    if section_match:
                        current_section = section_match.group(1).strip()
                        continue

                # 识别字段行：数字--字段名 或 数字.--字段名
                field_match = re.match(r'(\d+)(?:\.)?--(.+)', line)
                if field_match:
                    field_id = int(field_match.group(1))
                    field_name = field_match.group(2).strip()
                    self.field_names[field_id] = field_name
                    if current_section:
                        self.field_descriptions[field_id] = f"{current_section} - {field_name}"
                    else:
                        self.field_descriptions[field_id] = field_name

        except Exception as e:
            print(f"加载字段说明文件时出错: {e}")
            # 如果没有字段说明文件，使用默认的字段索引
            for i in range(1, 585):
                self.field_names[i] = f"字段{i}"
                self.field_descriptions[i] = f"字段{i}"

    def get_quarter_files(self, start_year, end_year):
        """
        获取指定年份范围内的财务数据文件

        Args:
            start_year: 起始年份
            end_year: 结束年份

        Returns:
            排序后的文件路径列表
        """
        files = []
        for filename in os.listdir(self.cw_dir):
            if filename.startswith('gpcw') and filename.endswith('.dat'):
                # 提取日期部分
                date_str = filename[4:12]  # gpcwYYYYMMDD.dat
                try:
                    year = int(date_str[:4])
                    if start_year <= year <= end_year:
                        files.append((os.path.join(self.cw_dir, filename), date_str))
                except ValueError:
                    continue

        # 按日期排序
        files.sort(key=lambda x: x[1])
        return [file[0] for file in files]

    def parse_cw_file(self, file_path, stock_code, field_indices=None):
        """
        解析单个财务数据文件，提取指定股票的指定字段

        Args:
            file_path: 数据文件路径
            stock_code: 股票代码（如 '000001'）
            field_indices: 需要提取的字段索引列表，None表示提取所有字段

        Returns:
            字段数据的字典，key为字段索引，value为字段值
        """
        try:
            with open(file_path, 'rb') as cw_file:
                # 读取文件头
                header_size = calcsize("<3h1H3L")
                data_header = cw_file.read(header_size)
                stock_header = unpack("<3h1H3L", data_header)
                max_count = stock_header[3]

                # 读取股票索引
                stock_item_size = calcsize("<6s1c1L")
                stock_code_found = False
                foa = None

                for stock_idx in range(max_count):
                    cw_file.seek(header_size + stock_idx * stock_item_size)
                    si = cw_file.read(stock_item_size)
                    stock_item = unpack("<6s1c1L", si)
                    code = stock_item[0].decode()

                    if code == stock_code:
                        stock_code_found = True
                        foa = stock_item[2]
                        break

                if not stock_code_found or foa is None:
                    return None

                # 定位并读取财务数据
                cw_file.seek(foa)
                data_size = 584 * 4  # 584个float，每个4字节
                info_data = cw_file.read(data_size)

                if len(info_data) < data_size:
                    # 如果数据不够，尝试读取264个字段（旧格式）
                    data_size = 264 * 4
                    info_data = cw_file.read(data_size)
                    if len(info_data) < data_size:
                        return None
                    cw_info = unpack('<264f', info_data)
                    # 扩展为584个字段，缺失的填充为0
                    extended_info = list(cw_info) + [0.0] * (584 - 264)
                    cw_info = tuple(extended_info)
                else:
                    cw_info = unpack('<584f', info_data)

                # 提取指定字段
                result = {}
                if field_indices is None:
                    # 提取所有字段
                    for i in range(len(cw_info)):
                        result[i + 1] = cw_info[i]
                else:
                    for idx in field_indices:
                        if 1 <= idx <= len(cw_info):
                            result[idx] = cw_info[idx - 1]
                        else:
                            result[idx] = 0.0

                return result

        except Exception as e:
            print(f"解析文件 {file_path} 时出错: {e}")
            return None

    def get_stock_financial_data(self, stock_code, start_year, end_year, field_indices=None):
        """
        获取指定股票在指定时间段内的财务数据

        Args:
            stock_code: 股票代码
            start_year: 起始年份
            end_year: 结束年份
            field_indices: 需要提取的字段索引列表，None表示提取所有字段

        Returns:
            按时间排序的财务数据列表，每个元素是(日期, 字段数据字典)
        """
        # 获取时间段内的文件
        files = self.get_quarter_files(start_year, end_year)
        if not files:
            print(f"在 {self.cw_dir} 目录下未找到 {start_year}-{end_year} 年的财务数据文件")
            return []

        results = []

        for file_path in files:
            # 从文件名提取日期
            filename = os.path.basename(file_path)
            date_str = filename[4:12]  # gpcwYYYYMMDD.dat
            date_display = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"

            print(f"正在处理 {date_display} 的数据...")

            # 解析文件
            data = self.parse_cw_file(file_path, stock_code, field_indices)
            if data:
                results.append((date_str, data))

        # 按日期排序
        results.sort(key=lambda x: x[0])
        return results

    def print_financial_data(self, stock_code, start_year, end_year, field_indices=None, max_rows=None):
        """
        打印指定股票的财务数据

        Args:
            stock_code: 股票代码
            start_year: 起始年份
            end_year: 结束年份
            field_indices: 需要提取的字段索引列表
            max_rows: 最大打印行数，None表示打印所有
        """
        results = self.get_stock_financial_data(stock_code, start_year, end_year, field_indices)

        if not results:
            print(f"未找到股票 {stock_code} 在 {start_year}-{end_year} 年的财务数据")
            return

        print(f"\n{'=' * 80}")
        print(f"股票代码: {stock_code}")
        print(f"时间范围: {start_year}年 至 {end_year}年")
        print(f"{'=' * 80}")

        # 限制打印行数
        if max_rows and len(results) > max_rows:
            results = results[:max_rows]
            print(f"显示前 {max_rows} 个报告期的数据\n")

        for date_str, data in results:
            date_display = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
            print(f"\n报告期: {date_display}")
            print("-" * 60)

            if field_indices is None:
                # 打印前20个字段作为示例
                print_indices = list(range(1, 21))
            else:
                print_indices = field_indices

            for idx in print_indices:
                if idx in data:
                    field_name = self.field_names.get(idx, f"字段{idx}")
                    value = data[idx]

                    # 格式化输出
                    if abs(value) < 0.0001 and abs(value) > 0:
                        value_str = f"{value:.6e}"
                    elif abs(value) > 1e9:
                        value_str = f"{value / 1e9:.2f}亿"
                    elif abs(value) > 1e4:
                        value_str = f"{value / 1e4:.2f}万"
                    else:
                        value_str = f"{value:.4f}"

                    print(f"{idx:3d}. {field_name:30s}: {value_str}")

            print("-" * 60)

        print(f"\n共找到 {len(results)} 个报告期的数据")

    def search_field_by_name(self, keyword):
        """
        根据关键字搜索字段

        Args:
            keyword: 搜索关键字

        Returns:
            匹配的字段列表，每个元素是(字段索引, 字段名)
        """
        matches = []
        for idx, name in self.field_names.items():
            if keyword.lower() in name.lower():
                matches.append((idx, name))
        return matches

    def get_field_info(self, field_indices):
        """
        获取指定字段的详细信息

        Args:
            field_indices: 字段索引列表

        Returns:
            字段信息字典
        """
        info = {}
        for idx in field_indices:
            if idx in self.field_names:
                info[idx] = {
                    'name': self.field_names[idx],
                    'description': self.field_descriptions.get(idx, '')
                }
        return info


def main():
    """主函数"""
    # 配置参数
    CW_DIR = "d:/new_hxzq_hc/vipdoc/cw/"  # 通达信财务数据目录
    FIELD_FILE = "专业财务数据字段说明.txt"  # 字段说明文件

    # 创建解析器
    parser = TDXFinancialDataParser(CW_DIR, FIELD_FILE)

    # 示例1: 查看字段搜索功能
    print("字段搜索示例:")
    matches = parser.search_field_by_name("净利润")
    for idx, name in matches[:5]:  # 只显示前5个结果
        print(f"{idx:3d}. {name}")
    print()

    # 示例2: 获取特定股票的财务数据
    stock_code = input("请输入股票代码 (如 000001): ").strip()
    start_year = int(input("请输入起始年份 (如 2021): "))
    end_year = int(input("请输入结束年份 (如 2022): "))

    # 常用财务指标字段
    common_fields = [
        1,  # 基本每股收益
        4,  # 每股净资产
        6,  # 净资产收益率
        8,  # 货币资金
        21,  # 流动资产合计
        40,  # 资产总计
        63,  # 负债合计
        72,  # 所有者权益合计
        74,  # 营业收入
        75,  # 营业成本
        86,  # 营业利润
        95,  # 净利润
        96,  # 归属于母公司所有者的净利润
        107,  # 经营活动产生的现金流量净额
        131,  # 现金及现金等价物净增加额
        159,  # 流动比率
        172,  # 应收帐款周转率
        183,  # 营业收入增长率
        197,  # 净资产收益率
        210,  # 资产负债率
    ]

    # 让用户选择字段
    print("\n选择要显示的字段:")
    print("1. 常用财务指标")
    print("2. 所有字段")
    print("3. 自定义字段")
    choice = input("请选择 (1/2/3): ").strip()

    if choice == '1':
        field_indices = common_fields
    elif choice == '2':
        field_indices = None  # 表示所有字段
    else:
        field_input = input("请输入字段索引(用逗号分隔, 如 1,4,74,95): ").strip()
        if field_input:
            field_indices = [int(x.strip()) for x in field_input.split(',')]
        else:
            field_indices = common_fields

    # 显示字段信息
    if field_indices:
        field_info = parser.get_field_info(field_indices)
        print("\n将要显示的字段:")
        for idx, info in field_info.items():
            print(f"{idx:3d}. {info['name']}")

    # 获取并打印财务数据
    max_rows = input("\n请输入最大显示报告期数量(直接回车显示所有): ").strip()
    max_rows = int(max_rows) if max_rows else None

    parser.print_financial_data(stock_code, start_year, end_year, field_indices, max_rows)

    # 示例3: 导出到CSV文件
    export = input("\n是否导出数据到CSV文件? (y/n): ").strip().lower()
    if export == 'y':
        results = parser.get_stock_financial_data(stock_code, start_year, end_year, field_indices)
        if results:
            csv_filename = f"{stock_code}_财务数据_{start_year}_{end_year}.csv"
            try:
                with open(csv_filename, 'w', encoding='utf-8') as f:
                    # 写入表头
                    if field_indices:
                        header = "报告期," + ",".join(
                            [f"字段{idx}({parser.field_names.get(idx, '')})" for idx in field_indices])
                    else:
                        header = "报告期," + ",".join(
                            [f"字段{idx}({parser.field_names.get(idx, '')})" for idx in range(1, 21)]) + ",..."

                    f.write(header + "\n")

                    # 写入数据
                    for date_str, data in results:
                        date_display = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
                        if field_indices:
                            row_values = [str(data.get(idx, 0)) for idx in field_indices]
                        else:
                            row_values = [str(data.get(idx, 0)) for idx in range(1, 21)]

                        row = date_display + "," + ",".join(row_values)
                        f.write(row + "\n")

                print(f"数据已导出到: {csv_filename}")
            except Exception as e:
                print(f"导出CSV文件时出错: {e}")


def test_example():
    """测试示例"""
    CW_DIR = "d:/new_hxzq_hc/vipdoc/cw/"
    FIELD_FILE = "专业财务数据字段说明.txt"

    parser = TDXFinancialDataParser(CW_DIR, FIELD_FILE)

    # 测试获取平安银行(000001)2021-2022年的财务数据
    stock_code = "000001"
    start_year = 2021
    end_year = 2022

    # 常用指标
    field_indices = [1, 4, 6, 74, 95, 96, 107, 197, 210]

    print("测试示例: 获取平安银行(000001)2021-2022年财务数据")
    parser.print_financial_data(stock_code, start_year, end_year, field_indices, max_rows=3)


if __name__ == '__main__':
    print("通达信财务数据解析工具")
    print("=" * 50)

    # 运行测试示例或主程序
    run_test = input("运行测试示例? (y/n): ").strip().lower()
    if run_test == 'y':
        test_example()
    else:
        main()