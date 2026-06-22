"""
============================================================================
 纯财务指标评分排名系统（独立版）

 功能：从综合财务与估值排名中，拆分出独立的纯财务评分排名
 - 仅使用财务指标（ROE、利润率、增长率、偿债能力、运营效率、现金流等）
 - 完全剔除估值指标（PE、PB、PS、PEG、股息率等）
 - 也无需加载股价数据，运行更快速
============================================================================
"""
from struct import unpack, calcsize
import os
import re
from datetime import datetime
import pandas as pd
from tqdm import tqdm
import warnings

warnings.filterwarnings('ignore')


class TDXPureFinancialRanker:
    """通达信纯财务指标排序器（不依赖股价/估值数据）"""

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

    # ──────────────────────────────────────────────
    #  字段说明加载
    # ──────────────────────────────────────────────
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

                if line.startswith('-------------') and '----------------' in line:
                    section_match = re.match(r'-*(\D+)-*', line)
                    if section_match:
                        current_section = section_match.group(1).strip()
                        continue

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
            for i in range(1, 585):
                self.field_names[i] = f"字段{i}"
                self.field_descriptions[i] = f"字段{i}"

    # ──────────────────────────────────────────────
    #  财务数据文件
    # ──────────────────────────────────────────────
    def get_latest_year_files(self, years=3):
        """
        获取最近几年的财务数据文件

        Args:
            years: 最近多少年

        Returns:
            排序后的文件路径列表
        """
        all_files = []
        for filename in os.listdir(self.cw_dir):
            if filename.startswith('gpcw') and filename.endswith('.dat'):
                date_str = filename[4:12]
                all_files.append((filename, date_str))

        all_files.sort(key=lambda x: x[1], reverse=True)
        print(all_files[:10])

        latest_files = []
        processed_years = set()

        for filename, date_str in all_files:
            year = date_str[:4]
            if year not in processed_years:
                processed_years.add(year)
                latest_files.append((filename, date_str))
            if len(processed_years) >= years:
                break

        latest_files.sort(key=lambda x: x[1])
        print(latest_files[:3])

        return [os.path.join(self.cw_dir, f[0]) for f in latest_files]

    def parse_all_stocks_in_file(self, file_path, field_indices=None, max_stocks=None):
        """
        解析单个财务数据文件中的所有股票

        Args:
            file_path: 数据文件路径
            field_indices: 需要提取的字段索引列表，None表示提取所有字段
            max_stocks: 最大解析股票数量（用于测试）

        Returns:
            字典，key为股票代码，value为字段数据字典
        """
        all_stocks_data = {}

        try:
            with open(file_path, 'rb') as cw_file:
                header_size = calcsize("<3h1H3L")
                data_header = cw_file.read(header_size)
                stock_header = unpack("<3h1H3L", data_header)
                max_count = int(stock_header[3])

                if max_stocks:
                    max_count = min(max_count, max_stocks)

                stock_item_size = calcsize("<6s1c1L")

                for stock_idx in tqdm(range(max_count), desc=f"解析 {os.path.basename(file_path)}", leave=False):
                    cw_file.seek(header_size + stock_idx * stock_item_size)
                    si = cw_file.read(stock_item_size)
                    stock_item = unpack("<6s1c1L", si)
                    code = stock_item[0].decode()
                    foa = stock_item[2]

                    cw_file.seek(foa)
                    data_size = 584 * 4
                    info_data = cw_file.read(data_size)

                    if len(info_data) < data_size:
                        data_size = 264 * 4
                        info_data = cw_file.read(data_size)
                        if len(info_data) < data_size:
                            continue
                        cw_info = unpack('<264f', info_data)
                        extended_info = list(cw_info) + [0.0] * (584 - 264)
                        cw_info = tuple(extended_info)
                    else:
                        cw_info = unpack('<584f', info_data)

                    if field_indices is None:
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

    # ──────────────────────────────────────────────
    #  纯财务得分计算（核心：不含任何估值指标）
    # ──────────────────────────────────────────────
    def calculate_pure_financial_score(self, stock_data_dict):
        """
        计算股票纯财务得分（仅含财务指标，不含PE/PB等估值指标）

        评分类别及权重（在原综合评分中财务部分占60%，现重归一化为100%）：
         - 盈利能力(ROE)        : 20%/60% ≈ 33.3%
         - 销售利润率           : 10%/60% ≈ 16.7%
         - 营收增长率           : 10%/60% ≈ 16.7%
         - 利润增长率           : 10%/60% ≈ 16.7%
         - 流动比率(偿债)       :  5%/60% ≈  8.3%
         - 资产负债率(反向)     :  5%/60% ≈  8.3%
         - 总资产周转率(运营)   :  5%/60% ≈  8.3%
         - 现金流              :  5%/60% ≈  8.3%
         ─────────────────────────
           总计                : 60%/60% = 100%
        """
        if not stock_data_dict:
            return 0

        # ── 获取最新报告期的数据 ──
        latest_date = max(stock_data_dict.keys()) if stock_data_dict else None
        if not latest_date:
            return 0
        latest_data = stock_data_dict[latest_date]

        # ── 纯财务权重（将原综合评分中财务部分的60%归一化为100%） ──
        financial_weights = {
            'roe':               0.333,   # 原 0.20 / 0.60
            'profit_margin':     0.167,   # 原 0.10 / 0.60
            'revenue_growth':    0.167,   # 原 0.10 / 0.60
            'profit_growth':     0.167,   # 原 0.10 / 0.60
            'current_ratio':     0.033,   # 原 0.05 / 0.60，适度降低流动性权重
            'debt_ratio':        0.033,   # 原 0.05 / 0.60（反向）
            'asset_turnover':    0.033,   # 原 0.05 / 0.60
            'cash_flow':         0.067,   # 原 0.05 / 0.60，提高现金流比重
        }
        # 重新微调：增强核心盈利能力与成长性权重
        financial_weights = {
            'roe':               0.30,    # 盈利能力核心
            'profit_margin':     0.12,    # 盈利质量
            'revenue_growth':    0.18,    # 成长性
            'profit_growth':     0.18,    # 成长性
            'current_ratio':     0.04,    # 偿债能力
            'debt_ratio':        0.04,    # 财务健康（反向）
            'asset_turnover':    0.05,    # 运营效率
            'cash_flow':         0.09,    # 现金流
        }

        # ── 获取原始财务指标值 ──
        raw_scores = {}

        # ROE (净资产收益率) - 字段197
        roe = latest_data.get(197, 0)
        raw_scores['roe'] = roe

        # 销售净利率 - 字段199
        profit_margin = latest_data.get(199, 0)
        raw_scores['profit_margin'] = profit_margin

        # 营业收入增长率 - 字段183
        revenue_growth = latest_data.get(183, 0)
        raw_scores['revenue_growth'] = revenue_growth

        # 净利润增长率 - 字段184
        profit_growth = latest_data.get(184, 0)
        raw_scores['profit_growth'] = profit_growth

        # 流动比率 - 字段159
        current_ratio = latest_data.get(159, 0)
        raw_scores['current_ratio'] = current_ratio

        # 资产负债率（反向指标）- 字段210，取 100 - 负债率
        debt_ratio = latest_data.get(210, 0)
        raw_scores['debt_ratio'] = 100 - debt_ratio if 0 < debt_ratio < 100 else (0 if debt_ratio >= 100 else 100)

        # 总资产周转率 - 字段175
        asset_turnover = latest_data.get(175, 0)
        raw_scores['asset_turnover'] = asset_turnover

        # 现金流得分 - 字段107（经营活动现金流净额），用亿元为单位并限幅，避免异常值，限幅在[-10, 10]之间
        cash_flow = latest_data.get(107, 0)
        # 异常值处理，避免除以0或过大值
        if abs(cash_flow) > 1e10:
            cash_flow = 0
        raw_scores['cash_flow'] = cash_flow / 1e8 if cash_flow != 0 else 0

        # ── 标准化处理 ──
        def normalize_scores(scores_dict):
            if not scores_dict:
                return {}

            valid_values = []
            for key, val in scores_dict.items():
                # 对反向处理的 debt_ratio 直接取有效范围
                v = abs(val)
                if v < 1e6:
                    valid_values.append(v)

            if not valid_values:
                return {k: 0 for k in scores_dict.keys()}

            max_val = max(valid_values)
            if max_val == 0:
                return {k: 0 for k in scores_dict.keys()}

            normalized = {}
            for key, value in scores_dict.items():
                abs_v = abs(value)
                if 0 < abs_v < 1e6:
                    normalized[key] = value / max_val
                else:
                    normalized[key] = 0

            return normalized

        normalized = normalize_scores(raw_scores)

        # ── 计算综合得分 ──
        total_score = 0.0
        for indicator, weight in financial_weights.items():
            score = normalized.get(indicator, 0)
            total_score += score * weight

        return total_score

    # ──────────────────────────────────────────────
    #  rank_by_category：支持多个评分类别的快捷排名
    # ──────────────────────────────────────────────
    def rank_by_category(self, years=3, top_n=100, category='综合', test_mode=False):
        """
        按类别进行排名（这里只实现纯财务评分，类别用于扩展）

        Args:
            years: 使用最近多少年的数据
            top_n: 显示前多少名
            category: 排名类别
                 - '综合' : 纯财务综合评分（包含所有财务指标）
                 - '盈利能力' : 只按盈利能力评分（ROE+利润率）
                 - '成长能力' : 只按成长能力评分（营收增长+利润增长）
                 - '偿债能力' : 只按偿债能力评分（流动比率+资产负债率反向）
                 - '运营效率' : 只按运营效率评分（总资产周转率+现金流）
            test_mode: 测试模式

        Returns:
            DataFrame
        """
        print(f"获取最近{years}年的财务数据文件...")
        files = self.get_latest_year_files(years)

        if not files:
            print("未找到财务数据文件")
            return pd.DataFrame()

        print(f"找到 {len(files)} 个财务数据文件")

        # ── 定义需要提取的财务字段 ──
        # (只需要财务指标，不需要任何估值/股价相关字段)
        field_indices = [
            1,    # 基本每股收益
            4,    # 每股净资产
            6,    # 净资产收益率(每股指标)
            72,   # 所有者权益合计
            74,   # 营业收入
            75,   # 营业成本
            86,   # 营业利润
            95,   # 净利润
            96,   # 归属于母公司所有者的净利润
            107,  # 经营活动产生的现金流量净额
            125,  # 分配股利、利润或偿付利息支付的现金
            159,  # 流动比率
            175,  # 总资产周转率
            183,  # 营业收入增长率
            184,  # 净利润增长率
            197,  # 净资产收益率(获利能力)
            199,  # 销售净利率
            200,  # 总资产净利率
            202,  # 销售毛利率
            208,  # 息税折旧摊销前利润(EBITDA)
            210,  # 资产负债率
            219,  # 每股经营性现金流
            238,  # 总股本
        ]

        # ── 解析最新财务数据文件 ──应依次解析每个财务文件，进行多期文件的解析

        latest_file = files[-2]
        print(latest_file)
        filename = os.path.basename(latest_file)
        date_str = filename[4:12]
        print(f"解析最新财务数据文件: {filename} ({date_str[:4]}-{date_str[4:6]}-{date_str[6:8]})")

        max_stocks = 1000 if test_mode else None
        stocks_data = self.parse_all_stocks_in_file(latest_file, field_indices, max_stocks)
        print(f"共收集到 {len(stocks_data)} 只股票的财务数据")

        if len(stocks_data) == 0:
            print("警告: 没有解析到任何股票数据")
            return pd.DataFrame()

        # ── 计算每只股票的纯财务得分 ──
        print(f"\n计算纯财务 {category} 得分...")
        stock_scores = {}
        stock_details = {}

        processed = 0
        for stock_code, financial_data in tqdm(stocks_data.items(), desc="计算得分"):
            multi_data = {date_str: financial_data}

            if category == '综合':
                # 纯财务综合评分（包含全部财务指标）
                score = self.calculate_pure_financial_score(multi_data)
            elif category == '盈利能力':
                roe = financial_data.get(197, 0)
                profit_margin = financial_data.get(199, 0)
                roa = financial_data.get(200, 0)
                gross_margin = financial_data.get(202, 0)
                # 盈利能力打分
                score = (roe * 0.40 + profit_margin * 0.25 +
                         roa * 0.20 + gross_margin * 0.15)
            elif category == '成长能力':
                revenue_growth = financial_data.get(183, 0)
                profit_growth = financial_data.get(184, 0)
                eps = financial_data.get(1, 0)
                # 成长能力打分
                score = (revenue_growth * 0.35 + profit_growth * 0.40 +
                         eps * 0.25)
            elif category == '偿债能力':
                current_ratio = financial_data.get(159, 0)
                debt_ratio = financial_data.get(210, 0)
                debt_score = 100 - debt_ratio if 0 < debt_ratio < 100 else 0
                # 偿债能力打分
                score = current_ratio * 0.50 + debt_score * 0.50
            elif category == '运营效率':
                asset_turnover = financial_data.get(175, 0)
                cash_flow = financial_data.get(107, 0)
                cf_score = cash_flow / 1e8 if abs(cash_flow) < 1e10 else 0
                score = asset_turnover * 0.50 + cf_score * 0.50
            else:
                continue

            stock_scores[stock_code] = score
            stock_details[stock_code] = {
                'financial_data': financial_data,
            }

            processed += 1
            if test_mode and processed >= 50:
                break

        if len(stock_scores) == 0:
            print("警告: 没有计算任何股票的得分")
            return pd.DataFrame()

        # ── 排序 ──
        sorted_stocks = sorted(stock_scores.items(), key=lambda x: x[1], reverse=True)

        results = []
        for rank, (stock_code, score) in enumerate(sorted_stocks[:top_n], 1):
            if stock_code not in stock_details:
                continue

            details = stock_details[stock_code]
            fin = details['financial_data']

            results.append({
                '排名': rank,
                '股票代码': stock_code,
                f'纯财务{category}得分': round(score, 4),
                'ROE(%)': round(fin.get(197, 0), 2),
                '销售净利率(%)': round(fin.get(199, 0), 2),
                '营收增长率(%)': round(fin.get(183, 0), 2),
                '净利润增长率(%)': round(fin.get(184, 0), 2),
                '净利润(亿)': round(fin.get(95, 0) / 1e8, 2) if fin.get(95, 0) != 0 and abs(fin.get(95, 0)) < 1e12 else 0,
                '营业收入(亿)': round(fin.get(74, 0) / 1e8, 2) if fin.get(74, 0) != 0 and abs(fin.get(74, 0)) < 1e12 else 0,
                '每股收益(元)': round(fin.get(1, 0), 2),
                '资产负债率(%)': round(fin.get(210, 0), 2),
                '流动比率': round(fin.get(159, 0), 2),
                '总资产周转率': round(fin.get(175, 0), 4),
                '现金流(亿)': round(fin.get(107, 0) / 1e8, 2) if fin.get(107, 0) != 0 and abs(fin.get(107, 0)) < 1e12 else 0,
                '每股净资产(元)': round(fin.get(4, 0), 2),
                '总股本(亿)': round(fin.get(238, 0) / 1e8, 2) if fin.get(238, 0) > 0 else 0,
            })

        df = pd.DataFrame(results)
        return df

    # ──────────────────────────────────────────────
    #  导出结果
    # ──────────────────────────────────────────────
    def export_to_excel(self, dfs_dict, filename="股票纯财务排名.xlsx"):
        """导出排名结果到Excel文件"""
        if not dfs_dict:
            print("没有数据可导出")
            return

        try:
            with pd.ExcelWriter(filename, engine='openpyxl') as writer:
                for category, df in dfs_dict.items():
                    if not df.empty:
                        sheet_name = category[:30]
                        df.to_excel(writer, sheet_name=sheet_name, index=False)

                        worksheet = writer.sheets[sheet_name]
                        for column in worksheet.columns:
                            max_length = 0
                            col_letter = column[0].column_letter
                            for cell in column:
                                try:
                                    if len(str(cell.value)) > max_length:
                                        max_length = len(str(cell.value))
                                except:
                                    pass
                            adjusted_width = min(max_length + 2, 30)
                            worksheet.column_dimensions[col_letter].width = adjusted_width

                # ── 指标说明 ──
                field_info = []
                for idx in [1, 4, 6, 72, 74, 95, 107, 159, 175, 183, 184, 197, 199, 200, 202, 210, 219, 238]:
                    if idx in self.field_names:
                        field_info.append({
                            '字段ID': idx,
                            '字段名称': self.field_names[idx],
                            '说明': self.field_descriptions.get(idx, '')
                        })
                if field_info:
                    pd.DataFrame(field_info).to_excel(writer, sheet_name='财务指标说明', index=False)

                info_df = pd.DataFrame({
                    '说明': [
                        '纯财务评分：完全基于财务报表指标，不包含PE/PB等估值指标',
                        '评分权重：ROE 30%、营收增长18%、利润增长18%、利润率12%、现金流9%、资产周转率5%等',
                        '与综合评分的区别：综合评分=财务指标+估值指标；本评分纯看财务基本面',
                        '财务数据来源：通达信财务数据(gpcw*.dat)',
                        '本程序不依赖股价数据，运行更快速',
                        f'生成时间：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}'
                    ]
                })
                info_df.to_excel(writer, sheet_name='数据说明', index=False)

            print(f"排名结果已导出到: {filename}")

        except Exception as e:
            print(f"导出Excel文件时出错: {e}")
            for category, df in dfs_dict.items():
                if not df.empty:
                    csv_file = f"{category}_排名.csv"
                    df.to_csv(csv_file, index=False, encoding='utf-8-sig')
                    print(f"已导出为CSV: {csv_file}")


