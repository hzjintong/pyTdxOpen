import sqlite3
import pandas as pd
import numpy as np


class IndustryFactorRanker:
    """
    量化系统多因子行业中性化排名与评估模组
    支持：截面因子提取、行业中性化标准化/排名、一票否决机制、9级分类评价、Excel报表输出及写回DB
    """

    def __init__(self, db_path="E:/tdx_financial.db"):
        self.db_path = db_path

    def _get_db_connection(self):
        return sqlite3.connect(self.db_path)

    def load_clean_dataset(self, report_date: int) -> pd.DataFrame:
        """
        根据指定报告期加载截面财务数据、行业数据及退市隔离信息
        """
        conn = self._get_db_connection()

        # 1. 查询行业底座与退市隔离表
        industry_query = """
        SELECT stock_code, industry_code, industry_name, stock_name, is_active 
        FROM dataset_industry_sectors 
        WHERE is_active = 1
        """
        df_ind = pd.read_sql_query(industry_query, conn)

        # 2. 查询指定报告期的财务主表关键因子 (列名通过字典映射)
        # field_6: 净资产收益率ROE
        # field_184/183: 净利润增长率 / 营业收入增长率
        # field_219/7: 每股经营现金流量
        # field_210: 资产负债率
        # field_362: 通达信财务总评分 (作为对比参考)
        fin_query = f"""
        SELECT 
            stock_code,
            report_date,
            field_6   AS roe,
            field_184 AS profit_yoy,
            field_183 AS revenue_yoy,
            field_219 AS ocf_ps,
            field_210 AS debt_to_asset,
            field_362 AS tdx_score
        FROM financial_data 
        WHERE report_date = {report_date}
        """
        df_fin = pd.read_sql_query(fin_query, conn)
        conn.close()

        # 合并行业与财务数据
        df_merged = pd.merge(df_ind, df_fin, on="stock_code", how="inner")
        return df_merged

    @staticmethod
    def calc_industry_neutralization(df: pd.DataFrame, factor_cols: list) -> pd.DataFrame:
        """
        行业中性化处理：在每个二级行业内部计算因子的 Z-Score 与 percentile rank
        """
        df_scored = df.copy()

        for col in factor_cols:
            # 缩尾处理 (Winsorize 1% ~ 99%)，消除极值干扰
            low = df_scored[col].quantile(0.01)
            high = df_scored[col].quantile(0.99)
            df_scored[col] = df_scored[col].clip(low, high)

            # 行业内标准化 (Z-Score) 与百分位排名
            group = df_scored.groupby('industry_code')[col]

            # 分组计算均值与标准差
            mean = group.transform('mean')
            std = group.transform('std').replace(0, 1e-6)  # 避免除零

            # 行业中性化 Z-Score 因子
            df_scored[f'{col}_zscore'] = (df_scored[col] - mean) / std
            # 行业内部截面 Rank (0-1 之间)
            df_scored[f'{col}_rank'] = group.rank(pct=True)

        return df_scored

    def calculate_scores_and_ratings(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        因子加权打分、一票否决判定与 A+ ~ C- 九级分类划分
        """
        # 定义关键因子权重配置
        weights = {
            'roe_zscore': 0.35,  # 获利能力
            'profit_yoy_zscore': 0.25,  # 成长能力 (净利润增长)
            'revenue_yoy_zscore': 0.15,  # 成长能力 (营收增长)
            'ocf_ps_zscore': 0.25  # 现金流质量
        }

        # 计算综合中性化得分 (行业内加权 Z-Score)
        df['composite_score'] = 0.0
        for factor, weight in weights.items():
            df['composite_score'] += df[factor] * weight

        # --- 一票否决机制 (Veto Rules) ---
        # 规则 1: 经营性现金流为负数 (现金流枯竭)
        # 规则 2: 资产负债率 > 85% (高债务风险)
        # 规则 3: 净利润同比下滑超过 50%
        veto_condition = (
                (df['ocf_ps'] < 0) |
                (df['debt_to_asset'] > 85.0) |
                (df['profit_yoy'] < -50.0)
        )
        df['is_vetoed'] = veto_condition

        # 针对通过一票否决筛查的股票进行行业内百分位分组 (0 - 100%)
        df['score_pct'] = df.groupby('industry_code')['composite_score'].rank(pct=True)

        # 映射为 9 级评价 (A+, A, A-, B+, B, B-, C+, C, C-)
        def assign_rating(row):
            if row['is_vetoed']:
                return 'C-'  # 被一票否决直接降至最低级 C-

            pct = row['score_pct']
            if pct >= 0.88:
                return 'A+'
            elif pct >= 0.76:
                return 'A'
            elif pct >= 0.64:
                return 'A-'
            elif pct >= 0.52:
                return 'B+'
            elif pct >= 0.40:
                return 'B'
            elif pct >= 0.28:
                return 'B-'
            elif pct >= 0.16:
                return 'C+'
            elif pct >= 0.08:
                return 'C'
            else:
                return 'C-'

        df['composite_rating'] = df.apply(assign_rating, axis=1)
        return df

    def export_top5_excel(self, df: pd.DataFrame, report_date: int, output_file: str):
        """
        筛选各行业前 5 名股票并导出为格式化的 Excel 报表
        """
        # 行业内按综合得分降序排序，取 Top 5
        top5_df = (
            df.sort_values(by=['industry_code', 'composite_score'], ascending=[True, False])
            .groupby('industry_code')
            .head(5)
            .copy()
        )

        # 选定与重命名输出列
        export_columns = {
            'stock_code': '股票代码',
            'stock_name': '股票名称',
            'industry_code': '行业板块代码',
            'industry_name': '所属行业名称',
            'composite_score': '综合得分',
            'composite_rating': '综合评价等级',
            'roe': '净资产收益率(%)',
            'profit_yoy': '净利润同比增长率(%)',
            'revenue_yoy': '营业收入同比增长率(%)',
            'ocf_ps': '每股经营现金流(元)',
            'tdx_score': '通达信财务总评分(field_362)'
        }

        result_df = top5_df[list(export_columns.keys())].rename(columns=export_columns)

        # 输出为 Excel 文件
        with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
            result_df.to_excel(writer, sheet_name=f'Top5_{report_date}', index=False)

        print(f"✅ Excel 行业 Top5 报告已成功导出至: {output_file}")

    def save_scores_to_db(self, df: pd.DataFrame):
        """
        将计算出的评分和等级写回 SQLite 数据库表 financial_data 中
        （通过新增列/更新字段实现，便于与 field_362 通达信评分对比）
        """
        conn = self._get_db_connection()
        cursor = conn.cursor()

        # 1. 检查并动态新增评价字段 (若不存在)
        cursor.execute("PRAGMA table_info(financial_data)")
        existing_cols = [col[1] for col in cursor.fetchall()]

        if 'custom_score' not in existing_cols:
            cursor.execute("ALTER TABLE financial_data ADD COLUMN custom_score REAL;")
        if 'custom_rating' not in existing_cols:
            cursor.execute("ALTER TABLE financial_data ADD COLUMN custom_rating TEXT;")

        # 2. 批量更新数据库记录
        update_data = [
            (row['composite_score'], row['composite_rating'], row['stock_code'], row['report_date'])
            for _, row in df.iterrows()
        ]

        update_sql = """
        UPDATE financial_data 
        SET custom_score = ?, custom_rating = ?
        WHERE stock_code = ? AND report_date = ?;
        """
        cursor.executemany(update_sql, update_data)
        conn.commit()
        conn.close()
        print("✅ 自研综合得分与九级评级已成功写回数据库 financial_data 表。")


# ==========================================
# 自动化运行入口
# ==========================================
if __name__ == "__main__":
    # 设定分析的目标财报周期 (如 2024年年报)
    TARGET_REPORT_DATE = 20260630
    OUTPUT_EXCEL_PATH = f"E:/分析日志/行业Top5财务评分分析_{TARGET_REPORT_DATE}.xlsx"

    ranker = IndustryFactorRanker(db_path="E:/tdx_financial.db")

    print("1. 正在读取截面财务与行业数据...")
    raw_df = ranker.load_clean_dataset(report_date=TARGET_REPORT_DATE)

    print("2. 执行二级行业内因子标准化与中性化...")
    neutral_factors = ['roe', 'profit_yoy', 'revenue_yoy', 'ocf_ps']
    df_neutral = ranker.calc_industry_neutralization(raw_df, factor_cols=neutral_factors)

    print("3. 计算综合加权得分、执行一票否决并划分 9 级评价...")
    df_final = ranker.calculate_scores_and_ratings(df_neutral)

    print("4. 导出各行业前 5 名至 Excel...")
    ranker.export_top5_excel(df_final, report_date=TARGET_REPORT_DATE, output_file=OUTPUT_EXCEL_PATH)

    print("5. 将评分与等级落盘回写至数据库...")
    ranker.save_scores_to_db(df_final)

    print("🏁 全部打分与评价重构流程顺利完成！")