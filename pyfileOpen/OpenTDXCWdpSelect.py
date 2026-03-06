from struct import unpack, calcsize
import os
import re
from datetime import datetime
import pandas as pd
from tqdm import tqdm
import warnings

warnings.filterwarnings('ignore')


class TDXStockRanker:
    """通达信股票财务指标排序器"""

    def __init__(self, cw_dir, field_file="专业财务数据字段说明.txt"):
        """
        初始化排序器

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

    def get_latest_year_files(self, years=3):
        """
        获取最近几年的财务数据文件

        Args:
            years: 最近多少年

        Returns:
            排序后的文件路径列表
        """
        # 获取所有文件
        all_files = []
        for filename in os.listdir(self.cw_dir):
            if filename.startswith('gpcw') and filename.endswith('.dat'):
                date_str = filename[4:12]  # gpcwYYYYMMDD.dat
                all_files.append((filename, date_str))

        # 按日期排序
        all_files.sort(key=lambda x: x[1], reverse=True)

        # 获取最近几年的文件（每年取最新的季度报告）
        latest_files = []
        processed_years = set()

        for filename, date_str in all_files:
            year = date_str[:4]
            if year not in processed_years:
                processed_years.add(year)
                latest_files.append((filename, date_str))

            if len(processed_years) >= years:
                break

        # 按日期正序排列
        latest_files.sort(key=lambda x: x[1])

        return [os.path.join(self.cw_dir, f[0]) for f in latest_files]

    def parse_all_stocks_in_file(self, file_path, field_indices=None):
        """
        解析单个财务数据文件中的所有股票

        Args:
            file_path: 数据文件路径
            field_indices: 需要提取的字段索引列表，None表示提取所有字段

        Returns:
            字典，key为股票代码，value为字段数据字典
        """
        all_stocks_data = {}

        try:
            with open(file_path, 'rb') as cw_file:
                # 读取文件头
                header_size = calcsize("<3h1H3L")
                data_header = cw_file.read(header_size)
                stock_header = unpack("<3h1H3L", data_header)
                max_count = stock_header[3]

                # 读取股票索引
                stock_item_size = calcsize("<6s1c1L")

                for stock_idx in tqdm(range(max_count), desc="解析股票数据", leave=False):
                    cw_file.seek(header_size + stock_idx * stock_item_size)
                    si = cw_file.read(stock_item_size)
                    stock_item = unpack("<6s1c1L", si)
                    code = stock_item[0].decode()
                    foa = stock_item[2]

                    # 定位并读取财务数据
                    cw_file.seek(foa)
                    data_size = 584 * 4  # 584个float，每个4字节
                    info_data = cw_file.read(data_size)

                    if len(info_data) < data_size:
                        # 如果数据不够，尝试读取264个字段（旧格式）
                        data_size = 264 * 4
                        info_data = cw_file.read(data_size)
                        if len(info_data) < data_size:
                            continue
                        cw_info = unpack('<264f', info_data)
                        # 扩展为584个字段，缺失的填充为0
                        extended_info = list(cw_info) + [0.0] * (584 - 264)
                        cw_info = tuple(extended_info)
                    else:
                        cw_info = unpack('<584f', info_data)

                    # 提取指定字段
                    if field_indices is None:
                        # 提取所有字段
                        data_dict = {i + 1: cw_info[i] for i in range(len(cw_info))}
                    else:
                        data_dict = {}
                        for idx in field_indices:
                            if 1 <= idx <= len(cw_info):
                                data_dict[idx] = cw_info[idx - 1]
                            else:
                                data_dict[idx] = 0.0

                    all_stocks_data[code] = data_dict

                return all_stocks_data

        except Exception as e:
            print(f"解析文件 {file_path} 时出错: {e}")
            return {}

    def calculate_stock_score(self, stock_data_dict):
        """
        计算股票综合得分

        Args:
            stock_data_dict: 包含多个报告期数据的字典

        Returns:
            综合得分
        """
        if not stock_data_dict:
            return 0

        # 计算各项指标的平均值
        indicators = {
            'roe': 197,  # 净资产收益率
            'roa': 200,  # 总资产净利率
            'profit_margin': 199,  # 销售净利率
            'gross_margin': 202,  # 销售毛利率
            'revenue_growth': 183,  # 营业收入增长率
            'profit_growth': 184,  # 净利润增长率
            'operating_cash_flow': 107,  # 经营活动产生的现金流量净额
            'current_ratio': 159,  # 流动比率
            'quick_ratio': 160,  # 速动比率
            'asset_turnover': 175,  # 总资产周转率
            'debt_ratio': 210,  # 资产负债率（需要反向处理）
        }

        # 计算每个指标的加权平均值（最新季度权重更高）
        scores = {}
        total_weight = 0

        for indicator_name, field_id in indicators.items():
            values = []
            weights = []

            # 获取每个报告期的数据
            for i, (date_str, data_dict) in enumerate(stock_data_dict.items()):
                if field_id in data_dict:
                    value = data_dict[field_id]

                    # 特殊处理：资产负债率是越低越好，需要取倒数
                    if indicator_name == 'debt_ratio' and value > 0:
                        value = 1.0 / value if value > 0.01 else 0

                    # 排除异常值
                    if abs(value) < 1e10:  # 防止极端值
                        values.append(value)
                        # 越近的季度权重越高
                        weights.append(i + 1)

            if values:
                # 计算加权平均值
                weighted_sum = sum(v * w for v, w in zip(values, weights))
                weight_sum = sum(weights)
                scores[indicator_name] = weighted_sum / weight_sum if weight_sum > 0 else 0
            else:
                scores[indicator_name] = 0

        # 计算综合得分
        # 权重分配
        weights = {
            'roe': 0.25,  # 盈利能力，净资产收益率
            'roa': 0.15,  # 盈利能力，总资产净利率
            'profit_margin': 0.10,  # 盈利能力，销售净利率
            'gross_margin': 0.10,  # 盈利能力，销售毛利率
            'revenue_growth': 0.10,  # 成长能力，营业收入增长率
            'profit_growth': 0.10,  # 成长能力，净利润增长率
            'operating_cash_flow': 0.05,  # 现金流，经营活动产生的现金流量净额
            'current_ratio': 0.05,  # 偿债能力，流动比率
            'quick_ratio': 0.05,  #偿债能力，速动比率
            'asset_turnover': 0.03,  # 运营效率，总资产周转率
            'debt_ratio': 0.02,  # 财务杠杆，资产负债率
        }

        # 标准化处理
        normalized_scores = {}
        for indicator, value in scores.items():
            if indicator == 'debt_ratio':
                # 负债率已处理，直接使用
                normalized_scores[indicator] = value
            else:
                # 简单的标准化：除以最大值（如果最大值不为0）
                max_val = max(abs(v) for v in scores.values() if abs(v) > 0)
                if max_val > 0:
                    normalized_scores[indicator] = value / max_val
                else:
                    normalized_scores[indicator] = 0

        # 计算加权总分
        total_score = sum(normalized_scores.get(indicator, 0) * weight
                          for indicator, weight in weights.items())

        return total_score

    def rank_all_stocks(self, years=3, top_n=100):
        """
        对所有股票进行排名

        Args:
            years: 使用最近多少年的数据
            top_n: 显示前多少名

        Returns:
            DataFrame，包含排名结果
        """
        print(f"获取最近{years}年的财务数据文件...")
        files = self.get_latest_year_files(years)

        if not files:
            print("未找到财务数据文件")
            return pd.DataFrame()

        print(f"找到 {len(files)} 个文件:")
        for f in files:
            print(f"  - {os.path.basename(f)}")

        # 收集所有股票的数据（多期）
        all_stocks_multi_data = {}

        # 定义需要提取的字段
        field_indices = [
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
            184,  # 净利润增长率
            197,  # 净资产收益率(获利能力)
            199,  # 销售净利率
            200,  # 总资产净利率
            202,  # 销售毛利率
            210,  # 资产负债率
            219,  # 每股经营性现金流
            220,  # 营业收入现金含量
        ]

        # 解析每个文件
        for file_path in files:
            filename = os.path.basename(file_path)
            date_str = filename[4:12]
            print(f"\n解析文件: {filename} ({date_str[:4]}-{date_str[4:6]}-{date_str[6:8]})")

            stocks_data = self.parse_all_stocks_in_file(file_path, field_indices)

            # 将数据添加到多期数据中
            for stock_code, data_dict in stocks_data.items():
                if stock_code not in all_stocks_multi_data:
                    all_stocks_multi_data[stock_code] = {}
                all_stocks_multi_data[stock_code][date_str] = data_dict

        print(f"\n共收集到 {len(all_stocks_multi_data)} 只股票的数据")

        # 计算每只股票的综合得分
        print("\n计算股票综合得分...")
        stock_scores = {}

        for stock_code, multi_data in tqdm(all_stocks_multi_data.items(), desc="计算得分"):
            score = self.calculate_stock_score(multi_data)
            stock_scores[stock_code] = score

        # 按得分排序
        print("\n对股票进行排序...")
        sorted_stocks = sorted(stock_scores.items(), key=lambda x: x[1], reverse=True)

        # 创建结果DataFrame
        results = []

        for rank, (stock_code, score) in enumerate(sorted_stocks[:top_n], 1):
            # 获取最新季度的关键指标
            latest_data = None
            latest_date = None

            if stock_code in all_stocks_multi_data:
                # 找到最新的报告期
                dates = list(all_stocks_multi_data[stock_code].keys())
                if dates:
                    latest_date = max(dates)
                    latest_data = all_stocks_multi_data[stock_code][latest_date]

            if latest_data:
                results.append({
                    '排名': rank,
                    '股票代码': stock_code,
                    '综合得分': round(score, 4),
                    '最新报告期': f"{latest_date[:4]}-{latest_date[4:6]}-{latest_date[6:8]}",
                    'ROE(%)': round(latest_data.get(197, 0), 2),
                    '净利润(亿)': round(latest_data.get(95, 0) / 1e8, 2) if latest_data.get(95, 0) != 0 else 0,
                    '营业收入(亿)': round(latest_data.get(74, 0) / 1e8, 2) if latest_data.get(74, 0) != 0 else 0,
                    '每股收益(元)': round(latest_data.get(1, 0), 2),
                    '资产负债率(%)': round(latest_data.get(210, 0), 2),
                    '销售毛利率(%)': round(latest_data.get(202, 0), 2),
                    '营收增长率(%)': round(latest_data.get(183, 0), 2),
                })

        df = pd.DataFrame(results)
        return df

    def rank_by_specific_indicator(self, field_id, years=3, top_n=100, ascending=False):
        """
        按特定指标进行排名

        Args:
            field_id: 字段ID
            years: 使用最近多少年的数据
            top_n: 显示前多少名
            ascending: 是否升序排列（False表示降序，即数值越大越好）

        Returns:
            DataFrame，包含排名结果
        """
        field_name = self.field_names.get(field_id, f"字段{field_id}")
        print(f"按 {field_name} 进行排名...")

        files = self.get_latest_year_files(years)

        if not files:
            print("未找到财务数据文件")
            return pd.DataFrame()

        # 获取最新文件的数据
        latest_file = files[-1]
        filename = os.path.basename(latest_file)
        date_str = filename[4:12]

        print(f"使用最新报告期: {date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}")

        stocks_data = self.parse_all_stocks_in_file(latest_file, [field_id])

        # 按指标值排序
        sorted_stocks = sorted(stocks_data.items(),
                               key=lambda x: x[1].get(field_id, 0),
                               reverse=not ascending)

        # 创建结果DataFrame
        results = []

        for rank, (stock_code, data_dict) in enumerate(sorted_stocks[:top_n], 1):
            value = data_dict.get(field_id, 0)

            # 格式化显示
            if abs(value) > 1e8:
                display_value = f"{value / 1e8:.2f}亿"
            elif abs(value) > 1e4:
                display_value = f"{value / 1e4:.2f}万"
            else:
                display_value = f"{value:.4f}"

            results.append({
                '排名': rank,
                '股票代码': stock_code,
                field_name: display_value,
                '原始值': value,
            })

        df = pd.DataFrame(results)
        return df

    def export_ranking_to_excel(self, df, filename="股票排名结果.xlsx"):
        """导出排名结果到Excel文件"""
        if df.empty:
            print("没有数据可导出")
            return

        try:
            # 使用ExcelWriter创建带多个工作表的Excel文件
            with pd.ExcelWriter(filename, engine='openpyxl') as writer:
                # 主排名表
                df.to_excel(writer, sheet_name='综合排名', index=False)

                # 调整列宽
                worksheet = writer.sheets['综合排名']
                for column in worksheet.columns:
                    max_length = 0
                    column_letter = column[0].column_letter
                    for cell in column:
                        try:
                            if len(str(cell.value)) > max_length:
                                max_length = len(str(cell.value))
                        except:
                            pass
                    adjusted_width = min(max_length + 2, 30)
                    worksheet.column_dimensions[column_letter].width = adjusted_width

                # 添加各指标说明表
                field_info = []
                for idx in [1, 197, 74, 95, 210, 202, 183]:
                    if idx in self.field_names:
                        field_info.append({
                            '字段ID': idx,
                            '字段名称': self.field_names[idx],
                            '说明': self.field_descriptions.get(idx, '')
                        })

                if field_info:
                    field_df = pd.DataFrame(field_info)
                    field_df.to_excel(writer, sheet_name='指标说明', index=False)

                # 添加数据说明
                info_df = pd.DataFrame({
                    '说明': [
                        '综合得分：根据多个财务指标加权计算得出，分数越高表示财务健康状况越好',
                        'ROE：净资产收益率，衡量公司盈利能力的重要指标',
                        '数据来源：通达信财务数据',
                        f'生成时间：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}'
                    ]
                })
                info_df.to_excel(writer, sheet_name='数据说明', index=False)

            print(f"排名结果已导出到: {filename}")

        except Exception as e:
            print(f"导出Excel文件时出错: {e}")
            # 尝试导出为CSV
            csv_file = filename.replace('.xlsx', '.csv')
            df.to_csv(csv_file, index=False, encoding='utf-8-sig')
            print(f"已导出为CSV文件: {csv_file}")


def main():
    """主函数"""
    print("=" * 80)
    print("通达信上市公司财务指标排序系统")
    print("=" * 80)

    # 配置参数
    CW_DIR = "d:/new_hxzq_hc/vipdoc/cw/"  # 通达信财务数据目录
    FIELD_FILE = "专业财务数据字段说明.txt"  # 字段说明文件

    # 创建排序器
    ranker = TDXStockRanker(CW_DIR, FIELD_FILE)

    # 选择排名方式
    print("\n请选择排名方式:")
    print("1. 综合财务指标排名（多指标加权）")
    print("2. 按特定指标排名（如ROE、净利润等）")
    print("3. 按盈利能力排名")
    print("4. 按成长能力排名")

    choice = input("\n请选择 (1-4): ").strip()

    if choice == '1':
        # 综合排名
        years = int(input("使用最近几年的数据? (默认3): ") or "3")
        top_n = int(input("显示前多少名? (默认100): ") or "100")

        print("\n正在计算综合排名，请稍候...")
        df = ranker.rank_all_stocks(years=years, top_n=top_n)

        if not df.empty:
            print("\n" + "=" * 100)
            print("综合财务指标排名结果（前50名）:")
            print("=" * 100)
            print(df.head(50).to_string(index=False))

            # 导出结果
            export = input("\n是否导出完整排名结果? (y/n): ").strip().lower()
            if export == 'y':
                filename = input("请输入导出文件名 (默认: 股票综合排名.xlsx): ") or "股票综合排名.xlsx"
                ranker.export_ranking_to_excel(df, filename)

    elif choice == '2':
        # 特定指标排名
        print("\n常用财务指标:")
        print("197 - 净资产收益率(ROE)")
        print("1   - 基本每股收益")
        print("95  - 净利润")
        print("74  - 营业收入")
        print("183 - 营业收入增长率")
        print("202 - 销售毛利率")
        print("210 - 资产负债率")

        field_id = int(input("\n请输入字段ID: "))
        ascending_input = input("是否升序排列? (y/n, 默认n降序): ").strip().lower()
        ascending = ascending_input == 'y'
        top_n = int(input("显示前多少名? (默认50): ") or "50")

        df = ranker.rank_by_specific_indicator(field_id, top_n=top_n, ascending=ascending)

        if not df.empty:
            print("\n" + "=" * 80)
            field_name = ranker.field_names.get(field_id, f"字段{field_id}")
            print(f"{field_name} 排名结果:")
            print("=" * 80)
            print(df.to_string(index=False))

            # 导出结果
            export = input("\n是否导出排名结果? (y/n): ").strip().lower()
            if export == 'y':
                filename = input(f"请输入导出文件名 (默认: {field_name}排名.xlsx): ") or f"{field_name}排名.xlsx"
                ranker.export_ranking_to_excel(df, filename)

    elif choice == '3':
        # 盈利能力排名
        print("\n正在按盈利能力进行排名...")
        df_roe = ranker.rank_by_specific_indicator(197, top_n=50)
        df_eps = ranker.rank_by_specific_indicator(1, top_n=50)

        if not df_roe.empty and not df_eps.empty:
            # 合并结果
            roe_dict = {row['股票代码']: row['排名'] for _, row in df_roe.iterrows()}
            eps_dict = {row['股票代码']: row['排名'] for _, row in df_eps.iterrows()}

            # 计算综合排名
            combined_scores = {}
            for code in set(list(roe_dict.keys())[:100] + list(eps_dict.keys())[:100]):
                roe_rank = roe_dict.get(code, 1000)
                eps_rank = eps_dict.get(code, 1000)
                combined_scores[code] = (roe_rank + eps_rank) / 2

            sorted_codes = sorted(combined_scores.items(), key=lambda x: x[1])

            results = []
            for rank, (code, score) in enumerate(sorted_codes[:50], 1):
                results.append({
                    '排名': rank,
                    '股票代码': code,
                    'ROE排名': roe_dict.get(code, '-'),
                    '每股收益排名': eps_dict.get(code, '-'),
                    '综合评分': round(score, 1)
                })

            df = pd.DataFrame(results)
            print("\n" + "=" * 80)
            print("盈利能力综合排名:")
            print("=" * 80)
            print(df.to_string(index=False))

    elif choice == '4':
        # 成长能力排名
        print("\n正在按成长能力进行排名...")
        df_rev_growth = ranker.rank_by_specific_indicator(183, top_n=50)
        df_profit_growth = ranker.rank_by_specific_indicator(184, top_n=50)

        if not df_rev_growth.empty and not df_profit_growth.empty:
            # 合并结果
            rev_dict = {row['股票代码']: row['排名'] for _, row in df_rev_growth.iterrows()}
            profit_dict = {row['股票代码']: row['排名'] for _, row in df_profit_growth.iterrows()}

            # 计算综合排名
            combined_scores = {}
            for code in set(list(rev_dict.keys())[:100] + list(profit_dict.keys())[:100]):
                rev_rank = rev_dict.get(code, 1000)
                profit_rank = profit_dict.get(code, 1000)
                combined_scores[code] = (rev_rank + profit_rank) / 2

            sorted_codes = sorted(combined_scores.items(), key=lambda x: x[1])

            results = []
            for rank, (code, score) in enumerate(sorted_codes[:50], 1):
                results.append({
                    '排名': rank,
                    '股票代码': code,
                    '营收增长排名': rev_dict.get(code, '-'),
                    '利润增长排名': profit_dict.get(code, '-'),
                    '综合评分': round(score, 1)
                })

            df = pd.DataFrame(results)
            print("\n" + "=" * 80)
            print("成长能力综合排名:")
            print("=" * 80)
            print(df.to_string(index=False))

    else:
        print("无效选择")


def quick_ranking():
    """快速排名示例"""
    CW_DIR = "d:/new_hxzq_hc/vipdoc/cw/"
    FIELD_FILE = "专业财务数据字段说明.txt"

    ranker = TDXStockRanker(CW_DIR, FIELD_FILE)

    print("正在对所有股票进行综合排名...")
    df = ranker.rank_all_stocks(years=3, top_n=100)

    if not df.empty:
        print("\n" + "=" * 100)
        print("上市公司财务健康度综合排名（前20名）:")
        print("=" * 100)
        print(df.head(20).to_string(index=False))

        # 导出完整结果
        ranker.export_ranking_to_excel(df, "上市公司财务排名.xlsx")

        # 按ROE单独排名
        print("\n" + "=" * 80)
        print("净资产收益率(ROE)排名前20:")
        print("=" * 80)
        df_roe = ranker.rank_by_specific_indicator(197, top_n=20)
        print(df_roe.to_string(index=False))


if __name__ == '__main__':
    print("通达信上市公司财务指标排序系统")
    print("=" * 60)

    mode = input("请选择模式:\n1. 完整交互模式\n2. 快速排名模式\n\n选择 (1/2): ").strip()

    if mode == '1':
        main()
    else:
        quick_ranking()