import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime


class BatchIndustryFactorRanker:
    """
    量化系统多周期全量财务打分、评级落盘与变动审计模组 (V3.1 修正版)
    BUG 修正说明：
    以历史快照表 financial_custom_ratings 中的记录作为唯一的“上一次评级基准”，
    彻底解决重复输出已调整历史变动记录的问题。
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

        # 1. 检查并给主表补充字段
        cursor.execute("PRAGMA table_info(financial_data)")
        existing_cols = [col[1] for col in cursor.fetchall()]
        if 'custom_score' not in existing_cols:
            cursor.execute("ALTER TABLE financial_data ADD COLUMN custom_score REAL;")
        if 'custom_rating' not in existing_cols:
            cursor.execute("ALTER TABLE financial_data ADD COLUMN custom_rating TEXT;")

        # 2. 创建评级快照历史表
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
        """获取全量离散报告期"""
        conn = self._get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT report_date FROM financial_data ORDER BY report_date ASC;")
        dates = [row[0] for row in cursor.fetchall() if row[0] is not None]
        conn.close()
        return dates

    def load_clean_dataset_with_snapshot_baseline(self, report_date: int) -> pd.DataFrame:
        """结合历史快照读取数据，并强制规范数据类型"""
        conn = self._get_db_connection()

        query = f"""
        SELECT 
            CAST(f.stock_code AS TEXT) AS stock_code,
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
            snap.custom_score  AS snap_custom_score,  -- 历史快照表记录的旧得分
            snap.custom_rating AS snap_custom_rating  -- 历史快照表记录的旧评级
        FROM financial_data f
        INNER JOIN dataset_industry_sectors ind 
            ON f.stock_code = ind.stock_code AND ind.is_active = 1
        LEFT JOIN financial_custom_ratings snap 
            ON f.stock_code = snap.stock_code AND f.report_date = snap.report_date
        WHERE f.report_date = {report_date}
        """
        df = pd.read_sql_query(query, conn)
        conn.close()

        # 显式确保股票代码为 6 位补零字符串，避免类型不匹配导致 JOIN 失败
        if not df.empty:
            df['stock_code'] = df['stock_code'].astype(str).str.zfill(6)
        return df

    @staticmethod
    def calc_industry_neutralization(df: pd.DataFrame, factor_cols: list) -> pd.DataFrame:
        """二级行业内标准化 (Z-Score)"""
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

    def calculate_scores_and_ratings(self, df: pd.DataFrame) -> pd.DataFrame:
        """综合加权得分与 9 级分类"""
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
        """批量计算与审计（修正数据类型与快照判定 BUG）"""
        report_dates = self.get_all_report_dates()
        print(f"🔍 检索到财务数据库中共包含 {len(report_dates)} 个报告期: {report_dates}")

        all_diff_records = []
        calc_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        conn = self._get_db_connection()
        cursor = conn.cursor()

        neutral_factors = ['roe', 'profit_yoy', 'revenue_yoy', 'ocf_ps']

        for date in report_dates:
            print(f"⚡ 正在处理报告期: {date} ...")

            # 1. 结合历史快照读取数据
            raw_df = self.load_clean_dataset_with_snapshot_baseline(report_date=date)
            if raw_df.empty:
                continue

            # 2. 中性化与重新打分
            df_neutral = self.calc_industry_neutralization(raw_df, factor_cols=neutral_factors)
            df_final = self.calculate_scores_and_ratings(df_neutral)

            # 3. 计算分值变动（处理 NaN 缺失值逻辑）
            df_final['score_diff'] = df_final['composite_score'] - df_final['snap_custom_score']

            # -------------------------------------------------------------
            # 核心修正：严格判定“真正的历史变更”
            # 1. snap_custom_rating 必须存在且有效 (非 NaN / 非空字符串)
            # 2. snap_custom_score 必须为有效数值 (非 NaN)
            # -------------------------------------------------------------
            has_snapshot = (
                    df_final['snap_custom_rating'].notna() &
                    (df_final['snap_custom_rating'] != '') &
                    df_final['snap_custom_score'].notna()
            )

            rating_changed = df_final['composite_rating'] != df_final['snap_custom_rating']
            score_changed = df_final['score_diff'].abs() > 0.001

            # 只有在存在历史有效快照，且评级或分值发生变动时，才写入变动审计日志
            diff_mask = has_snapshot & (rating_changed | score_changed)
            diff_df = df_final[diff_mask].copy()

            if not diff_df.empty:
                all_diff_records.append(diff_df)

            # 4. 落盘更新：主表 financial_data + 快照历史表 financial_custom_ratings
            update_data_main = [
                (
                    float(row['composite_score']) if pd.notna(row['composite_score']) else 0.0,
                    str(row['composite_rating']),
                    str(row['stock_code']).zfill(6),
                    int(row['report_date'])
                )
                for _, row in df_final.iterrows()
            ]
            cursor.executemany("""
                UPDATE financial_data 
                SET custom_score = ?, custom_rating = ?
                WHERE stock_code = ? AND report_date = ?;
            """, update_data_main)

            snapshot_data = [
                (
                    str(row['stock_code']).zfill(6),
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

            # 提交当前报告期的事务
            conn.commit()

        conn.close()

        # 5. 输出差异审计日志
        if all_diff_records:
            total_diff_df = pd.concat(all_diff_records, ignore_index=True)

            audit_columns = {
                'report_date': '报告期',
                'stock_code': '股票代码',
                'stock_name': '股票名称',
                'industry_name': '所属行业',
                'snap_custom_score': '上次归档综合得分',
                'composite_score': '本次综合得分',
                'score_diff': '得分变动幅度',
                'snap_custom_rating': '上次归档评价等级',
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
            print("\n✅ 比对完成！本次计算结果与历史快照库完全一致，无新引发的变动记录（历史修改已全部归档）。")

        print("🏁 全量批量打分与快照比对审计成功完成！")

# ==========================================
# 自动化运行入口
# ==========================================
if __name__ == "__main__":
    TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
    AUDIT_EXCEL_PATH = f"E:/分析日志/财务评级历史变更审计报告_{TIMESTAMP}.xlsx"

    batch_ranker = BatchIndustryFactorRanker(db_path="E:/tdx_financial.db")
    batch_ranker.run_batch_process_and_audit(audit_excel_path=AUDIT_EXCEL_PATH)