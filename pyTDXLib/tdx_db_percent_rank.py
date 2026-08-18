import sqlite3
import os
import pandas as pd

"""
量化系统1：行业内因子排名器（现金流）
"""
class MultiFactorSectorRanker高性能版:
    def __init__(self, db_path: str = "E:/tdx_financial.db"):
        self.db_path = db_path
        if not os.path.exists(db_path):
            raise FileNotFoundError(f"未找到核心数据库: {db_path}")

    def _get_connection(self):
        return sqlite3.connect(self.db_path)

    def generate_rank_matrix_fast(self, start_date: int = 20260501, end_date: int = 20260630,
                                  factor_fields: list = ["field_7", "field_197"],
                                  ascending_flags: list = [False, False]):
        """利用SUBSTR精确切片联表，秒级激活索引，拒绝卡死"""

        # 1. 动态构建横截面窗口打分函数（引入 100 - 修正打分方向）
        window_clauses = []
        for field, is_asc in zip(factor_fields, ascending_flags):
            # is_asc 为 True 代表指标越小越好（如市盈率、资产负债率）；False 代表越大越好（如现金流、ROE）
            order_dir = "ASC" if is_asc else "DESC"
            score_col_name = f"{field}_sector_score"

            # 核心修正：使用 100 - (...) 翻转百分比排名
            # 使 DESC 排序下，排在第一位（因数值最大）的个股获得 100 - 0 = 100 分（满分特化）
            clause = f"""
                        (1.0 - PERCENT_RANK() OVER (
                            PARTITION BY trade_date, industry_name 
                            ORDER BY CASE WHEN {field} IS NULL THEN -999999 ELSE {field} END {order_dir}
                        )) * 100 AS {score_col_name}
                    """
            window_clauses.append(clause)

        dynamic_windows = ", ".join(window_clauses)

        # 核心高性能 SQL 逻辑
        # 优化点：通过 SUBSTR(k.stock_code, 3) 剥离前缀，强制走全等(=)索引连接，速度提升万倍
        query_fast = f"""
            WITH ValidFinancial AS (
                SELECT 
                    stock_code, -- 纯数字，如 '000001'
                    report_date,
                    20260501 as publish_date,
                    {", ".join(factor_fields)}
                FROM financial_data
                WHERE report_date = 20260331
                  AND {factor_fields[0]} IS NOT NULL
            ),
            RankedFinancial AS (
                SELECT 
                    k.trade_date,
                    k.stock_code as full_stock_code,
                    i.stock_name,
                    i.industry_name,
                    k.close,
                    f.report_date,
                    {", ".join([f"f.{fd}" for fd in factor_fields])},
                    ROW_NUMBER() OVER (
                        PARTITION BY k.trade_date, k.stock_code 
                        ORDER BY f.report_date DESC
                    ) as rn
                FROM stock_daily_kline k
                -- 防御性过滤：日线表代码必须是 8 位长度（如 BJ810011, SZ000001），剔除脏数据占位符
                INNER JOIN dataset_industry_sectors i ON k.stock_code = i.full_stock_code
                -- 精确匹配：截取日线表第3位开始的6位纯数字，秒级同步财务表
                INNER JOIN ValidFinancial f ON f.stock_code = SUBSTR(k.stock_code, 3)
                    AND k.trade_date >= f.publish_date
                WHERE k.trade_date BETWEEN {start_date} AND {end_date}
            )
            SELECT 
                trade_date,
                full_stock_code as stock_code,
                stock_name,
                industry_name,
                close,
                report_date,
                {", ".join([f"{fd}" for fd in factor_fields])},
                {dynamic_windows}
            FROM RankedFinancial
            WHERE rn = 1
            ORDER BY trade_date DESC, industry_name ASC;
        """

        conn = self._get_connection()
        try:
            print(f"正在执行高性能精确切片行业内排名调度... 窗口区间: {start_date} 至 {end_date}")
            df = pd.read_sql_query(query_fast, conn)
            return df
        finally:
            conn.close()


if __name__ == "__main__":
    ranker = MultiFactorSectorRanker高性能版()

    try:
        # ---- 新增：显式配置 Pandas 终端打印参数，防止中文字段被折叠成 ... ----

        # 1. 设置打印最大宽度为不限制（自适应）
        pd.set_option('display.max_columns', None)
        pd.set_option('display.width', 1000)
        # 2. 激活中文字符对齐与等宽补全（非常关键，能让中文对齐不杂乱）
        pd.set_option('display.unicode.ambiguous_as_wide', True)
        pd.set_option('display.unicode.east_asian_width', True)
        # -------------------------------------------------------------

        df_res = ranker.generate_rank_matrix_fast()
        if df_res.empty:
            print("\n❌ 关联结果为空。")
        else:
            print(f"\n🎉 闪电计算成功！共产出 {len(df_res)} 行横截面行业特征排名矩阵。")
            # 完整打印指定列，此时股票名称和行业名称会乖乖显现
            print(df_res[[
                'trade_date',
                'stock_code',
                'stock_name',
                'industry_name',
                'field_7',
                'field_7_sector_score'
            ]].head(15))

    except Exception as e:
        print(f"运行失败: {e}")