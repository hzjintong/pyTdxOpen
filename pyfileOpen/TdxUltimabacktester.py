import os
import struct
import pandas as pd
import numpy as np
from datetime import datetime
import talib
import warnings
import re

warnings.filterwarnings('ignore')


# ==========================================
# 1. 财务解析引擎 (保持稳定)
# ==========================================
class TdxFinancialReader:
    def __init__(self):
        self.header_format = "<3h1H3L"
        self.item_format = "<6s1c1L"
        self.data_format = "<584f"
        self.header_size = struct.calcsize(self.header_format)
        self.item_size = struct.calcsize(self.item_format)
        self.data_size = struct.calcsize(self.data_format)

    def read_all_stocks(self, file_path):
        results = []
        if not os.path.exists(file_path): return pd.DataFrame()
        try:
            with open(file_path, 'rb') as f:
                f.read(self.header_size)
                while True:
                    item_data = f.read(self.item_size)
                    if len(item_data) < self.item_size: break
                    item_fields = struct.unpack(self.item_format, item_data)
                    stock_code = item_fields[0].decode('gbk', errors='ignore').strip('\x00').strip()
                    data_bytes = f.read(self.data_size)
                    if len(data_bytes) < self.data_size: break
                    f_vals = struct.unpack(self.data_format, data_bytes)
                    # 197:ROE, 183:营收增长, 210:资产负债率
                    results.append({'code': stock_code, 'roe': f_vals[196], 'growth': f_vals[182], 'debt': f_vals[209]})
        except Exception as e:
            print(f"财务读取错误: {e}")
        return pd.DataFrame(results)


# ==========================================
# 2. 技术分析引擎
# ==========================================
class TechnicalEngine:
    @staticmethod
    def get_signals(df_day):
        res = {'bull': False, 'vol': False, 'exit': False, 'valid_data': False, 'data_len': 0}
        if df_day is None or len(df_day) < 35:  # 留出MA20所需的计算空间
            if df_day is not None: res['data_len'] = len(df_day)
            return res

        close = df_day['close'].values.astype(float)
        volume = df_day['volume'].values.astype(float)

        try:
            ma5 = talib.SMA(close, timeperiod=5)
            ma10 = talib.SMA(close, timeperiod=10)
            ma20 = talib.SMA(close, timeperiod=20)
            ma60 = talib.SMA(close, timeperiod=60)
            vma5 = talib.SMA(volume, timeperiod=5)
            vma10 = talib.SMA(volume, timeperiod=10)

            res['bull'] = (close[-1] > ma5[-1] > ma10[-1] > ma20[-1] > ma60[-1])
            res['vol'] = (volume[-1] > vma5[-1] * 1.5)
            res['exit'] = (close[-1] < ma20[-1]) or (close[-1] < ma60[-1])
            res['valid_data'] = True
            res['data_len'] = len(df_day)
        except Exception as e:
            print(e)
            pass
        return res


