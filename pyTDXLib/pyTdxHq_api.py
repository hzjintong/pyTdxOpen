from pytdx.hq import TdxHq_API
import pandas as pd

# 1. 实例化 API 对象
api = TdxHq_API()

# 2. 连接服务器 (参数：服务器IP, 端口)
# 常用服务器：119.147.212.81 (深圳), 114.80.149.19 (上海)
if api.connect('103.251.85.58', 7709 ):  # IP地址我换了tdx中的行情主站的地址，端口7709正确可用
    print("连接成功！\n")

    # --- 功能 1: 获取五档行情 (get_security_quotes) ---
    # 市场代码：0 深圳，1 上海
    # 代码：股票代码
    print("--- 实时五档行情 ---")
    quotes = api.get_security_quotes([(0, '000001'), (1, '600000')])
    print(pd.DataFrame(quotes))

    # --- 功能 2: 获取K线数据 (get_security_bars) ---
    # 参数：类别(9日线, 8周线...), 市场代码, 股票代码, 起始位置, 数量
    # 类别说明：0 5分钟, 4 1小时, 9 日线, 11 周线
    print("\n--- 日K线数据 ---")
    bars = api.get_security_bars(9, 0, '000001', 0, 10)
    print(api.to_df(bars))

    # --- 功能 3: 获取分笔成交 (get_transaction_data) ---
    print("\n--- 分笔成交数据 ---")
    transaction = api.get_transaction_data(0, '000001', 0, 10)
    print(api.to_df(transaction))

    # --- 功能 4: 获取市场股票数量 (get_security_count) ---
    print("\n--- 深圳市场股票总数 ---")
    count = api.get_security_count(0)
    print(f"总数: {count}")

    # --- 功能 5: 获取股票列表 (get_security_list) ---
    # 参数：市场代码, 起始位置 (每次最多取1000条)
    print("\n--- 股票列表前5个 ---")
    stocks = api.get_security_list(0, 0)
    print(pd.DataFrame(stocks).head(5))

    # 3. 断开连接
    api.disconnect()
else:
    print("连接失败，请更换IP试一下")