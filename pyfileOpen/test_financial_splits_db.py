import sqlite3
import pandas as pd


def analyze_financial_and_splits_perfect():
    # 1. 建立数据库连接
    conn = sqlite3.connect("D:/tdx_financial.db")

    # 🎯 完美对齐你的底层数据结构：
    # f.stock_code -> 财务表的 6 位纯数字 (如 '600036')
    # f.report_date -> 财务表的整数型日期 (如 20251231)
    # SUBSTR(s.code, 3) -> 将权息表的 'SH600036' / 'SZ600036' 转为 '600036' 完美关联
    # 年份对齐 -> 确保拉出来的是该财务报告期对应年度内的分红除权明细
    sql_query = """
        SELECT 
            f.stock_code AS 股票代码,
            f.report_date AS 财务报告期,
            f.field_197 AS 净资产收益率_ROE,     -- 示例：通达信通常第197列是ROE
            f.field_95 / 1e8 AS 净利润_亿元,     -- 示例：通达信通常第95列是净利润
            s.date AS 分红除权日,
            s.dividend AS 每股现金红利_元,
            s.song_ratio AS 每股送转股数
        FROM financial_data f
        LEFT JOIN stock_splits s 
               ON f.stock_code = SUBSTR(s.code, 3) 
              AND SUBSTR(CAST(s.date AS TEXT), 1, 4) = SUBSTR(CAST(f.report_date AS TEXT), 1, 4)
        WHERE f.stock_code = '600036' 
          AND f.report_date = 20251231
    """

    try:
        # 2. 执行联合查询
        df_result = pd.read_sql(sql_query, conn)
        conn.close()

        if df_result.empty:
            print("⚠️ 提示：字段已完全对齐，但该报告期内未查询到招商银行(600036)的数据。")
            print("请确认本地通达信的 20241231 财务报表文件是否已经使用 batch_import 或增量更新解析入库。")

            # 💡 自动降级探测：如果不限定报告期，看看招商银行在数据库里到底有哪些年份的数据
            print("\n🔍 正在为你自动探测招商银行在数据库中的所有历史财务报告期快照...")
            conn = sqlite3.connect("D:/tdx_financial.db")
            df_check = pd.read_sql(
                "SELECT DISTINCT report_date FROM financial_data WHERE stock_code='600036' ORDER BY report_date DESC LIMIT 10;",
                conn)
            conn.close()
            if not df_check.empty:
                print("数据库中实际存在的报告期有：")
                print(df_check['report_date'].tolist())
            else:
                print("❌ 财务表 financial_data 中完全没有 600036 的任何历史数据，请检查财务数据是否导入完整。")
        else:
            print("🎉【合流调阅成功】招商银行财务指标与历史网络分红明细联查结果如下：")
            print(df_result)

    except Exception as e:
        print(f"❌ 运行发生 SQL 语法或字段异常: {e}")
        if 'conn' in locals():
            conn.close()


if __name__ == "__main__":
    analyze_financial_and_splits_perfect()