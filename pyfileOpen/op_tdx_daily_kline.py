import os
import sys
import struct
import sqlite3
from glob import glob

# 核心配置對齊您的系統
DB_PATH = r"E:\tdx_financial.db"
BASE_DIR = r"D:\new_hxzq_hc\vipdoc"

PATH_STRUCTURES = {
    'bj': ['lday'],
    'ds': ['lday'],
    'sh': ['lday'],
    'sz': ['lday']
}


def init_database():
    """初始化日線資料庫表與索引"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS stock_daily_kline (
        stock_code VARCHAR(20) NOT NULL,
        trade_date INTEGER NOT NULL,
        open REAL NOT NULL,
        high REAL NOT NULL,
        low REAL NOT NULL,
        close REAL NOT NULL,
        amount REAL NOT NULL,
        volume INTEGER NOT NULL,
        spare INTEGER,
        PRIMARY KEY (stock_code, trade_date)
    );
    """)

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_kline_code_date ON stock_daily_kline (stock_code, trade_date DESC);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_kline_date_code ON stock_daily_kline (trade_date, stock_code);")

    conn.commit()
    conn.close()


def parse_and_import_file(file_path, market_type):
    """解析單個二進制文件並返回結構化數據元組列表"""
    # 從文件名提取證券代碼（轉大寫，如 SH000896）
    file_name = os.path.basename(file_path)
    stock_code = os.path.splitext(file_name)[0].upper()

    # 根據是否為擴展市場選擇解包格式
    # ds 市場為 <I5f2I，普通市場為 <5If2I
    is_ds = (market_type == 'ds')
    struct_fmt = '<I5f2I' if is_ds else '<5If2I'
    record_size = 32

    records = []

    try:
        with open(file_path, 'rb') as f:
            buffer = f.read()

        size = len(buffer)
        for loc in range(0, size, record_size):
            if loc + record_size > size:
                break

            chunk = buffer[loc:loc + record_size]
            data = struct.unpack(struct_fmt, chunk)

            trade_date = data[0]

            # 價格數據換算邏輯對齊
            if is_ds:
                open_p, high_p, low_p, close_p = data[1], data[2], data[3], data[4]
            else:
                open_p, high_p, low_p, close_p = data[1] / 100.0, data[2] / 100.0, data[3] / 100.0, data[4] / 100.0

            amount = data[5]
            volume = data[6]
            spare = data[7]

            records.append((stock_code, trade_date, open_p, high_p, low_p, close_p, amount, volume, spare))

    except Exception as e:
        print(f"[-] 解析文件失敗 {file_path}: {e}")

    return records


def batch_import_market(market_type):
    """批量導入某一特定市場的日線數據"""
    if 'lday' not in PATH_STRUCTURES.get(market_type, []):
        return

    search_path = os.path.join(BASE_DIR, market_type, 'lday', '*.day')
    file_list = glob(search_path)

    if not file_list:
        print(f"[*] 未在市場 [{market_type}] 中找到 .day 文件。")
        return

    print(f"[*] 開始處理市場 [{market_type}]，共 {len(file_list)} 個文件...")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 關閉同步，極大提升寫入速度（適用於百萬級大數據首次入庫）
    cursor.execute("PRAGMA synchronous = OFF;")
    cursor.execute("PRAGMA journal_mode = MEMORY;")

    total_inserted = 0

    for idx, file_path in enumerate(file_list):
        records = parse_and_import_file(file_path, market_type)
        if not records:
            continue

        # 使用 INSERT OR REPLACE 實現增量 Upsert
        cursor.executemany("""
            INSERT OR REPLACE INTO stock_daily_kline 
            (stock_code, trade_date, open, high, low, close, amount, volume, spare)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, records)

        total_inserted += len(records)

        # 每處理 500 個文件提交一次事務，防止內存溢出
        if (idx + 1) % 500 == 0:
            conn.commit()
            print(f"    -> 已進度: {idx + 1}/{len(file_list)} 文件，累計入庫 {total_inserted} 條 K 線。")

    conn.commit()
    conn.close()
    print(f"[+] 市場 [{market_type}] 導入完成，共入庫 {total_inserted} 條記錄。")


def main():
    print("=== 通達信二進制日線高效 SQL 入庫系統 ===")
    init_database()

    # 遍歷清洗所有市場
    for market in PATH_STRUCTURES.keys():
        batch_import_market(market)

    print("\n[+] 全市場日線數據重構入庫完畢！")


if __name__ == "__main__":
    main()