# ==========================================
# 3. 整合回测系统 (修正日线定位逻辑)
# ==========================================
class TdxUltimateBacktester:
    def __init__(self, cw_dir, day_dir, sector_file):
        self.cw_dir = cw_dir
        self.day_dir = day_dir  # 对应 D:\new_hxzq_hc\vipdoc
        self.sector_file = sector_file
        self.reader = TdxFinancialReader()
        self.sector_df = self._load_sector_data()
        self.results_log = []

    def _load_sector_data(self):
        try:
            df = pd.read_csv(self.sector_file, sep=',', encoding='gbk', header=None,
                             names=['sid', 'sector_name', 'code', 'name'], dtype={'code': str})
            df['code'] = df['code'].str.zfill(6)
            return df
        except:
            return pd.DataFrame()

    @staticmethod
    def get_market_from_code(stock_code):
        """根据股票代码判断市场"""
        if stock_code.startswith('6') or stock_code.startswith('90') or stock_code.startswith('99'):
            return 'sh'
        elif stock_code.startswith('0') or stock_code.startswith('3') or stock_code.startswith('2'):
            return 'sz'
        elif stock_code.startswith('4') or stock_code.startswith('8') or stock_code.startswith('92'):
            return 'bj'
        else:
            return 'ds'

    def get_day_file_path(self, stock_code):
        """
        参考 Tdx_CW_GZ_dsfix.py 逻辑定位日线文件
        """
        """获取日线数据文件路径"""
        # 判断市场
        market = self.get_market_from_code(stock_code)
        # market_prefix = ''
        if market == 'sh':
            market_prefix = 'SH'
        elif market == 'sz':
            market_prefix = 'SZ'
        elif market == 'bj':
            market_prefix = 'BJ'
        else:
            market_prefix = 'DS'

        # 拼接完整路径: 根目录\sh\lday\sh600000.day
        file_name = f"{market_prefix}{stock_code}.day"
        file_path = os.path.join(self.day_dir, market, 'lday', file_name)

        # 如果不存在，尝试其他可能的路径
        if not os.path.exists(file_path):
            # 尝试另一种命名方式
            alt_file_path = os.path.join(self.day_dir, market, 'lday', f"{stock_code}.day")
            if os.path.exists(alt_file_path):
                return alt_file_path

        return file_path

    def _get_history_day_data(self, code, target_date):
        file_path = self.get_day_file_path(code)
        print(file_path)
        if not os.path.exists(file_path):
            print(f"警告: 股票 {code} 的日线数据文件不存在: {file_path}")
            return None

        # 2. 讀取並解析通達信二進制日線數據
        records = []
        target_str = target_date.strftime("%Y%m%d")
        try:
            with open(file_path, 'rb') as f:
                f.seek(0, 2)
                f_size = f.tell()
                # 至少读120个交易日以确保计算指标
                f.seek(max(0, f_size - 32 * 9000))
                while True:
                    data = f.read(32)
                    if len(data) < 32: break
                    item = struct.unpack('5If2I', data)
                    # 只取回测日期之前的数据
                    # print(f'读取：{item[0]}， 比较：{target_str}' )
                    if str(item[0]) < target_str:
                        records.append({'close': item[4] / 100.0, 'volume': item[6]})
        except Exception as e:
            print(f'解析二进制数据文件出错：{e}')
            return None

        return pd.DataFrame(records)

    def _match_cw_file(self, dt):
        if dt.month <= 4:
            y, m = dt.year - 1, "0930"
        elif dt.month <= 8:
            y, m = dt.year, "0331"
        elif dt.month <= 10:
            y, m = dt.year, "0630"
        else:
            y, m = dt.year, "0930"
        path = os.path.join(self.cw_dir, f"gpcw{y}{m}.dat")
        return path if os.path.exists(path) else None

    def run(self, start_year=2020, end_year=2024):
        print(f">>> 启动终极回测系统 (定位日线模式)...")
        for year in range(start_year, end_year + 1):
            for month in range(1, 13):
                curr_dt = datetime(year, month, 1)
                if curr_dt > datetime.now(): break

                cw_file = self._match_cw_file(curr_dt)
                if not cw_file: continue

                cw_df = self.reader.read_all_stocks(cw_file)
                if cw_df.empty: continue

                df = pd.merge(cw_df, self.sector_df, on='code')
                if df.empty: continue

                # 二级行业内部评分
                df['roe_rank'] = df.groupby('sector_name')['roe'].rank(pct=True)
                df['growth_rank'] = df.groupby('sector_name')['growth'].rank(pct=True)
                df['total_score'] = (df['roe_rank'] + df['growth_rank']) / 2
                df['sector_rank'] = df.groupby('sector_name')['total_score'].rank(ascending=False, method='first')

                # 取前3名
                top_3 = df[df['sector_rank'] <= 3]

                month_hits = 0
                for _, row in top_3.iterrows():
                    day_data = self._get_history_day_data(row['code'], curr_dt)
                    sig = TechnicalEngine.get_signals(day_data)

                    # 只有当数据有效且满足技术信号（或用于记录调试）时才存入
                    if sig['valid_data']:
                        if sig['bull'] or sig['vol']:
                            month_hits += 1
                            industry_size = len(df[df['sector_name'] == row['sector_name']])
                            exit_a = "财务预警" if row['sector_rank'] > (industry_size * 0.2) else "财务持仓"
                            exit_b = "技术破位" if sig['exit'] else "技术持仓"

                            self.results_log.append({
                                '日期': curr_dt.strftime("%Y-%m"),
                                '代码': row['code'],
                                '名称': row['name'],
                                '行业': row['sector_name'],
                                '排名': int(row['sector_rank']),
                                '技术信号': "均线多头" if sig['bull'] else "放量突破",
                                '策略A_财务': exit_a,
                                '策略B_技术': exit_b
                            })

                print(f"进度: {year}-{month:02d} | 财务入围: {len(top_3)} | 最终选中: {month_hits}")

        # 导出
        if self.results_log:
            output = "Industry_Backtest_Final_Fixed.csv"
            pd.DataFrame(self.results_log).to_csv(output, index=False, encoding='utf_8_sig')
            print(f"\n[任务成功] 结果已导出至: {output}，共 {len(self.results_log)} 条数据。")
        else:
            print("\n[警告] 依然没有选中数据。请检查 DAY_DATA 路径是否指向了 vipdoc 文件夹。")


if __name__ == "__main__":
    # --- 请务必确认此路径下包含 sh 和 sz 文件夹 ---
    CW_DATA = r"D:\new_hxzq_hc\vipdoc\cw"
    DAY_DATA = r"D:\new_hxzq_hc\vipdoc"
    SECTOR_FILE = "二级行业板块.txt"

    tester = TdxUltimateBacktester(CW_DATA, DAY_DATA, SECTOR_FILE)
    tester.run(start_year=2000, end_year=2020)