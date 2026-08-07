import os
import sqlite3
import pandas as pd
from tqdm import tqdm

# 🎯 您的核心配置路徑
DB_PATH = "E:/tdx_financial.db"
TXT_PATH = "D:/行业板块.txt"

# 🎯 核心防禦開關：如果表結構發生衝突報錯，將此處改為 True，運行一次後會自動洗表重構
FORCE_REBUILD = False  # 遇到表結構衝突報，需要变更时改為 True ，也可以直接删除表，或手工增江两个字段，以便保留已经手工维护进去的退市股票


def init_industry_table_v2(force_clean=False):
    """
    【核心防禦 V2.1】初始化行業板塊表，具備動態洗表重構機制
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    if force_clean:
        print(f"🧹 [🚨 安全清理机制触发]：正在清除旧版行业表結構，准备升级...")
        cursor.execute("DROP TABLE IF EXISTS dataset_industry_sectors;")
        conn.commit()

    print(f"⚙️ 正在检查并初始化行业数据表 V2.0 (含上市/退市時間戳)...")

    # 建立 7 欄位高階行業底座
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS dataset_industry_sectors (
            industry_code TEXT NOT NULL,
            industry_name TEXT NOT NULL,
            stock_code TEXT NOT NULL,
            stock_name TEXT NOT NULL,
            full_stock_code TEXT NOT NULL,
            is_active INTEGER DEFAULT 1,     -- 1:上市中, 0:已退市
            list_date INTEGER,               -- 上市日期 (如 19931220)
            delist_date INTEGER,             -- 退市日期 (如 20070427)
            PRIMARY KEY (industry_code, stock_code)
        )
    """)

    # 索引優化
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_industry_code ON dataset_industry_sectors (industry_code);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_industry_stock ON dataset_industry_sectors (stock_code);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_stock_dates ON dataset_industry_sectors (list_date, delist_date);")

    conn.commit()
    conn.close()


def guess_market_prefix(code: str) -> str:
    code = str(code).strip().zfill(6)
    if code.startswith(('60', '68', '88', '900')):
        return "SH" + code
    elif code.startswith(('00', '30', '200', '400', '430')):
        return "SZ" + code
    elif code.startswith(('83', '87', '88')):
        return "BJ" + code
    return "SZ" + code


def import_industry_txt_to_db_v2():
    if not os.path.exists(TXT_PATH):
        print(f"❌ 错误：未在路径处找到文本文件: {TXT_PATH}")
        return

    # 執行建表，並傳入是否強制重構的參數
    init_industry_table_v2(force_clean=FORCE_REBUILD)

    print(f"📖 正在解析通达信行业板块文本...")
    try:
        df = pd.read_csv(TXT_PATH, sep=',', header=None,
                         names=['industry_code', 'industry_name', 'stock_code', 'stock_name'],
                         dtype=str, encoding='gbk')
    except UnicodeDecodeError:
        df = pd.read_csv(TXT_PATH, sep=',', header=None,
                         names=['industry_code', 'industry_name', 'stock_code', 'stock_name'],
                         dtype=str, encoding='utf-8')

    if df.empty:
        print("⚠️ 警告：文本中没有有效数据。")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    insert_count = 0
    print(f"🚀 开始向 V2.0 行业表灌注基础映射数据...")

    try:
        for _, row in tqdm(df.iterrows(), total=len(df), desc="行业资产入库中"):
            ind_code = str(row['industry_code']).strip()
            ind_name = str(row['industry_name']).strip()
            stk_code = str(row['stock_code']).strip().zfill(6)
            stk_name = str(row['stock_name']).strip()

            if not ind_code or not stk_code:
                continue

            full_stk_code = guess_market_prefix(stk_code)

            # 如果不是強制重建模式，我們才走動態過濾檢查
            if not FORCE_REBUILD:
                try:
                    cursor.execute(
                        "SELECT list_date, delist_date FROM dataset_industry_sectors WHERE industry_code=? AND stock_code=?",
                        (ind_code, stk_code))
                    exist_row = cursor.fetchone()
                except sqlite3.OperationalError:
                    # 雙重防禦：如果運行中依然報錯找不到新欄位，直接切換為全新寫入
                    exist_row = None
            else:
                exist_row = None

            if exist_row:
                # 記錄存在，更新名字，保留已手工維護的時間戳
                cursor.execute("""
                    UPDATE dataset_industry_sectors 
                    SET industry_name=?, stock_name=?, full_stock_code=?
                    WHERE industry_code=? AND stock_code=?
                """, (ind_name, stk_name, full_stk_code, ind_code, stk_code))
            else:
                # 全新寫入
                cursor.execute("""
                    INSERT OR REPLACE INTO dataset_industry_sectors 
                    (industry_code, industry_name, stock_code, stock_name, full_stock_code, is_active, list_date, delist_date)
                    VALUES (?, ?, ?, ?, ?, 1, NULL, NULL)
                """, (ind_code, ind_name, stk_code, stk_name, full_stk_code))

            insert_count += 1
            if insert_count % 500 == 0:
                conn.commit()

        conn.commit()

        # 統計最新結果
        cursor.execute("SELECT COUNT(DISTINCT industry_code), COUNT(*) FROM dataset_industry_sectors;")
        total_sectors, total_records = cursor.fetchone()
        conn.close()

        print(f"\n【🎉 行业底座 V2.0 升级并灌注大成功！】")
        print(f"📊 最终运行统计（{DB_PATH}）：")
        print(f"  └─ 本次成功處理映射關係：{insert_count} 条")
        print(f"  └─ 当前库内共囊括二级行业：{total_sectors} 个")
        print(f"  └─ 当前行業總股本成分池总量：{total_records} 只")
        print(f"💡 提示：升级成功后，您可以将代碼中的 FORCE_REBUILD 改回 False，以便後續進行安全的常態化維護。")

    except Exception as e:
        print(f"\n❌ 导入过程中发生严重异常: {e}")
        if 'conn' in locals(): conn.close()


if __name__ == "__main__":
    import_industry_txt_to_db_v2()