from struct import unpack, calcsize
import os
import re
from datetime import datetime, timedelta
import pandas as pd
from tqdm import tqdm
import warnings
import holidays

warnings.filterwarnings('ignore')


class TDXFinancialValuationRanker:
    """通达信财务与估值综合排序器"""

    def __init__(self, cw_dir, day_data_dir, field_file="专业财务数据字段说明.txt"):
        """
        初始化排序器

        Args:
            cw_dir: 财务数据文件目录
            day_data_dir: 日线数据根目录
            field_file: 字段说明文件路径
        """
        self.cw_dir = cw_dir
        self.day_data_dir = day_data_dir
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

    def get_market_from_code(self, stock_code):
        """根据股票代码判断市场"""
        if stock_code.startswith('6') or stock_code.startswith('9'):
            return 'sh'
        elif stock_code.startswith('0') or stock_code.startswith('3'):
            return 'sz'
        elif stock_code.startswith('4') or stock_code.startswith('8'):
            return 'bj'
        else:
            return 'ds'

    def get_day_file_path(self, stock_code):
        """获取日线数据文件路径"""
        market = self.get_market_from_code(stock_code)
        market_prefix = ''
        if market == 'sh':
            market_prefix = 'SH'
        elif market == 'sz':
            market_prefix = 'SZ'
        elif market == 'bj':
            market_prefix = 'BJ'
        else:
            market_prefix = 'DS'

        file_name = f"{market_prefix}{stock_code}.day"
        file_path = os.path.join(self.day_data_dir, market, 'lday', file_name)

        # 如果不存在，尝试其他可能的路径
        if not os.path.exists(file_path):
            # 尝试另一种命名方式
            alt_file_path = os.path.join(self.day_data_dir, market, 'lday', f"{stock_code}.day")
            if os.path.exists(alt_file_path):
                return alt_file_path

        return file_path

    def parse_tdx_day_record(self, record_buffer, format_type='standard'):
        """
        解析通达信日线数据记录

        Args:
            record_buffer: 二进制数据
            format_type: 格式类型 ('standard' 或 'alternative')

        Returns:
            解析后的数据字典
        """
        try:
            if format_type == 'standard':
                # 标准格式: <5If2I (小端字节序)
                # 日期(4), 开盘价(4), 最高价(4), 最低价(4), 收盘价(4), 成交额(4), 成交量(4), 保留(4)
                data = unpack('<5If2I', record_buffer)

                return {
                    'date': data[0],  # 日期 (YYYYMMDD格式)
                    'open': data[1] / 100,  # 开盘价
                    'high': data[2] / 100,  # 最高价
                    'low': data[3] / 100,  # 最低价
                    'close': data[4] / 100,  # 收盘价
                    'amount': data[5],  # 成交额
                    'volume': data[6],  # 成交量
                    'spare': data[7]  # 保留
                }
            elif format_type == 'alternative':
                # 备选格式: <I4f2I (小端字节序)
                # 日期(4), 开盘价(4), 最高价(4), 最低价(4), 收盘价(4), 成交额(4), 成交量(4), 保留(4)
                data = unpack('<I4f2I', record_buffer)

                return {
                    'date': data[0],  # 日期 (YYYYMMDD格式)
                    'open': data[1],  # 开盘价 (已经是元)
                    'high': data[2],  # 最高价
                    'low': data[3],  # 最低价
                    'close': data[4],  # 收盘价
                    'amount': data[5],  # 成交额
                    'volume': data[6],  # 成交量
                    'spare': data[7]  # 保留
                }
            else:
                print(f"未知的格式类型: {format_type}")
                return None

        except Exception as e:
            # 尝试其他可能的格式
            if format_type == 'standard':
                return self.parse_tdx_day_record(record_buffer, 'alternative')
            else:
                print(f"解析日线数据记录时出错: {e}")
                return None

    def get_latest_price_data(self, stock_code):
        """获取最新股价数据"""
        file_path = self.get_day_file_path(stock_code)

        if not os.path.exists(file_path):
            print(f"警告: 股票 {stock_code} 的日线数据文件不存在: {file_path}")
            return None

        try:
            # 获取文件大小
            file_size = os.path.getsize(file_path)
            if file_size == 0:
                print(f"警告: 股票 {stock_code} 的日线数据文件为空")
                return None

            # 尝试不同的记录大小 (通达信日线数据记录可能是32字节或28字节)
            record_sizes = [32, 28]
            record_data = None

            with open(file_path, 'rb') as f:
                for record_size in record_sizes:
                    # 计算记录数量
                    record_count = file_size // record_size
                    if record_count == 0:
                        continue

                    try:
                        # 读取最后一条记录
                        f.seek(-record_size, 2)
                        record_buffer = f.read(record_size)

                        # 尝试解析记录
                        if record_size == 32:
                            record_data = self.parse_tdx_day_record(record_buffer, 'standard')
                        elif record_size == 28:
                            # 28字节格式可能需要特殊处理
                            # 尝试标准格式解析
                            record_data = self.parse_tdx_day_record(record_buffer, 'standard')

                        if record_data:
                            break
                    except Exception:
                        continue

                # 如果仍然无法解析，尝试读取第一条记录
                if not record_data:
                    f.seek(0)
                    record_buffer = f.read(32)  # 尝试32字节
                    if len(record_buffer) == 32:
                        record_data = self.parse_tdx_day_record(record_buffer, 'standard')
                    elif len(record_buffer) == 28:
                        record_data = self.parse_tdx_day_record(record_buffer, 'alternative')

                if record_data:
                    return record_data
                else:
                    print(f"警告: 无法解析股票 {stock_code} 的日线数据")
                    return None

        except Exception as e:
            print(f"读取股票 {stock_code} 的日线数据时出错: {e}")
            return None

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
                # 读取文件头
                header_size = calcsize("<3h1H3L")
                data_header = cw_file.read(header_size)
                stock_header = unpack("<3h1H3L", data_header)
                max_count = stock_header[3]

                # 限制解析数量用于测试
                if max_stocks:
                    max_count = min(max_count, max_stocks)

                # 读取股票索引
                stock_item_size = calcsize("<6s1c1L")

                for stock_idx in tqdm(range(max_count), desc=f"解析 {os.path.basename(file_path)}", leave=False):
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

    def calculate_valuation_metrics(self, stock_data, price_data):
        """
        计算估值指标

        Args:
            stock_data: 财务数据字典
            price_data: 股价数据字典

        Returns:
            估值指标字典
        """
        if not price_data or 'close' not in price_data:
            return {
                'pe': 0, 'pb': 0, 'ps': 0, 'pcf': 0, 'peg': 0,
                'dividend_yield': 0, 'ev_ebitda': 0, 'market_cap': 0,
                'price': 0
            }

        close_price = price_data['close']

        # 获取财务数据
        net_profit = stock_data.get(95, 0)  # 净利润
        net_asset = stock_data.get(72, 0)  # 净资产(所有者权益合计)
        revenue = stock_data.get(74, 0)  # 营业收入
        cash_flow = stock_data.get(107, 0)  # 经营活动现金流净额
        total_shares = stock_data.get(238, 0)  # 总股本
        ebitda = stock_data.get(208, 0)  # EBITDA
        profit_growth = stock_data.get(184, 0)  # 净利润增长率
        dividend = stock_data.get(125, 0)  # 分配股利、利润或偿付利息支付的现金

        # 计算总市值
        if total_shares > 0:
            market_cap = close_price * total_shares
        else:
            # 如果总股本数据缺失，使用简化估算
            market_cap = close_price * 100000000  # 假设1亿股

        # 计算估值指标
        metrics = {}

        # 市盈率 PE = 市值 / 净利润
        if net_profit > 0:
            metrics['pe'] = market_cap / net_profit
        else:
            metrics['pe'] = 0

        # 市净率 PB = 市值 / 净资产
        if net_asset > 0:
            metrics['pb'] = market_cap / net_asset
        else:
            metrics['pb'] = 0

        # 市销率 PS = 市值 / 营业收入
        if revenue > 0:
            metrics['ps'] = market_cap / revenue
        else:
            metrics['ps'] = 0

        # 市现率 PCF = 市值 / 现金流
        if cash_flow > 0:
            metrics['pcf'] = market_cap / cash_flow
        else:
            metrics['pcf'] = 0

        # PEG = PE / 盈利增长率
        if metrics['pe'] > 0 and profit_growth > 0:
            metrics['peg'] = metrics['pe'] / profit_growth
        else:
            metrics['peg'] = 0

        # 股息率 = 股息 / 市值
        if market_cap > 0 and dividend > 0:
            metrics['dividend_yield'] = dividend / market_cap * 100
        else:
            metrics['dividend_yield'] = 0

        # EV/EBITDA
        if ebitda > 0:
            # 简化计算：EV ≈ 市值
            metrics['ev_ebitda'] = market_cap / ebitda
        else:
            metrics['ev_ebitda'] = 0

        metrics['market_cap'] = market_cap
        metrics['price'] = close_price

        return metrics

    def calculate_comprehensive_score(self, stock_data_dict, valuation_metrics):
        """
        计算股票综合得分（财务+估值）

        Args:
            stock_data_dict: 包含多个报告期数据的字典
            valuation_metrics: 估值指标字典

        Returns:
            综合得分
        """
        if not stock_data_dict:
            return 0

        # 财务指标权重
        financial_weights = {
            'roe': 0.20,  # 盈利能力
            'profit_margin': 0.10,
            'revenue_growth': 0.10,  # 成长能力
            'profit_growth': 0.10,
            'current_ratio': 0.05,  # 偿债能力
            'debt_ratio': 0.05,  # 财务健康度（反向）
            'asset_turnover': 0.05,  # 运营效率
            'cash_flow': 0.05,  # 现金流
        }

        # 估值指标权重
        valuation_weights = {
            'pe': 0.10,  # 越低越好
            'pb': 0.10,  # 越低越好
            'ps': 0.05,  # 越低越好
            'peg': 0.05,  # 越低越好
            'dividend_yield': 0.05,  # 越高越好
        }

        # 获取最新报告期的数据
        latest_data = None
        latest_date = max(stock_data_dict.keys()) if stock_data_dict else None
        if latest_date:
            latest_data = stock_data_dict[latest_date]

        if not latest_data:
            return 0

        # 计算财务指标得分
        financial_scores = {}

        # ROE (净资产收益率)
        roe = latest_data.get(197, 0)
        financial_scores['roe'] = roe

        # 销售净利率
        profit_margin = latest_data.get(199, 0)
        financial_scores['profit_margin'] = profit_margin

        # 营业收入增长率
        revenue_growth = latest_data.get(183, 0)
        financial_scores['revenue_growth'] = revenue_growth

        # 净利润增长率
        profit_growth = latest_data.get(184, 0)
        financial_scores['profit_growth'] = profit_growth

        # 流动比率
        current_ratio = latest_data.get(159, 0)
        financial_scores['current_ratio'] = current_ratio

        # 资产负债率（反向指标）
        debt_ratio = latest_data.get(210, 0)
        financial_scores['debt_ratio'] = 100 - debt_ratio if debt_ratio > 0 else 0

        # 总资产周转率
        asset_turnover = latest_data.get(175, 0)
        financial_scores['asset_turnover'] = asset_turnover

        # 现金流得分
        cash_flow = latest_data.get(107, 0)
        # 避免除以0或过大值
        if abs(cash_flow) > 1e10:
            cash_flow = 0
        financial_scores['cash_flow'] = cash_flow / 1e9 if cash_flow != 0 else 0

        # 计算估值指标得分（注意：有些指标是越低越好，有些是越高越好）
        valuation_scores = {}

        # PE（市盈率）：越低越好，使用倒数
        pe = valuation_metrics.get('pe', 0)
        valuation_scores['pe'] = 1 / pe if pe > 0 and pe < 1e6 else 0

        # PB（市净率）：越低越好，使用倒数
        pb = valuation_metrics.get('pb', 0)
        valuation_scores['pb'] = 1 / pb if pb > 0 and pb < 1e6 else 0

        # PS（市销率）：越低越好，使用倒数
        ps = valuation_metrics.get('ps', 0)
        valuation_scores['ps'] = 1 / ps if ps > 0 and ps < 1e6 else 0

        # PEG（市盈增长比）：越低越好，使用倒数
        peg = valuation_metrics.get('peg', 0)
        valuation_scores['peg'] = 1 / peg if peg > 0 and peg < 1e6 else 0

        # 股息率：越高越好，直接使用
        dividend_yield = valuation_metrics.get('dividend_yield', 0)
        valuation_scores['dividend_yield'] = min(dividend_yield, 10)  # 限制最大值

        # 标准化处理
        def normalize_scores(scores_dict):
            if not scores_dict:
                return {}

            # 找到最大值（排除异常值）
            valid_values = [abs(v) for v in scores_dict.values() if 0 < abs(v) < 1e6]
            if not valid_values:
                return {k: 0 for k in scores_dict.keys()}

            max_val = max(valid_values)
            if max_val == 0:
                return {k: 0 for k in scores_dict.keys()}

            normalized = {}
            for key, value in scores_dict.items():
                if 0 < abs(value) < 1e6:  # 排除异常值
                    normalized[key] = value / max_val
                else:
                    normalized[key] = 0

            return normalized

        # 标准化财务指标得分
        normalized_financial = normalize_scores(financial_scores)

        # 标准化估值指标得分
        normalized_valuation = normalize_scores(valuation_scores)

        # 计算综合得分
        total_score = 0

        # 财务指标部分
        for indicator, weight in financial_weights.items():
            score = normalized_financial.get(indicator, 0)
            total_score += score * weight

        # 估值指标部分
        for indicator, weight in valuation_weights.items():
            score = normalized_valuation.get(indicator, 0)
            total_score += score * weight

        return total_score

    def rank_by_category(self, years=3, top_n=100, category='综合', test_mode=False):
        """
        按类别进行排名

        Args:
            years: 使用最近多少年的数据
            top_n: 显示前多少名
            category: 排名类别 ('综合', '盈利能力', '成长能力', '估值')
            test_mode: 测试模式，只处理少量股票

        Returns:
            DataFrame，包含排名结果
        """
        print(f"获取最近{years}年的财务数据文件...")
        files = self.get_latest_year_files(years)

        if not files:
            print("未找到财务数据文件")
            return pd.DataFrame()

        print(f"找到 {len(files)} 个财务数据文件")

        # 定义需要提取的字段
        field_indices = [
            1,  # 基本每股收益
            4,  # 每股净资产
            6,  # 净资产收益率(每股指标)
            72,  # 所有者权益合计
            74,  # 营业收入
            75,  # 营业成本
            86,  # 营业利润
            95,  # 净利润
            96,  # 归属于母公司所有者的净利润
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

        # 解析最新财务数据文件
        latest_file = files[-1]
        filename = os.path.basename(latest_file)
        date_str = filename[4:12]
        print(f"解析最新财务数据文件: {filename} ({date_str[:4]}-{date_str[4:6]}-{date_str[6:8]})")

        # 如果测试模式，只解析少量股票
        max_stocks = 100 if test_mode else None
        stocks_data = self.parse_all_stocks_in_file(latest_file, field_indices, max_stocks)

        print(f"共收集到 {len(stocks_data)} 只股票的财务数据")

        if len(stocks_data) == 0:
            print("警告: 没有解析到任何股票数据")
            return pd.DataFrame()

        # 计算每只股票的得分
        print(f"\n计算股票{category}得分...")
        stock_scores = {}
        stock_details = {}

        processed = 0
        skipped_no_price = 0

        for stock_code, financial_data in tqdm(stocks_data.items(), desc="计算得分"):
            # 获取最新股价数据
            price_data = self.get_latest_price_data(stock_code)

            if price_data is None:
                skipped_no_price += 1
                continue  # 跳过没有股价数据的股票

            # 创建多期数据字典（简化版本，只使用最新数据）
            multi_data = {date_str: financial_data}

            # 计算估值指标
            valuation_metrics = self.calculate_valuation_metrics(financial_data, price_data)

            # 根据类别计算得分
            if category == '综合':
                score = self.calculate_comprehensive_score(multi_data, valuation_metrics)
            elif category == '盈利能力':
                # 盈利能力得分：ROE + 利润率
                roe = financial_data.get(197, 0)
                profit_margin = financial_data.get(199, 0)
                score = roe * 0.6 + profit_margin * 0.4
            elif category == '成长能力':
                # 成长能力得分：营收增长 + 利润增长
                revenue_growth = financial_data.get(183, 0)
                profit_growth = financial_data.get(184, 0)
                score = revenue_growth * 0.5 + profit_growth * 0.5
            elif category == '估值':
                # 估值得分：PE、PB、PEG的倒数加权
                pe = valuation_metrics.get('pe', 0)
                pb = valuation_metrics.get('pb', 0)
                peg = valuation_metrics.get('peg', 0)
                dividend_yield = valuation_metrics.get('dividend_yield', 0)

                pe_score = 1 / pe if pe > 0 and pe < 1e6 else 0
                pb_score = 1 / pb if pb > 0 and pb < 1e6 else 0
                peg_score = 1 / peg if peg > 0 and peg < 1e6 else 0
                dividend_score = min(dividend_yield, 10) / 10  # 标准化

                score = pe_score * 0.3 + pb_score * 0.3 + peg_score * 0.2 + dividend_score * 0.2
            else:
                continue

            stock_scores[stock_code] = score
            stock_details[stock_code] = {
                'financial_data': financial_data,
                'valuation_metrics': valuation_metrics,
                'price_data': price_data
            }

            processed += 1

            # 测试模式下只处理少量股票
            if test_mode and processed >= 50:
                break

        if skipped_no_price > 0:
            print(f"跳过了 {skipped_no_price} 只没有股价数据的股票")

        if len(stock_scores) == 0:
            print("警告: 没有计算任何股票的得分")
            return pd.DataFrame()

        # 按得分排序
        sorted_stocks = sorted(stock_scores.items(), key=lambda x: x[1], reverse=True)

        # 创建结果DataFrame
        results = []

        for rank, (stock_code, score) in enumerate(sorted_stocks[:top_n], 1):
            if stock_code not in stock_details:
                continue

            details = stock_details[stock_code]
            financial = details['financial_data']
            valuation = details['valuation_metrics']
            price = details['price_data']

            results.append({
                '排名': rank,
                '股票代码': stock_code,
                f'{category}得分': round(score, 4),
                '当前股价': round(price['close'], 2),
                'ROE(%)': round(financial.get(197, 0), 2),
                '净利润(亿)': round(financial.get(95, 0) / 1e8, 2) if financial.get(95, 0) != 0 else 0,
                '营收增长率(%)': round(financial.get(183, 0), 2),
                'PE(倍)': round(valuation.get('pe', 0), 2),
                'PB(倍)': round(valuation.get('pb', 0), 2),
                'PS(倍)': round(valuation.get('ps', 0), 2),
                '股息率(%)': round(valuation.get('dividend_yield', 0), 2),
                '市值(亿)': round(valuation.get('market_cap', 0) / 1e8, 2) if valuation.get('market_cap', 0) > 0 else 0,
            })

        df = pd.DataFrame(results)
        return df

    def export_ranking_to_excel(self, dfs_dict, filename="股票综合排名.xlsx"):
        """导出排名结果到Excel文件"""
        if not dfs_dict:
            print("没有数据可导出")
            return

        try:
            with pd.ExcelWriter(filename, engine='openpyxl') as writer:
                # 写入各分类排名
                for category, df in dfs_dict.items():
                    if not df.empty:
                        df.to_excel(writer, sheet_name=category[:30], index=False)  # Excel工作表名称不能超过31字符

                        # 调整列宽
                        worksheet = writer.sheets[category[:30]]
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

                # 添加指标说明
                field_info = []
                for idx in [1, 197, 74, 95, 183, 184, 210, 107]:
                    if idx in self.field_names:
                        field_info.append({
                            '字段ID': idx,
                            '字段名称': self.field_names[idx],
                            '说明': self.field_descriptions.get(idx, '')
                        })

                if field_info:
                    field_df = pd.DataFrame(field_info)
                    field_df.to_excel(writer, sheet_name='财务指标说明', index=False)

                # 添加估值指标说明
                valuation_info = [
                    {'指标': 'PE', '说明': '市盈率 = 市值 / 净利润，衡量股价相对于盈利的估值水平'},
                    {'指标': 'PB', '说明': '市净率 = 市值 / 净资产，衡量股价相对于净资产的估值水平'},
                    {'指标': 'PS', '说明': '市销率 = 市值 / 营业收入，衡量股价相对于营收的估值水平'},
                    {'指标': 'PEG', '说明': '市盈增长比 = PE / 盈利增长率，考虑成长性的估值指标'},
                    {'指标': '股息率', '说明': '股息收益率 = 股息 / 股价，衡量分红回报'},
                ]

                valuation_df = pd.DataFrame(valuation_info)
                valuation_df.to_excel(writer, sheet_name='估值指标说明', index=False)

                # 添加数据说明
                info_df = pd.DataFrame({
                    '说明': [
                        '综合得分：根据财务指标和估值指标加权计算得出',
                        '财务数据来源：通达信财务数据',
                        '股价数据来源：通达信日线数据',
                        '排名规则：得分越高表示综合表现越好',
                        f'生成时间：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}'
                    ]
                })
                info_df.to_excel(writer, sheet_name='数据说明', index=False)

            print(f"排名结果已导出到: {filename}")

        except Exception as e:
            print(f"导出Excel文件时出错: {e}")
            # 尝试导出为CSV
            for category, df in dfs_dict.items():
                if not df.empty:
                    csv_file = f"{category}_排名.csv"
                    df.to_csv(csv_file, index=False, encoding='utf-8-sig')
                    print(f"已导出 {category} 排名为CSV文件: {csv_file}")


def main():
    """主函数"""
    print("=" * 80)
    print("通达信上市公司财务与估值综合排序系统")
    print("=" * 80)

    # 配置参数
    CW_DIR = "d:/new_hxzq_hc/vipdoc/cw/"  # 通达信财务数据目录
    DAY_DATA_DIR = "d:/new_hxzq_hc/vipdoc/"  # 通达信日线数据根目录
    FIELD_FILE = "专业财务数据字段说明.txt"  # 字段说明文件

    # 创建排序器
    ranker = TDXFinancialValuationRanker(CW_DIR, DAY_DATA_DIR, FIELD_FILE)

    # 测试日线数据读取
    print("\n测试日线数据读取...")
    test_codes = ['000001', '000002', '600000']
    for code in test_codes:
        price_data = ranker.get_latest_price_data(code)
        if price_data:
            print(f"股票 {code}: 股价 {price_data['close']:.2f}元, 日期 {price_data['date']}")
        else:
            print(f"股票 {code}: 无法获取股价数据")

    # 选择排名类别
    print("\n请选择排名类别:")
    print("1. 综合财务与估值排名")
    print("2. 盈利能力排名")
    print("3. 成长能力排名")
    print("4. 估值水平排名")
    print("5. 所有类别排名")
    print("6. 测试模式（少量股票）")

    choice = input("\n请选择 (1-6): ").strip()

    test_mode = (choice == '6')
    if test_mode:
        choice = '1'  # 测试模式下默认使用综合排名

    years = 1 if test_mode else int(input("使用最近几年的数据? (默认1): ") or "1")
    top_n = 20 if test_mode else int(input("显示前多少名? (默认50): ") or "50")

    categories_to_run = []

    if choice == '1':
        categories_to_run = ['综合']
    elif choice == '2':
        categories_to_run = ['盈利能力']
    elif choice == '3':
        categories_to_run = ['成长能力']
    elif choice == '4':
        categories_to_run = ['估值']
    elif choice == '5':
        categories_to_run = ['综合', '盈利能力', '成长能力', '估值']
    else:
        print("无效选择")
        return

    # 运行排名
    results = {}

    for category in categories_to_run:
        print(f"\n正在计算{category}排名...")
        df = ranker.rank_by_category(years=years, top_n=top_n, category=category, test_mode=test_mode)

        if not df.empty:
            results[category] = df
            print(f"\n{category}排名前{min(20, len(df))}名:")
            print("=" * 120)
            print(df.head(20).to_string(index=False))
            print(f"\n共找到 {len(df)} 只股票")
        else:
            print(f"没有找到{category}排名数据")

    # 导出结果
    if results:
        export = input("\n是否导出排名结果? (y/n): ").strip().lower()
        if export == 'y':
            filename = input("请输入导出文件名 (默认: 股票综合排名.xlsx): ") or "股票综合排名.xlsx"
            ranker.export_ranking_to_excel(results, filename)


def quick_ranking():
    """快速排名示例"""
    CW_DIR = "d:/new_hxzq_hc/vipdoc/cw/"
    DAY_DATA_DIR = "d:/new_hxzq_hc/vipdoc/"
    FIELD_FILE = "专业财务数据字段说明.txt"

    ranker = TDXFinancialValuationRanker(CW_DIR, DAY_DATA_DIR, FIELD_FILE)

    print("测试日线数据读取...")
    test_code = '000001'
    price_data = ranker.get_latest_price_data(test_code)
    if price_data:
        print(f"测试成功: 股票 {test_code}, 股价 {price_data['close']:.2f}元")
    else:
        print(f"测试失败: 无法获取股票 {test_code} 的股价数据")
        print("请检查日线数据文件路径是否正确")
        return

    print("\n正在计算综合财务与估值排名...")
    df_comprehensive = ranker.rank_by_category(years=1, top_n=30, category='综合', test_mode=True)

    if not df_comprehensive.empty:
        print("\n" + "=" * 120)
        print("综合财务与估值排名前20名:")
        print("=" * 120)
        print(df_comprehensive.head(20).to_string(index=False))
    else:
        print("没有找到排名数据")
        return

    print("\n" + "=" * 120)
    print("估值水平排名前20名:")
    print("=" * 120)
    df_valuation = ranker.rank_by_category(years=1, top_n=20, category='估值', test_mode=True)
    if not df_valuation.empty:
        print(df_valuation.head(20).to_string(index=False))
    else:
        print("没有找到估值排名数据")

    # 导出完整结果
    results = {
        '综合排名': df_comprehensive,
        '估值排名': df_valuation
    }
    ranker.export_ranking_to_excel(results, "股票估值排名.xlsx")


def analyze_single_stock():
    """分析单只股票"""
    CW_DIR = "d:/new_hxzq_hc/vipdoc/cw/"
    DAY_DATA_DIR = "d:/new_hxzq_hc/vipdoc/"
    FIELD_FILE = "专业财务数据字段说明.txt"

    ranker = TDXFinancialValuationRanker(CW_DIR, DAY_DATA_DIR, FIELD_FILE)

    stock_code = input("请输入股票代码: ").strip()

    # 获取最新财务数据
    files = ranker.get_latest_year_files(1)
    if files:
        latest_file = files[-1]
        stocks_data = ranker.parse_all_stocks_in_file(latest_file, list(range(1, 300)), max_stocks=10)

        if stock_code in stocks_data:
            financial_data = stocks_data[stock_code]

            # 获取股价数据
            price_data = ranker.get_latest_price_data(stock_code)

            if price_data:
                # 计算估值指标
                valuation_metrics = ranker.calculate_valuation_metrics(financial_data, price_data)

                print(f"\n股票 {stock_code} 分析报告")
                print("=" * 60)
                print(f"当前股价: {price_data['close']:.2f}元")
                print(f"日期: {price_data['date']}")
                print("\n财务指标:")
                print(f"  净资产收益率(ROE): {financial_data.get(197, 0):.2f}%")
                print(f"  净利润: {financial_data.get(95, 0) / 1e8:.2f}亿元")
                print(f"  营业收入: {financial_data.get(74, 0) / 1e8:.2f}亿元")
                print(f"  营收增长率: {financial_data.get(183, 0):.2f}%")
                print(f"  资产负债率: {financial_data.get(210, 0):.2f}%")

                print("\n估值指标:")
                print(f"  市盈率(PE): {valuation_metrics.get('pe', 0):.2f}倍")
                print(f"  市净率(PB): {valuation_metrics.get('pb', 0):.2f}倍")
                print(f"  市销率(PS): {valuation_metrics.get('ps', 0):.2f}倍")
                print(f"  PEG: {valuation_metrics.get('peg', 0):.2f}")
                print(f"  股息率: {valuation_metrics.get('dividend_yield', 0):.2f}%")
                print(f"  总市值: {valuation_metrics.get('market_cap', 0) / 1e8:.2f}亿元")
            else:
                print(f"无法获取股票 {stock_code} 的股价数据")
        else:
            print(f"未找到股票 {stock_code} 的财务数据")


if __name__ == '__main__':
    print("通达信财务与估值综合排序系统")
    print("=" * 60)

    print("请选择功能:")
    print("1. 综合排名")
    print("2. 快速排名示例（测试模式）")
    print("3. 单只股票分析")

    mode = input("\n选择 (1-3): ").strip()

    if mode == '1':
        main()
    elif mode == '2':
        quick_ranking()
    elif mode == '3':
        analyze_single_stock()
    else:
        print("无效选择")