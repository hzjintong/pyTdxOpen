from pytdx.exhq import TdxExHq_API
import pandas as pd

# 1. 定义多个潜在的扩展行情服务器 (IP, Port)
# 这些是通达信常用的扩展行情节点，如果一个不行会尝试下一个
SERVERS = [
    ('119.4.167.144', 7721),    # 华西证券的扩展行情主机 CONNECT.cfg（编码gb18030）中 DSHOST信息组下
    ('116.205.143.214', 7727),  # 可用服务器
    ('119.147.164.60', 7727),
    ('124.71.187.122', 7727),
    ('47.107.75.159', 7727),
    ('103.251.85.58', 7727)
]


def test_ex_hq():
    api = TdxExHq_API()
    connected = False

    # --- 步骤 1: 尝试连接可用的服务器 ---
    print("正在寻找可用的扩展行情服务器...")
    for ip, port in SERVERS:
        try:
            if api.connect(ip, port):
                print(f"成功连接到服务器: {ip}:{port}")
                # 尝试获取市场列表，确认服务器真的能给数据
                markets = api.get_markets()
                if markets is not None and len(markets) > 0:
                    connected = True
                    break
                else:
                    print(f"服务器 {ip} 连接成功但返回数据为空，尝试下一个...")
                    api.disconnect()
        except Exception as e:
            print(f"连接 {ip} 失败: {e}")

    if not connected:
        print("错误：无法找到可用的扩展行情服务器，请检查网络或稍后再试。")
        return

    try:
        # --- 步骤 2: 打印市场列表 (核心调试步) ---
        # 这一步非常重要，你需要从这里找到你想查询的市场 ID
        print("\n--- 1. 获取市场列表 (前10个) ---")
        markets = api.get_markets()
        df_markets = api.to_df(markets)
        print(df_markets.head(10))

        # 假设我们要找“中金所”或“上期所”
        # 通常：47 是中金所(CFFEX), 29 或 30 是大商所/上期所
        # 我们随机取一个市场ID和代码进行测试
        target_market = 47  # 中金所
        # 注意：期货合约请使用当前活跃的合约，例如 IF + 年月
        # 或者使用连续合约代码（如果服务器支持），这里改用 IFL8 (假设) 或当前月份
        target_code = 'IFL8'

        # --- 步骤 3: 获取特定品种行情 ---
        print(f"\n--- 2. 查询品种行情 ({target_market}, {target_code}) ---")
        quote = api.get_instrument_quote(target_market, target_code)

        # 调试：打印原始返回类型和内容
        print(f"原始返回类型: {type(quote)}")
        if quote:
            print("查询成功，结果如下：")
            print(pd.DataFrame(quote))
        else:
            print(f"查询失败：品种 {target_code} 在市场 {target_market} 中未找到或已过期。")
            print("建议：请从上面的‘市场列表’中确认市场ID，并检查合约代码是否正确。")

        # --- 步骤 4: 获取K线数据 ---
        print(f"\n--- 3. 获取日K线数据 ({target_code}) ---")
        # 参数: 9 (日线), 市场ID, 代码, 起始位置, 数量
        bars = api.get_instrument_bars(9, target_market, target_code, 0, 5)
        if bars:
            print(api.to_df(bars))
        else:
            print("获取K线失败。")

    finally:
        api.disconnect()
        print("\n已断开连接。")


if __name__ == "__main__":
    test_ex_hq()