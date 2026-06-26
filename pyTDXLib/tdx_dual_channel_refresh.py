import os
import re
import time
import socket
import struct
import sqlite3
import pandas as pd
from datetime import datetime
from pytdx.hq import TdxHq_API
from pytdx.exhq import TdxExHq_API

# === 核心路徑配置（E 盤與本地環境完全對齊） ===
DB_PATH = r"E:\tdx_financial.db"
CFG_PATH = r"D:\new_tdx\connect.cfg"
BASE_DIR = r"D:\new_hxzq_hc\vipdoc"
FINAL_AUDIT_LOG = r"E:\tdx_dual_channel_audit.xlsx"


def parse_and_speed_test(cfg_path):
    """解析配置檔（修正為 Raw String 消除 Python 3.14 警告），並進行實時最快節點篩選"""
    hq_servers, ds_servers = [], []
    if not os.path.exists(cfg_path):
        print(f"[-] 未找到配置文件: {cfg_path}")
        return None, None

    with open(cfg_path, 'r', encoding='gb18030', errors='ignore') as f:
        content = f.read()

    # 使用 r'' 原始字串消除轉義警告
    for section, pool in [(r'\[HQHOST\]', hq_servers), (r'\[DSHOST\]', ds_servers)]:
        match = re.search(f'{section}(.*?)(?:\\[|$)', content, re.DOTALL)
        if match:
            block = match.group(1)
            ips = re.findall(r'IPAddress\d+=(.*?)\n', block)
            ports = re.findall(r'Port\d+=(.*?)\n', block)
            names = re.findall(r'HostName\d+=(.*?)\n', block)
            for n, ip, p in zip(names, ips, ports):
                pool.append({'name': n.strip(), 'ip': ip.strip(), 'port': int(p.strip())})

    def test_speed(srv_list):
        best = None
        min_ms = float('inf')
        for s in srv_list:
            start = time.perf_counter()
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(0.3)
                sock.connect((s['ip'], s['port']))
                sock.close()
                ms = (time.perf_counter() - start) * 1000
                if ms < min_ms:
                    min_ms = ms
                    best = (s['ip'], s['port'])
            except:
                continue
        return best

    print("[*] 正在進行雙通道網絡節點智選測速...")
    return test_speed(hq_servers), test_speed(ds_servers)


def get_db_stock_meta():
    """獲取本地資料庫中各股票的最新交易日期與已有記錄數"""
    if not os.path.exists(os.path.dirname(DB_PATH)):
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # 確保主表結構完整建立
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stock_daily_kline (
            stock_code TEXT, trade_date INTEGER, open REAL, high REAL, low REAL, close REAL, 
            amount REAL, volume INTEGER, spare INTEGER, PRIMARY KEY(stock_code, trade_date)
        );
    """)
    cursor.execute("SELECT stock_code, MAX(trade_date), COUNT(*) FROM stock_daily_kline GROUP BY stock_code;")
    rows = cursor.fetchall()
    conn.close()
    return {row[0]: {'last_date': row[1], 'count': row[2]} for row in rows}


def main():
    print("=== 通達信雙通道（在市 Seek 追加 + 退市市場 33 補全）自動化系統 ===")

    # 1. 網路智選
    best_hq, best_ds = parse_and_speed_test(CFG_PATH)
    print(f"[+] 主板最快通道: {best_hq} | 擴展(退市)最快通道: {best_ds}")

    # 2. 讀取現有資料庫狀態
    db_meta = get_db_stock_meta()
    audit_logs = []

    # 3. 測試退市股通道網絡同步 (以 000549 為例)
    target_retired = "000549"
    print(f"\n[*] 執行退市股網路雙通道同步核對: {target_retired}")

    # 獲取本地已有的最大日期
    meta = db_meta.get(f"SZ{target_retired}", {'last_date': 0, 'count': 0})
    last_local_date = meta['last_date'] if meta['last_date'] else 0

    if best_ds:
        api_ex = TdxExHq_API()
        if api_ex.connect(best_ds[0], best_ds[1]):
            try:
                # 使用穿透成功的市場 33 下載歷史 K 線
                bars = api_ex.get_instrument_bars(9, 33, target_retired, 0, 100)
                if bars:
                    df = api_ex.to_df(bars)
                    if not df.empty:
                        # 兼容性修正：自動偵測擴展接口的日期欄位與成交量欄位
                        date_col = 'datetime' if 'datetime' in df.columns else 'date'
                        vol_col = 'vol' if 'vol' in df.columns else ('volume' if 'volume' in df.columns else None)
                        amt_col = 'amount' if 'amount' in df.columns else 'trade_amount'

                        # 轉換擴展日期的格式 (去掉時間部分，保留8位整數日期)
                        df['pure_date'] = df[date_col].apply(
                            lambda x: int(str(x).split()[0].replace('-', '')) if '-' in str(x) else int(str(x)[:8])
                        )

                        # 篩選比本地資料庫更新的數據
                        df_new = df[df['pure_date'] > last_local_date]

                        if not df_new.empty:
                            conn = sqlite3.connect(DB_PATH)
                            cursor = conn.cursor()
                            inserted_rows = 0

                            for _, row in df_new.iterrows():
                                # 提取成交量和成交額
                                volume_val = row[vol_col] if vol_col else 0
                                amount_val = row[amt_col] if amt_col in df.columns else 0

                                cursor.execute("""
                                    INSERT OR REPLACE INTO stock_daily_kline 
                                    (stock_code, trade_date, open, high, low, close, amount, volume)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                                """, (f"SZ{target_retired}", row['pure_date'], row['open'], row['high'], row['low'],
                                      row['close'], amount_val, volume_val))
                                inserted_rows += 1

                            conn.commit()
                            conn.close()

                            print(f"    [+] 網絡同步成功：向 E 盤資料庫寫入 {inserted_rows} 條退市歷史缺失 K 線。")
                            audit_logs.append({
                                '代碼': target_retired, '模式': '擴展通道33', '狀態': '同步成功',
                                '新增行數': inserted_rows, '詳情': f'補全歷史至 {df_new["pure_date"].max()}'
                            })
                        else:
                            print("    [~] 本地資料庫中的退市數據已是最新，無需更新。")
                            audit_logs.append(
                                {'代碼': target_retired, '模式': '擴展通道33', '狀態': '無需變動', '新增行數': 0,
                                 '詳情': '數據已與伺服器完全一致'})
            except Exception as e:
                print(f"[-] 同步過程中發生未知錯誤: {e}")
            finally:
                api_ex.disconnect()

    # 4. 產出審計日誌
    df_audit = pd.DataFrame(audit_logs if audit_logs else [
        {'代碼': 'SYSTEM', '模式': '無', '狀態': '正常', '新增行數': 0, '詳情': '雙通道基礎校驗完成'}])
    df_audit.to_excel(FINAL_AUDIT_LOG, index=False)
    print(f"\n[+] 自動更新校驗結束，審計日誌已生成至: {FINAL_AUDIT_LOG}")


if __name__ == "__main__":
    main()