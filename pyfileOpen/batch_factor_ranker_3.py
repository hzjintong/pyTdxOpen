import sqlite3
import pandas as pd
# import numpy as np
from datetime import datetime


class BatchIndustryFactorRanker:
    """
    量化系统多周期全量财务打分、评级落盘与变动审计模组 (V3.3 修正版)
    修正说明：
    - 以 financial_data 主表当前的 custom_score/custom_rating 为基准
    - 更新时使用原始股票代码（不补零），避免更新失败
    - 保留标准化代码用于显示和分组
    """

    def __init__(self, db_path="E:/tdx_financial.db"):
        self.db_path = db_path
        self._init_rating_tables()

    def _get_db_connection(self):
        return sqlite3.connect(self.db_path)

    def _init_rating_tables(self):
        """初始化主表扩展字段与历史快照表"""
        conn = self._get_db_connection()
        cursor = conn.cursor()

        cursor.execute("PRAGMA table_info(financial_data)")
        existing_cols = [col[1] for col in cursor.fetchall()]
        if 'custom_score' not in existing_cols:
            cursor.execute("ALTER TABLE financial_data ADD COLUMN custom_score REAL;")
        if 'custom_rating' not in existing_cols:
            cursor.execute("ALTER TABLE financial_data ADD COLUMN custom_rating TEXT;")

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
        conn = self._get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT report_date FROM financial_data ORDER BY report_date ASC;")
        dates = [row[0] for row in cursor.fetchall() if row[0] is not None]
        conn.close()
        return dates

    def load_clean_dataset_with_current_baseline(self, report_date: int) -> pd.DataFrame:
        """
        读取数据，同时获取主表当前的 custom_score/custom_rating 作为基准，
        并保留原始股票代码（用于更新）和标准化代码（用于显示）。
        """
        conn = self._get_db_connection()
        query = f"""
        SELECT 
            f.stock_code AS stock_code_raw,               -- 原始值，用于更新
            CAST(f.stock_code AS TEXT) AS stock_code_str, -- 转为文本
            CAST(f.report_date AS INTEGER) AS report_date,
            ind.industry_code,
            ind.industry_name,
            ind.stock_name,
            COALESCE(f.field_6, 0.0)   AS roe,
            COALESCE(f.field_184, 0.0) AS profit_yoy,
            COALESCE(f.field_183, 0.0) AS revenue_yoy,
            COALESCE(f.field_219, 0.0) AS ocf_ps,
            COALESCE(f.field_210, 0.0) AS debt_to_asset,
            f.field_362 AS tdx_score,
            f.custom_score  AS current_score,
            f.custom_rating AS current_rating
        FROM financial_data f
        INNER JOIN dataset_industry_sectors ind 
            ON f.stock_code = ind.stock_code AND ind.is_active = 1
        WHERE f.report_date = {report_date}
        """
        df = pd.read_sql_query(query, conn)
        conn.close()

        if not df.empty:
            # 生成标准化的股票代码（6位补零），用于显示和分组
            df['stock_code'] = df['stock_code_str'].astype(str).str.zfill(6)
            # 保留原始代码用于更新
            # stock_code_raw 已存在
        return df

    @staticmethod
    def calc_industry_neutralization(df: pd.DataFrame, factor_cols: list) -> pd.DataFrame:
        df_scored = df.copy()
        for col in factor_cols:
            low = df_scored[col].quantile(0.01)
            high = df_scored[col].quantile(0.99)
            df_scored[col] = df_scored[col].clip(low, high)

            group = df_scored.groupby('industry_code')[col]
            mean = group.transform('mean')
            std = group.transform('std').replace(0, 1e-6)
            df_scored[f'{col}_zscore'] = (df_scored[col] - mean) / std
        return df_scored

    @staticmethod
    def calculate_scores_and_ratings(df: pd.DataFrame) -> pd.DataFrame:
        weights = {
            'roe_zscore': 0.35,
            'profit_yoy_zscore': 0.25,
            'revenue_yoy_zscore': 0.15,
            'ocf_ps_zscore': 0.25
        }
        df['composite_score'] = 0.0
        for factor, weight in weights.items():
            df['composite_score'] += df[factor] * weight

        veto_condition = (
            (df['ocf_ps'] < 0) |
            (df['debt_to_asset'] > 85.0) |
            (df['profit_yoy'] < -50.0)
        )
        df['is_vetoed'] = veto_condition.astype(int)

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
        report_dates = self.get_all_report_dates()
        print(f"🔍 检索到财务数据库中共包含 {len(report_dates)} 个报告期: {report_dates}")

        all_diff_records = []
        calc_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        conn = self._get_db_connection()
        cursor = conn.cursor()
        neutral_factors = ['roe', 'profit_yoy', 'revenue_yoy', 'ocf_ps']

        for date in report_dates:
            print(f"⚡ 正在处理报告期: {date} ...")

            raw_df = self.load_clean_dataset_with_current_baseline(report_date=date)
            if raw_df.empty:
                continue

            df_neutral = self.calc_industry_neutralization(raw_df, factor_cols=neutral_factors)
            df_final = self.calculate_scores_and_ratings(df_neutral)

            # 计算变动
            df_final['score_diff'] = df_final['composite_score'] - df_final['current_score']

            has_baseline = (
                df_final['current_rating'].notna() &
                (df_final['current_rating'] != '') &
                df_final['current_score'].notna()
            )
            rating_changed = df_final['composite_rating'] != df_final['current_rating']
            score_changed = df_final['score_diff'].abs() > 0.001

            diff_mask = has_baseline & (rating_changed | score_changed)
            diff_df = df_final[diff_mask].copy()
            if not diff_df.empty:
                all_diff_records.append(diff_df)

            # ---- 更新主表（使用原始股票代码） ----
            update_data_main = []
            for _, row in df_final.iterrows():
                # 使用原始代码（不补零）
                stock_raw = str(row['stock_code_raw'])
                # 如果原始代码是数字字符串，可能不带前导零，直接使用
                update_data_main.append((
                    float(row['composite_score']) if pd.notna(row['composite_score']) else 0.0,
                    str(row['composite_rating']),
                    stock_raw,
                    int(row['report_date'])
                ))

            cursor.executemany("""
                UPDATE financial_data 
                SET custom_score = ?, custom_rating = ?
                WHERE stock_code = ? AND report_date = ?;
            """, update_data_main)
            conn.commit()

            # 打印受影响行数（调试用）
            total_updated = cursor.rowcount  # 注意：executemany 后 rowcount 是所有影响行的总数
            print(f"   主表更新影响行数: {total_updated}")

            # ---- 更新快照表（使用标准化代码，便于查阅） ----
            snapshot_data = [
                (
                    str(row['stock_code']),  # 标准化6位
                    int(row['report_date']),
                    float(row['composite_score']) if pd.notna(row['composite_score']) else 0.0,
                    str(row['composite_rating']),
                    int(row['is_vetoed']),
                    calc_timestamp
                )
                for _, row in df_final.iterrows()
            ]
            cursor.executemany("""
                INSERT OR REPLACE INTO financial_custom_ratings 
                (stock_code, report_date, custom_score, custom_rating, is_vetoed, calc_timestamp)
                VALUES (?, ?, ?, ?, ?, ?);
            """, snapshot_data)

            conn.commit()

        conn.close()

        # 输出审计报告
        if all_diff_records:
            total_diff_df = pd.concat(all_diff_records, ignore_index=True)
            audit_columns = {
                'report_date': '报告期',
                'stock_code': '股票代码',
                'stock_name': '股票名称',
                'industry_name': '所属行业',
                'current_score': '上次归档综合得分',
                'composite_score': '本次综合得分',
                'score_diff': '得分变动幅度',
                'current_rating': '上次归档评价等级',
                'composite_rating': '本次评价等级',
                'is_vetoed': '是否触发一票否决',
                'roe': '净资产收益率(%)',
                'profit_yoy': '净利润同比增长率(%)',
                'ocf_ps': '每股经营现金流(元)'
            }
            audit_result = total_diff_df[list(audit_columns.keys())].rename(columns=audit_columns)

            with pd.ExcelWriter(audit_excel_path, engine='openpyxl') as writer:
                audit_result.to_excel(writer, sheet_name='评级差异审计报告', index=False)
                summary_df = pd.DataFrame([{
                    '审计计算时间': calc_timestamp,
                    '处理报告期总数': len(report_dates),
                    '新引发变更记录总数': len(audit_result),
                    '影响股票总只数': audit_result['股票代码'].nunique()
                }])
                summary_df.to_excel(writer, sheet_name='审计汇总概览', index=False)

            print(f"\n⚠️ 捕获到新的历史数据修正导致的评级变动！审计报告已生成: {audit_excel_path}")
            print(f"📊 变更记录共 {len(audit_result)} 条，涉及 {audit_result['股票代码'].nunique()} 只股票。")
        else:
            print("\n✅ 比对完成！本次计算结果与主表当前值完全一致，无新引发的变动记录。")

        print("🏁 全量批量打分与快照比对审计成功完成！")


if __name__ == "__main__":
    TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
    AUDIT_EXCEL_PATH = f"E:/分析日志/财务评级历史变更审计报告_{TIMESTAMP}.xlsx"

    batch_ranker = BatchIndustryFactorRanker(db_path="E:/tdx_financial.db")
    batch_ranker.run_batch_process_and_audit(audit_excel_path=AUDIT_EXCEL_PATH)