# ═══════════════════════════════════════════════════
#  主程序入口
# ═══════════════════════════════════════════════════
def main():
    print("=" * 80)
    print("通达信上市公司纯财务评分排名系统（独立版）")
    print("=" * 80)
    print()

    CW_DIR = "d:/new_hxzq_hc/vipdoc/cw/"
    FIELD_FILE = "专业财务数据字段说明.txt"

    ranker = TDXPureFinancialRanker(CW_DIR, FIELD_FILE)

    # ── 交互选择 ──
    print("请选择排名类型:")
    print("1. 纯财务综合评分排名（推荐）")
    print("2. 盈利能力排名")
    print("3. 成长能力排名")
    print("4. 偿债能力排名")
    print("5. 运营效率排名")
    print("6. 测试模式（少量股票快速验证）")
    print("7. 所有类别排名")

    choice = input("\n请选择 (1-7): ").strip()

    test_mode = False
    if choice == '6':
        test_mode = True
        choice = '1'
        print("测试模式：仅解析少量股票")

    mapping = {
        '1': ['综合'],
        '2': ['盈利能力'],
        '3': ['成长能力'],
        '4': ['偿债能力'],
        '5': ['运营效率'],
        '6': ['综合'],
        '7': ['综合', '盈利能力', '成长能力', '偿债能力', '运营效率'],
    }
    categories = mapping.get(choice, ['综合'])

    years_val = 1 if test_mode else int(input("使用最近几年的数据? (默认3): ") or "3")
    top_n_val = 20 if test_mode else int(input("显示前多少名? (默认50): ") or "50")

    results = {}
    for cat in categories:
        print(f"\n{'─' * 60}")
        print(f"正在计算纯财务{cat}排名...")
        df = ranker.rank_by_category(years=years_val, top_n=top_n_val, category=cat, test_mode=test_mode)
        if not df.empty:
            results[cat] = df
            print(f"\n纯财务『{cat}』排名前{min(20, len(df))}名:")
            print("=" * 120)
            print(df.head(20).to_string(index=False))
            print(f"共 {len(df)} 只股票")
        else:
            print(f"未获取到{cat}排名数据")

    # ── 导出 ──
    if results:
        exp = input("\n是否导出排名结果? (y/n): ").strip().lower()
        if exp == 'y':
            time_stamp = datetime.now().strftime("%Y%m%d%H%M")
            fn = input(f"请输入文件名 (默认: 股票纯财务排名{time_stamp}.xlsx): ")
            if not fn:
                fn = f"股票纯财务排名{time_stamp}.xlsx"
            ranker.export_to_excel(results, fn)


