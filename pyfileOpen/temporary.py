import pandas as pd
import numpy as np
from datetime import datetime
import os
from Tdx_CW_GZ_dsfix import TDXFinancialValuationRanker

# 假设原有的 TDXFinancialValuationRanker 类已经存在
class TDXBacktester(TDXFinancialValuationRanker):
    def __init__(self, cw_dir, day_data_dir, sector_file):
        super().__init__(cw_dir, day_data_dir, sector_file=sector_file)
        self.sector_df = self.load_sector_data(sector_file)

    def load_sector_data(self, sector_file):
        """加载二级行业分类文件"""
        # 通达信格式通常为: 行业代码,行业名称,股票代码,股票名称
        try:
            df = pd.read_csv(sector_file, sep=',', encoding='gb18030', header=None,
                             names=['sector_code', 'sector_name', 'code', 'name'],
                             dtype={'code': str})
            return df
        except Exception as e:
            print(f"读取行业文件失败: {e}")
            return pd.DataFrame()

    def calculate_industry_scores(self, df_all_stocks):
        """
        核心逻辑：按二级行业进行财务评分
        """
        if df_all_stocks.empty:
            return df_all_stocks

        # 合并行业信息
        df = pd.merge(df_all_stocks, self.sector_df[['code', 'sector_name']], on='code', how='left')

        # 定义需要评分的财务指标 (例如 ROE, 净利增长, PE)
        # 这里仅以ROE(197字段)为例，您可以扩展更多
        metrics = {'roe': 197, 'net_profit_growth': 183}

        for name, field_id in metrics.items():
            # 计算行业内排名百分位 (0-1之间，1代表行业最强)
            df[f'{name}_score'] = df.groupby('sector_name')[field_id].rank(pct=True)

            # 填充缺失值（如果没有行业分类的给中位数评分）
            df[f'{name}_score'] = df[f'{name}_score'].fillna(0.5)

        # 综合财务得分 = 各项指标得分的平均
        score_cols = [f'{name}_score' for name in metrics.keys()]
        df['total_fin_score'] = df[score_cols].mean(axis=1)

        return df

    def run_backtest_export(self, report_dates):
        """
        回测历史数据并导出
        Args:
            report_dates: 列表，例如 ['20240331', '20240630', '20240930']
        """
        all_results = []

        for r_date in report_dates:
            print(f"正在模拟回测日期: {r_date} ...")
            # 1. 加载该日期的财务快照 (此处需调用您原有的读取.dat文件的逻辑)
            snap_df = self.get_financial_snapshot(r_date)

            # 2. 计算行业评分
            # rated_df = self.calculate_industry_scores(snap_df)

            # 3. 模拟选股：每个二级行业选出前2名，或者全市场财务总分前50
            # top_stocks = rated_df.nlargest(50, 'total_fin_score')
            # top_stocks['backtest_date'] = r_date
            # all_results.append(top_stocks)

        # 导出结果
        # final_df = pd.concat(all_results)
        # final_df.to_csv("historical_backtest_results.csv", index=False, encoding='utf_8_sig')
        # print("回测结果已导出至 historical_backtest_results.csv")

