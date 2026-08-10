import os
import struct
import sqlite3
from tqdm import tqdm
import pandas as pd
from datetime import datetime
from pytdx.hq import TdxHq_API
"""
用本地文件中的数据高效合并归集数据到数据库
"""
# === 核心配置對齊 ===
DB_PATH = r"E:\tdx_financial.db"
BASE_DIR = r"D:\new_hxzq_hc\vipdoc"
AUDIT_LOG_PATH = f"E:/分析日志/日线审计_tdx_daily_update_audit{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx"
HQ_SERVER = ('103.251.85.58', 7709)

PATH_STRUCTURES = {
    'bj': ['lday'],
    'ds': ['lday'],
    'sh': ['lday'],
    'sz': ['lday']
}


def get_db_kline_meta():
    """從資料庫獲取全市場所有股票的最新日期與記錄數，用於增量對比"""
    print("[*] 阶段 1：讀取資料庫現有K線...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT stock_code, MAX(trade_date), COUNT(*) FROM stock_daily_kline GROUP BY stock_code;")
    rows = cursor.fetchall()
    conn.close()
    return {row[0]: {'last_date': row[1], 'count': row[2]} for row in rows}


def refresh_local_binary_files(db_meta):
    """
    第一部分：高效率讀取本地二進制文件，增量追加每日新數據
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("PRAGMA synchronous = OFF;")
    cursor.execute("PRAGMA journal_mode = MEMORY;")

    audit_records = []
    total_new_rows = 0

    print("[*] 階段 2：開始掃描本地二進制目錄進行高效率增量更新...")

    for market, sub_dirs in PATH_STRUCTURES.items():
        if 'lday' not in sub_dirs:
            continue

        dir_path = os.path.join(BASE_DIR, market, 'lday')
        if not os.path.exists(dir_path):
            continue

        file_list = os.listdir(dir_path)
        is_ds = (market == 'ds')
        struct_fmt = '<I5f2I' if is_ds else '<5If2I'
        record_size = 32

        for file_name in tqdm(file_list, desc="Processing file_list"):
            if not file_name.endswith('.day'):  # endswith是作为方法调用，修正：.day 文件
                continue

            stock_code = os.path.splitext(file_name)[0].upper()
            file_path = os.path.join(dir_path, file_name)

            # 獲取資料庫當前該股狀態
            stock_meta = db_meta.get(stock_code, {'last_date': None, 'count': 0})
            last_date = stock_meta['last_date']

            try:
                file_size = os.path.getsize(file_path)
                # 計算理論上的總記錄數
                total_file_records = file_size // record_size

                # 如果本地文件記錄數大於資料庫，或者資料庫還沒有數據，則進行 Seek 追加
                new_to_insert = []
                with open(file_path, 'rb') as f:
                    # 粗略定位：如果資料庫已有 N 條，直接跳過前面的數據
                    start_pos = max(0, (stock_meta['count'] - 5 ) * record_size)
                    f.seek(start_pos)

                    while True:
                        chunk = f.read(record_size)
                        if len(chunk) < record_size:
                            break

                        data = struct.unpack(struct_fmt, chunk)
                        trade_date = data[0]

                        # 僅處理比資料庫最新日期更晚的數據
                        if last_date and trade_date <= last_date - 5:  # 留點緩衝，防止最后几天的数据并非收盘后的最终数据
                            continue

                        if is_ds:
                            open_p, high_p, low_p, close_p = data[1], data[2], data[3], data[4]
                        else:
                            open_p, high_p, low_p, close_p = data[1] / 100.0, data[2] / 100.0, data[3] / 100.0, data[
                                4] / 100.0

                        new_to_insert.append(
                            (stock_code, trade_date, open_p, high_p, low_p, close_p, data[5], data[6], data[7]))

                if new_to_insert:
                    cursor.executemany("""
                        INSERT OR REPLACE INTO stock_daily_kline 
                        (stock_code, trade_date, open, high, low, close, amount, volume, spare)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """, new_to_insert)

                    total_new_rows += len(new_to_insert)
                    # 記錄審計日誌
                    audit_records.append({
                        '更新時間': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        '證券代碼': stock_code,
                        '更新模式': '本地二進制增量(Seek)',
                        '變動狀態': 'NEW_INSERT',
                        '影響行數': len(new_to_insert),
                        '變動詳情': f"追加了從 {new_to_insert[0][1]} 到 {new_to_insert[-1][1]} 的最新K線"
                    })

            except Exception as e:
                print(f"[-] 處理文件 {file_name} 失敗: {e}")

    conn.commit()
    conn.close()
    print(f"[+] 本地二進制增量更新完成，共追加入庫 {total_new_rows} 條記錄。")
    return audit_records


def patch_via_network(db_meta, audit_records):
    """
    第二部分：針對在市交易個股進行網路一致性校驗與網路修補
    """
    print("\n[*] 階段 3：啟動網路接口進行常規在市個股數據校验與缺失補全...")
    api = TdxHq_API()

    # 這裡我們篩選出主板滬深交易活躍個股進行校驗（可過濾指數或特定標的）
    # 為防止單次請求過大，我們示範核心邏輯。實際系統中可以配合您的二級行業表篩選 active 的個股
    check_list = [code for code in db_meta.keys() if code.startswith('SH6') or code.startswith('SZ00')]

    if not check_list:
        print("[*] 未在資料庫中找到符合常規校驗的在市個股。")
        return audit_records

    network_patches = 0
    if api.connect(HQ_SERVER[0], HQ_SERVER[1]):
        try:
            # 抽樣或遍歷前 50 隻活躍股作為校驗與補全演示（您可以擴大範圍）
            for stock_code in check_list[:50]:
                market_id = 1 if stock_code.startswith('SH') else 0
                pure_code = stock_code[2:]  # 提取 6 位純數字

                # 獲取網路端最新的 5 條數據進行校驗
                bars = api.get_security_bars(9, market_id, pure_code, 0, 5)
                if not bars:
                    continue

                df_net = api.to_df(bars)
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()

                for _, row in df_net.iterrows():
                    net_date = int(row['date'].replace('-', '')) if isinstance(row['date'], str) else row['date']
                    net_close = row['close']
                    print(f"  校驗 {stock_code}, {net_close}, {net_date}")

                    # 查詢本地資料庫是否存在這一天的數據
                    cursor.execute("SELECT close FROM stock_daily_kline WHERE stock_code=? AND trade_date=?",
                                   (stock_code, net_date))
                    local_row = cursor.fetchone()

                    if not local_row:
                        # 情況 A：網路有，本地缺失 -> 執行網絡修補
                        cursor.execute("""
                            INSERT INTO stock_daily_kline (stock_code, trade_date, open, high, low, close, amount, volume)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                        """, (stock_code, net_date, row['open'], row['high'], row['low'], row['close'], row['amount'],
                              row['volume']))
                        conn.commit()
                        network_patches += 1
                        audit_records.append({
                            '更新時間': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            '證券代碼': stock_code,
                            '更新模式': '網路校驗補全(PyTdx)',
                            '變動狀態': 'PATCH_MISSING',
                            '影響行數': 1,
                            '變動詳情': f"補全了本地缺失的日期 {net_date} K線"
                        })
                    elif abs(local_row[0] - net_close) > 0.01:
                        # 情況 B：本地有但數值與網路官方不一致 -> 執行數據校正（例如處理除權或數據污染）
                        cursor.execute("""
                            UPDATE stock_daily_kline SET open=?, high=?, low=?, close=?, amount=?, volume=?
                            WHERE stock_code=? AND trade_date=?;
                        """, (row['open'], row['high'], row['low'], row['close'], row['amount'], row['volume'],
                              stock_code, net_date))
                        conn.commit()
                        audit_records.append({
                            '更新時間': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            '證券代碼': stock_code,
                            '更新模式': '網路數據校正(PyTdx)',
                            '變動狀態': 'VALUE_CORRECTED',
                            '影響行數': 1,
                            '變動詳情': f"修正了日期 {net_date} 的數值，原本地收盤:{local_row[0]} -> 修正為網頁端:{net_close}"
                        })
                conn.close()
        except Exception as e:
            print(f"[-] 網路校驗過程中發生錯誤: {e}")
        finally:
            api.disconnect()

    print(f"[+] 網路校驗完畢，共自動向下修補/修正了 {network_patches} 條記錄。")
    return audit_records


def main():
    print("=== 綜合量化系統：日線自動更新與審計審查模組 ===")

    # 步驟 1: 讀取基礎元數據
    db_meta = get_db_kline_meta()

    # 步驟 2: 執行本地二進制高效追加
    audit_logs = refresh_local_binary_files(db_meta)

    # 步驟 3: 執行網路校驗與數據修補
    final_logs = patch_via_network(db_meta, audit_logs)

    # 步驟 4: 輸出審計 Excel 報告
    print(f"\n[*] 正在將數據變動日誌寫入高階量化審計文檔...")
    if final_logs:
        df_audit = pd.DataFrame(final_logs)
    else:
        df_audit = pd.DataFrame(columns=['更新時間', '證券代碼', '更新模式', '變動狀態', '影響行數', '變動詳情'])
        # 插入一條空白無變動的記錄
        df_audit.loc[0] = [datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'SYSTEM', '無變動', 'NORMAL', 0,
                           '今日全市場數據已與磁碟/網路同步，未發生新增或覆蓋。']

    df_audit.to_excel(AUDIT_LOG_PATH, index=False)
    print(f"[+] 審計日誌已成功產出：{AUDIT_LOG_PATH}")


if __name__ == "__main__":
    main()