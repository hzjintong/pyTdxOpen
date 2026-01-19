from pytdx.exhq import TdxExHq_API
import pandas as pd
import time

# 更加全面的扩展行情服务器列表（尝试不同的运营商和地区）
SERVERS = [
    ('139.159.241.5', 7727),
    ('112.74.214.43', 7727),
    ('120.25.218.6', 7727),
    ('43.139.173.246', 7727),
    ('159.75.90.107', 7727),
    ('106.52.170.195', 7727),
    ('139.9.191.175', 7727),
    ('175.24.47.69', 7727),
    ('150.158.9.199', 7727),
    ('150.158.20.127', 7727),
    ('49.235.119.116', 7727),
    ('49.234.13.160', 7727),
    ('116.205.143.214', 7727), # 可用服务器
    ('124.71.223.19', 7727),
    ('113.45.175.47', 7727),
    ('123.60.173.210', 7727),
]


def debug_ex_hq():
    api = TdxExHq_API()
    found_server = False

    print(f"开始测试，共有 {len(SERVERS)} 个服务器待检测...\n")

    for i, (ip, port) in enumerate(SERVERS):
        print(f"[{i + 1}/{len(SERVERS)}] 正在尝试连接: {ip}:{port} ...")

        try:
            # 设置连接超时时间（虽然pytdx没直接暴露超时，但我们可以手动控制）
            start_time = time.time()
            is_connected = api.connect(ip, port)

            if is_connected:
                print(f"  √ TCP连接建立成功 (耗时: {time.time() - start_time:.2f}s)")

                # 测试关键接口：获取市场列表
                markets = api.get_markets()

                if markets is not None and len(markets) > 0:
                    print(f"  ！！！ 发现可用服务器 ！！！")
                    print(f"  数据正常，该市场共包含 {len(markets)} 个板块。")

                    # 打印前 3 个板块信息确认数据真实性
                    df_m = api.to_df(markets)
                    print("  板块示例:")
                    print(df_m[['market', 'category', 'name']].head(3).to_string(index=False))

                    # 如果找到了可用的，我们在这里执行具体的业务逻辑测试
                    run_business_logic(api)

                    found_server = True
                    api.disconnect()
                    break  # 找到可用的就停止搜索
                else:
                    print("  × 警告：连接虽通，但接口返回空数据(None)，可能被限流或已关闭API访问。")
            else:
                print("  × 连接失败：服务器无响应。")

        except Exception as e:
            print(f"  × 发生异常: {str(e)}")

        finally:
            api.disconnect()
            print("-" * 50)

    if not found_server:
        print("\n结论：遍历了所有已知服务器，均无法获取扩展行情数据。")
        print("建议：1. 检查本地防火墙；2. 打开通达信电脑版，在登录界面点击“通讯设置”查看最新的扩展行情IP。")


def run_business_logic(api):
    """
    具体的业务测试逻辑，只有在服务器确认可用时才调用
    """
    print("\n--- 正在执行业务数据测试 ---")
    # 尝试获取一个通用的期货合约（通常 47 是中金所，ID可能因服务器而异）
    # 我们先随便取一个市场ID测试
    try:
        # 获取市场列表中的第一个市场ID
        m_list = api.get_markets()
        first_market_id = m_list[0]['market']

        print(f"尝试读取市场ID为 {first_market_id} 的代码列表...")
        instruments = api.get_instrument_info(first_market_id, 0, 5)
        if instruments:
            df_ins = api.to_df(instruments)
            print("获取代码成功:")
            print(df_ins[['code', 'name']].head(5))

            # 测试获取K线（取第一个代码）
            test_code = df_ins.iloc[0]['code']
            print(f"尝试获取 {test_code} 的K线...")
            bars = api.get_instrument_bars(9, first_market_id, test_code, 0, 3)
            if bars:
                print(api.to_df(bars))
    except Exception as e:
        print(f"业务测试报错: {e}")


if __name__ == "__main__":
    debug_ex_hq()