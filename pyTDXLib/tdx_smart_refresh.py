import os
import re
import time
import socket
import sqlite3
import pandas as pd
from pytdx.hq import TdxHq_API
from pytdx.exhq import TdxExHq_API

# === 核心配置對齊 ===
DB_PATH = r"E:\tdx_financial.db"  # 已成功遷移至 E 盤
CFG_PATH = r"D:\new_hxzq_hc\connect.cfg"
LOG_XLSX = r"E:\分析日志\tdx_smart_scan_log.xlsx"


def parse_connect_cfg(cfg_path):
    """解析通達信配置檔（GB18030），提取 HQHOST(標準) 和 DSHOST(擴展) 伺服器清單"""
    hq_servers = []
    ds_servers = []

    if not os.path.exists(cfg_path):
        print(f"[-] 未找到配置文件: {cfg_path}")
        return hq_servers, ds_servers

    with open(cfg_path, 'r', encoding='gb18030', errors='ignore') as f:
        content = f.read()

    # 1. 提取標準行情伺服器 [HQHOST]
    hq_section = re.search(r'\[HQHOST\](.*?)\[', content, re.DOTALL)
    if hq_section:
        block = hq_section.group(1)
        ips = re.findall(r'IPAddress\d+=(.*?)\n', block)
        ports = re.findall(r'Port\d+=(.*?)\n', block)
        names = re.findall(r'HostName\d+=(.*?)\n', block)
        for name, ip, port in zip(names, ips, ports):
            hq_servers.append({'name': name.strip(), 'ip': ip.strip(), 'port': int(port.strip())})

    # 2. 提取擴展行情伺服器 [DSHOST]
    ds_section = re.search(r'\[DSHOST\](.*?)(?:\[|$)', content, re.DOTALL)
    if ds_section:
        block = ds_section.group(1)
        ips = re.findall(r'IPAddress\d+=(.*?)\n', block)
        ports = re.findall(r'Port\d+=(.*?)\n', block)
        names = re.findall(r'HostName\d+=(.*?)\n', block)
        for name, ip, port in zip(names, ips, ports):
            ds_servers.append({'name': name.strip(), 'ip': ip.strip(), 'port': int(port.strip())})

    return hq_servers, ds_servers


def select_best_server(server_list):
    """對伺服器清單進行 TCP 連線測速，返回最快且可用的 (IP, Port)"""
    best_server = None
    min_latency = float('inf')

    print(f"[*] 開始對 {len(server_list)} 個節點進行動態優選測速...")
    for svr in server_list:
        ip = svr['ip']
        port = svr['port']
        name = svr['name']

        start_time = time.perf_counter()
        try:
            # 建立一個輕量級的 TCP socket 測試連線速度
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.5)  # 500毫秒超時
            s.connect((ip, port))
            s.close()
            latency = (time.perf_counter() - start_time) * 1000  # 轉為毫秒

            print(f"    -> [{name}] {ip}:{port} | 延遲: {latency:.2f} 毫秒")
            if latency < min_latency:
                min_latency = latency
                best_server = (ip, port, name)
        except (socket.timeout, ConnectionRefusedError, Exception):
            continue

    if best_server:
        print(f"[+] 智選最優節點: [{best_server[2]}] {best_server[0]}:{best_server[1]} (回應時間: {min_latency:.2f}ms)")
        return best_server[0], best_server[1]
    return None


def main():
    print("=== 通達信科學自動化：多伺服器動態選站與退市多維穿透系統 ===")

    # 1. 讀取與解析 connect.cfg
    hq_pool, ds_pool = parse_connect_cfg(CFG_PATH)
    print(f"[+] 從本地配置中加載了 {len(hq_pool)} 個標準站點，{len(ds_pool)} 個擴展站點。")

    # 2. 測速並獲取最佳站點
    print("\n--- 標準行情站點測速 ---")
    best_hq = select_best_server(hq_pool)
    print("\n--- 擴展行情站點測速 ---")
    best_ds = select_best_server(ds_pool)

    verification_logs = []

    # 3. 如果找到了最佳擴展站點，我們發動「全市場編碼大穿透」
    if best_ds:
        print("\n--- 3. 執行退市股票精準多 market_id 大穿透 ---")
        api_ex = TdxExHq_API()
        if api_ex.connect(best_ds[0], best_ds[1]):
            try:
                # 基於您提供的 38#（與衍生品、其他特殊市場相關）和 42（股轉）等線索
                # 遍歷通達信可能被指派的所有擴展市場 ID
                probe_markets = [1, 2, 8, 9, 27, 31, 33, 38, 41, 42, 43, 44]
                target_code = "000549"  # 湘火炬A

                # 同時測試您在圖二中手工映射的變體代碼（看伺服器認哪個）
                variant_codes = [target_code, f"394{target_code[3:]}", f"394{target_code}"]

                for m_id in probe_markets:
                    for code_to_test in variant_codes:
                        print(f"[*] 試探擴展市場 [{m_id}] 上的證券代碼 [{code_to_test}] ...")
                        # 獲取 9：日線 K 線
                        bars = api_ex.get_instrument_bars(9, m_id, code_to_test, 0, 50)
                        if bars:
                            df = api_ex.to_df(bars)
                            if not df.empty:
                                date_col = 'datetime' if 'datetime' in df.columns else 'date'
                                print(f"    [======= 🔥 穿透成功！ =======]")
                                print(f"    在擴展市場ID: {m_id} 成功用代碼 {code_to_test} 獲取到歷史 K 線！")
                                print(f"    最新記錄日期: {df[date_col].iloc[0]}, 收盤價: {df['close'].iloc[0]}")

                                verification_logs.append({
                                    '市場類型': 'EX', '市場ID': m_id, '測試代碼': code_to_test,
                                    '結果': '成功', '總條數': len(df), '摘要': f"最新日:{df[date_col].iloc[0]}"
                                })
                                continue

                        verification_logs.append({
                            '市場類型': 'EX', '市場ID': m_id, '測試代碼': code_to_test,
                            '結果': '未能獲取', '總條數': 0, '摘要': 'N/A'
                        })
            finally:
                api_ex.disconnect()

    # 4. 輸出檢測 Excel
    if verification_logs:
        pd.DataFrame(verification_logs).to_excel(LOG_XLSX, index=False)
        print(f"\n[+] 穿透與優選報告已產出至: {LOG_XLSX}")
    else:
        print("\n[-] 本次未啟動穿透測試，請檢查擴展網路連接。")


if __name__ == "__main__":
    main()