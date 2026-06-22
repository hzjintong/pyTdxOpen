import os
import pandas as pd
from pytdx.hq import TdxHq_API
from pytdx.exhq import TdxExHq_API

# 1. 核心配置（完全對齊您測試通過的可用伺服器與路徑）
HQ_SERVER = ('103.251.85.58', 7709)  # 您實測可用的主站 IP

EX_SERVERS = [
    ('116.205.143.214', 7727),  # 您實測可用的擴展主機
    ('119.4.167.144', 7721),
    ('119.147.164.60', 7727),
    ('124.71.187.122', 7727),
    ('47.107.75.159', 7727),
    ('103.251.85.58', 7727)
]

LOG_OUTPUT_PATH = r"D:\tdx_api_verify_log.xlsx"


def scan_extended_markets():
    """
    自動連線擴展伺服器並獲取完整的市場清單
    用來幫我們定位 '394' 開頭品種或退市品種到底歸屬於哪個 market_id 數字
    """
    api = TdxExHq_API()
    connected = False
    df_markets = None

    print("[*] 正在尋找可用的擴展行情伺服器...")
    for ip, port in EX_SERVERS:
        try:
            if api.connect(ip, port):
                print(f"[+] 成功連接到擴展伺服器: {ip}:{port}")
                markets = api.get_markets()
                if markets:
                    df_markets = api.to_df(markets)
                    connected = True
                    break
                api.disconnect()
        except Exception as e:
            print(f"[-] 嘗試連線 {ip}:{port} 失敗: {e}")

    if not connected or df_markets is None:
        print("[-] 無法獲取擴展市場清單。")
        return None

    try:
        # 在控制台列印前20個市場供觀察（確認是否有自定義板塊、三板或退市板塊的名稱）
        print("\n--- 成功獲取擴展市場清單 (前 20 條) ---")
        print(df_markets.head(20))
    finally:
        api.disconnect()

    return df_markets


def test_hq_kline(market, code):
    """測試主板/標準行情接口"""
    api = TdxHq_API()
    result = None
    if api.connect(HQ_SERVER[0], HQ_SERVER[1]):
        try:
            # category=9 代表日線, start=0, count=50
            bars = api.get_security_bars(9, market, code, 0, 50)
            if bars:
                result = api.to_df(bars)
        except Exception as e:
            print(f"[-] 查詢主板 K 線出錯 ({market}, {code}): {e}")
        finally:
            api.disconnect()
    return result


def test_ex_kline(market, code):
    """測試擴展行情接口"""
    api = TdxExHq_API()
    result = None
    # 使用清單中第一個可用的伺服器
    ip, port = EX_SERVERS[0]
    if api.connect(ip, port):
        try:
            # category=9 代表日線, start=0, count=50
            bars = api.get_instrument_bars(9, market, code, 0, 50)
            if bars:
                result = api.to_df(bars)
        except Exception as e:
            print(f"[-] 查詢擴展 K 線出錯 ({market}, {code}): {e}")
        finally:
            api.disconnect()
    return result


def main():
    print("=== 通達信網路接口深度遍歷與退市數據補全驗證 ===")

    # 步驟 1: 掃描並拉取擴展市場清單，確認退市板塊的 market 識別碼
    df_markets = scan_extended_markets()

    # 建立一個清單來儲存測試結果，最後導出 Excel 日誌
    verification_logs = []

    # 步驟 2: 設定多個試探性組合 (針對退市股進行暴力遍歷驗證)
    # 組合結構：(市場識別類型 'HQ'/'EX', 模擬 market_id, 測試股票代碼, 描述備註)
    test_cases = [
        # 常規深滬市場試探（部分退市股如果在伺服器未被物理刪除，可能依舊保留在0或1）
        ('HQ', 0, '000549', '主板深市-原代碼試探(湘火炬A)'),
        ('HQ', 0, '394549', '主板深市-394自定義代碼試探'),

        # 擴展市場試探（通常退市股會劃分到特殊的 market_id，例如 2、31 或其他，這裡做盲測）
        ('EX', 2, '394549', '擴展市場ID=2-自定義代碼試探'),
        ('EX', 2, '000549', '擴展市場ID=2-自定義代碼試探'),
        ('EX', 31, '394549', '擴展市場ID=31-自定義代碼試探'),
        ('EX', 47, 'IFL8', '擴展市場對照組-中金所股指期貨(預期成功)'),
        ('HQ', 0, '000001', '標準市場對照組-平安銀行(預期成功)')
    ]

    print("\n--- 開始執行品種 K 線多通道多代碼試探 ---")

    for idx, (api_type, market_id, code, desc) in enumerate(test_cases):
        print(f"[*] 測試 [{idx + 1}/{len(test_cases)}]: {desc} ({api_type} -> 證券:{code}) ...")

        df_kline = None
        if api_type == 'HQ':
            df_kline = test_hq_kline(market_id, code)
        elif api_type == 'EX':
            df_kline = test_ex_kline(market_id, code)

        if df_kline is not None and not df_kline.empty:
            print(f"    [+] 獲取成功！成功拿到 {len(df_kline)} 條歷史 K 線。最新收盤價: {df_kline['close'].iloc[0]}")
            status = "SUCCESS"
            record_count = len(df_kline)
            sample_data = f"最新日期:{df_kline['date'].iloc[0]}, 收盤:{df_kline['close'].iloc[0]}"
        else:
            print("    [-] 未能獲取數據。")
            status = "FAILED"
            record_count = 0
            sample_data = "N/A"

        verification_logs.append({
            '測試編號': idx + 1,
            '接口類型': api_type,
            '市場ID': market_id,
            '證券代碼': code,
            '策略描述': desc,
            '測試結果狀態': status,
            '獲取記錄數': record_count,
            '樣本數據摘要': sample_data
        })

    # 步驟 3: 將測試日誌與掃描到的市場字典一同導出至 Excel
    print(f"\n[*] 正在產生驗證報告至 {LOG_OUTPUT_PATH} ...")
    with pd.ExcelWriter(LOG_OUTPUT_PATH, engine='openpyxl') as writer:
        pd.DataFrame(verification_logs).to_excel(writer, sheet_name='品種穿透測試日誌', index=False)
        if df_markets is not None:
            df_markets.to_excel(writer, sheet_name='擴展市場編碼字典', index=False)

    print(
        "[+] 驗證完成！請打開 Excel 檔案查看分析報告，特別是『擴展市場編碼字典』頁籤，它能告訴我們通達信當前開放的所有特殊板塊代碼。")


if __name__ == "__main__":
    main()