def quick_demo():
    """快速演示：纯财务评分与旧综合评分的对比示意"""
    CW_DIR = "d:/new_hxzq_hc/vipdoc/cw/"
    FIELD_FILE = "专业财务数据字段说明.txt"

    ranker = TDXPureFinancialRanker(CW_DIR, FIELD_FILE)

    print("=" * 80)
    print(" 纯财务评分排名 vs 综合财务&估值排名 对比说明")
    print("=" * 80)
    print()
    print("【原综合评分 = 财务指标(60%) + 估值指标(40%)】")
    print("   财务部分: ROE、利润率、增长率、流动比率、负债率、周转率、现金流")
    print("   估值部分: PE ÷1、PB ÷1、PS ÷1、PEG ÷1、股息率")
    print()
    print("【本纯财务评分 = 财务指标(100%)】")
    print("   去掉估值成分，财务部分的权重重归一化为100%")
    print("   运行更快（无需日线股价数据），反映纯粹的基本面质量")
    print()

    # 执行一次综合排名
    df = ranker.rank_by_category(years=3, top_n=50, category='综合')
    if not df.empty:
        print("\n├─ 纯财务综合评分 Top 20 ─────────────────────")
        print(df.head(20).to_string(index=False))

    # 导出样例数据
    exp = input("\n导出示例结果? (y/n): ").strip().lower()
    if exp == 'y':
        ts = datetime.now().strftime("%Y%m%d%H%M")
        fn = f"股票纯财务排名示例_{ts}.xlsx"
        ranker.export_to_excel({'纯财务综合': df}, fn)


if __name__ == '__main__':
    print("通达信纯财务评分排名系统")
    print("=" * 60)
    print("1. 交互式排名")
    print("2. 快速（对比）演示")

    m = input("\n请选择 (1-2): ").strip()
    if m == '1':
        main()
    elif m == '2':
        quick_demo()
    else:
        print("无效选择，运行交互模式")
        main()
