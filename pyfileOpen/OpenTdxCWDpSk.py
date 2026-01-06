from struct import unpack, calcsize
import os
from datetime import datetime


class SimpleTDXFinancialParser:
    """简化的通达信财务数据解析器"""

    def __init__(self, cw_dir):
        self.cw_dir = cw_dir

    def get_available_files(self, start_year, end_year):
        """获取指定年份范围内的可用文件"""
        files = []
        for f in os.listdir(self.cw_dir):
            if f.startswith('gpcw') and f.endswith('.dat'):
                date_str = f[4:12]
                try:
                    year = int(date_str[:4])
                    if start_year <= year <= end_year:
                        files.append((os.path.join(self.cw_dir, f), date_str))
                except:
                    continue
        files.sort(key=lambda x: x[1])
        return [f[0] for f in files]

    def extract_stock_data(self, file_path, stock_code, field_indices):
        """从单个文件中提取股票数据"""
        try:
            with open(file_path, 'rb') as f:
                # 读取文件头
                header = unpack("<3h1H3L", f.read(calcsize("<3h1H3L")))
                max_count = header[3]

                # 查找股票
                for i in range(max_count):
                    f.seek(calcsize("<3h1H3L") + i * calcsize("<6s1c1L"))
                    code, _, offset = unpack("<6s1c1L", f.read(calcsize("<6s1c1L")))
                    if code.decode() == stock_code:
                        f.seek(offset)
                        # 读取584个字段
                        data = unpack('<584f', f.read(584 * 4))
                        result = {}
                        for idx in field_indices:
                            if 1 <= idx <= 584:
                                result[idx] = data[idx - 1]
                        return result
        except Exception as e:
            print(f"读取 {file_path} 时出错: {e}")
        return None

    def get_multi_period_data(self, stock_code, start_year, end_year, field_indices):
        """获取多期数据"""
        results = []
        files = self.get_available_files(start_year, end_year)

        for file_path in files:
            date_str = os.path.basename(file_path)[4:12]
            data = self.extract_stock_data(file_path, stock_code, field_indices)
            if data:
                results.append((date_str, data))

        return sorted(results, key=lambda x: x[0])

    def print_formatted_data(self, stock_code, start_year, end_year, field_indices, field_names=None):
        """格式化打印数据"""
        data = self.get_multi_period_data(stock_code, start_year, end_year, field_indices)

        if not data:
            print(f"未找到数据")
            return

        print(f"\n股票: {stock_code}  {start_year}-{end_year}")
        print("=" * 80)

        # 表头
        header = ["报告期"] + [field_names.get(idx, f"F{idx}") for idx in field_indices]
        print(" | ".join(header))
        print("-" * 80)

        # 数据行
        for date_str, values in data:
            date_fmt = f"{date_str[:4]}-{date_str[4:6]}"
            row = [date_fmt]
            for idx in field_indices:
                val = values.get(idx, 0)
                if abs(val) > 1e9:
                    row.append(f"{val / 1e9:.2f}B")
                elif abs(val) > 1e6:
                    row.append(f"{val / 1e6:.2f}M")
                elif abs(val) > 1e4:
                    row.append(f"{val / 1e4:.2f}W")
                else:
                    row.append(f"{val:.2f}")
            print(" | ".join(row))


# 使用示例
if __name__ == '__main__':
    # 常用字段定义
    FIELD_MAP = {
        1: "基本每股收益",
        4: "每股净资产",
        6: "净资产收益率",
        74: "营业收入",
        95: "净利润",
        96: "归母净利润",
        107: "经营现金流",
        197: "ROE",
        210: "资产负债率"
    }

    # 选择关注的字段
    selected_fields = [1, 4, 6, 74, 95, 96, 107, 197, 210]

    # 创建解析器
    parser = SimpleTDXFinancialParser("d:/new_hxzq_hc/vipdoc/cw/")

    # 获取并显示数据
    stock = input("输入股票代码: ")
    start = int(input("起始年份: "))
    end = int(input("结束年份: "))

    parser.print_formatted_data(stock, start, end, selected_fields, FIELD_MAP)