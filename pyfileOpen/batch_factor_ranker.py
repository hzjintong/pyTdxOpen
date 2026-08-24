import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime


class BatchIndustryFactorRanker:
    """
    量化系统多周期全量财务打分、评级落盘与变动审计模组
    支持：
    1. 自动读取全量离散报告期并逐周期截面打分
    2. 维护财务评级历史快照表 (financial_custom_ratings)
    3. 新旧计算差异对比，生成 Excel 变更审计报告
    4. 回写最新结果至 financial_data 主表，供多周期表型稳定性分析
    """

    def __init__(self, db_path="E:/tdx_financial.db"):
        self.db_path = db_path
        self._init_rating_tables()

    def _get_db_connection(self):
        return sqlite3.connect(self.db_path)

    def _init_rating_tables(self):
        """
        初始化评级相关表结构：
        1. 在 financial_data 中补齐 custom_score, custom_rating 字段
        2. 创建历史评级快照表 financial_custom_ratings
        """
        conn = self._get_db_connection()
        cursor = conn.cursor()

        # 1. 检查并给主表补充字段
        cursor.execute("PRAGMA table_info(financial_data)")
        existing_cols = [col[1] for col in cursor.fetchall()]
        if 'custom_score' not in existing_cols:
            cursor.execute("ALTER TABLE financial_data ADD COLUMN custom_score REAL;")
        if 'custom_rating' not in existing_cols:
            cursor.execute("ALTER TABLE financial_data ADD COLUMN custom_rating TEXT;")

        # 2. 创建评级快照历史表 (支持历史溯源)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS financial_custom_ratings (
            stock_code TEXT NOT NULL,
            report_date INTEGER NOT NULL,
            custom_score REAL,
            custom_rating TEXT,
            is_vetoed INTEGER,
            calc_timestamp TEXT,
            PRIMARY KEY (stock_code, report_date)
        );
        """)
        conn.commit()
        conn.close()

    def get_all_report_dates(self) -> list:
        """从数据库中提取所有已有数据的离散报告期列表（升序排列）"""
        conn = self._get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT report_date FROM financial_data ORDER BY report_date ASC;")
        dates = [row[0] for row in cursor.fetchall() if row[0] is not None]
        conn.close()
        return dates

    def load_clean_dataset(self, report_date: int) -> pd.DataFrame:
        """加载单个截面报告期的财务与行业数据"""
        conn = self._get_db_connection()

        # 获取行业数据（过滤退市股）
        industry_query = """
        SELECT stock_code, industry_code, industry_name, stock_name, is_active 
        FROM dataset_industry_sectors 
        WHERE is_active = 1
        """
        df_ind = pd.read_sql_query(industry_query, conn)

        # 获取指定报告期的关键财务指标以及上一次记录的评分评级
        fin_query = f"""
        SELECT 
            stock_code,
            report_date,
            field_6   AS roe,
            field_184 AS profit_yoy,
            field_183 AS revenue_yoy,
            field_219 AS ocf_ps,
            field_210 AS debt_to_asset,
            field_362 AS tdx_score,
            custom_score  AS old_custom_score,
            custom_rating AS old_custom_rating
        FROM financial_data 
        WHERE report_date = {report_date}
        """
        df_fin = pd.read_sql_query(fin_query, conn)
        conn.close()

        return pd.merge(df_ind, df_fin, on="stock_code", how="inner")

    @staticmethod
    def calc_industry_neutralization(df: pd.DataFrame, factor_cols: list) -> pd.DataFrame:
        """二级行业内标准化 (Z-Score) 与排名"""
        df_scored = df.copy()
        for col in factor_cols:
            # 缩尾处理 1%~99%
            low = df_scored[col].quantile(0.01)
            high = df_scored[col].quantile(0.99)
            df_scored[col] = df_scored[col].clip(low, high)

            group = df_scored.groupby('industry_code')[col]
            mean = group.transform('mean')
            std = group.transform('std').replace(0, 1e-6)

            df_scored[f'{col}_zscore'] = (df_scored[col] - mean) / std
        return df_scored

    def calculate_scores_and_ratings(self, df: pd.DataFrame) -> pd.DataFrame:
        """计算综合得分、一票否决与 9 级评价"""
        weights = {
            'roe_zscore': 0.35,
            'profit_yoy_zscore': 0.25,
            'revenue_yoy_zscore': 0.15,
            'ocf_ps_zscore': 0.25
        }

        df['composite_score'] = 0.0
        for factor, weight in weights.items():
            df['composite_score'] += df[factor] * weight

        # 一票否决机制
        veto_condition = (
                (df['ocf_ps'] < 0) |
                (df['debt_to_asset'] > 85.0) |
                (df['profit_yoy'] < -50.0)
        )
        df['is_vetoed'] = veto_condition.astype(int)

        # 行业内部百分位计算
        df['score_pct'] = df.groupby('industry_code')['composite_score'].rank(pct=True)

        def assign_rating(row):
            if row['is_vetoed'] == 1:
                return 'C-'
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

    def run_batch_process_and_audit(self, audit_excel_path: str):
        """
        批量处理核心函数：
        1. 遍历所有历史报告期进行打分与评级
        2. 捕获变动记录（原评分 vs 新评分）
        3. 输出差异审计报告 Excel
        4. 回写数据库
        """
        report_dates = self.get_all_report_dates()
        print(f"🔍 检索到财务数据库中共包含 {len(report_dates)} 个报告期: {report_dates}")

        all_diff_records = []
        calc_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        conn = self._get_db_connection()
        cursor = conn.cursor()

        neutral_factors = ['roe', 'profit_yoy', 'revenue_yoy', 'ocf_ps']

        for date in report_dates:
            print(f"⚡ 正在处理报告期: {date} ...")
            raw_df = self.load_clean_dataset(report_date=date)
            if raw_df.empty:
                continue

            df_neutral = self.calc_industry_neutralization(raw_df, factor_cols=neutral_factors)
            df_final = self.calculate_scores_and_ratings(df_neutral)

            # --- 变动差异比对逻辑 ---
            # 过滤出存在旧记录且 (得分差值 > 0.001 或 评级发生改变) 的记录
            df_final['score_diff'] = df_final['composite_score'] - df_final['old_custom_score']

            # 判断是否有明显变动
            has_old_data = df_final['old_custom_rating'].notna() & (df_final['old_custom_rating'] != '')
            rating_changed = df_final['composite_rating'] != df_final['old_custom_rating']
            score_changed = df_final['score_diff'].abs() > 0.001

            diff_mask = has_old_data & (rating_changed | score_changed)
            diff_df = df_final[diff_mask].copy()

            if not diff_df.empty:
                all_diff_records.append(diff_df)

            # --- 数据库持久化落盘 ---
            # 1. 更新主表 financial_data
            update_data_main = [
                (row['composite_score'], row['composite_rating'], row['stock_code'], row['report_date'])
                for _, row in df_final.iterrows()
            ]
            cursor.executemany("""
                UPDATE financial_data 
                SET custom_score = ?, custom_rating = ?
                WHERE stock_code = ? AND report_date = ?;
            """, update_data_main)

            # 2. 插入/替换 历史快照表 financial_custom_ratings
            snapshot_data = [
                (row['stock_code'], row['report_date'], row['composite_score'], row['composite_rating'],
                 row['is_vetoed'], calc_timestamp)
                for _, row in df_final.iterrows()
            ]
            cursor.executemany("""
                INSERT OR REPLACE INTO financial_custom_ratings 
                (stock_code, report_date, custom_score, custom_rating, is_vetoed, calc_timestamp)
                VALUES (?, ?, ?, ?, ?, ?);
            """, snapshot_data)

            conn.commit()

        conn.close()

        # --- 生成 Excel 审计报告 ---
        if all_diff_records:
            total_diff_df = pd.concat(all_diff_records, ignore_index=True)

            audit_columns = {
                'report_date': '报告期',
                'stock_code': '股票代码',
                'stock_name': '股票名称',
                'industry_name': '所属行业',
                'old_custom_score': '原综合得分',
                'composite_score': '本次综合得分',
                'score_diff': '得分变动幅度',
                'old_custom_rating': '原评价等级',
                'composite_rating': '本次评价等级',
                'is_vetoed': '是否触发一票否决',
                'roe': '净资产收益率(%)',
                'profit_yoy': '净利润同比增长率(%)',
                'ocf_ps': '每股经营现金流(元)'
            }

            audit_result = total_diff_df[list(audit_columns.keys())].rename(columns=audit_columns)

            with pd.ExcelWriter(audit_excel_path, engine='openpyxl') as writer:
                audit_result.to_excel(writer, sheet_name='评级差异审计报告', index=False)
                # 附带汇总 Sheet
                summary_df = pd.DataFrame([{
                    '计算时间': calc_timestamp,
                    '处理报告期总数': len(report_dates),
                    '发生变更记录总数': len(audit_result),
                    '影响股票总只数': audit_result['股票代码'].nunique()
                }])
                summary_df.to_excel(writer, sheet_name='审计汇总概览', index=False)

            print(f"\n⚠️ 检测到历史数据修正导致的评级变动！差异审计报告已生成: {audit_excel_path}")
            print(f"📊 累计包含 {len(audit_result)} 条变更记录，涉及 {audit_result['股票代码'].nunique()} 只股票。")
        else:
            print("\n✅ 全量历史数据比对完成，无评级/得分差异记录（历史评级保持完全一致）。")

        print("🏁 全量历史周期打分与持久化落盘全部顺利完成！")


# ==========================================
# 自动化运行入口
# ==========================================
if __name__ == "__main__":
    TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
    AUDIT_EXCEL_PATH = f"E:/分析日志/财务评级历史变更审计报告_{TIMESTAMP}.xlsx"

    batch_ranker = BatchIndustryFactorRanker(db_path="E:/tdx_financial.db")
    batch_ranker.run_batch_process_and_audit(audit_excel_path=AUDIT_EXCEL_PATH)