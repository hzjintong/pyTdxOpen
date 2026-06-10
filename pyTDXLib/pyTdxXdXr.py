import pandas as pd
from pytdx.hq import TdxHq_API

# 潜在的可用行情服务器列表
SERVERS = [
    ('103.251.85.58', 7709),  # 华西证券
    ('103.251.85.28', 7709),
]


def fetch_and_inspect_xdxr(market_code: int, stock_code: str, servers: list = SERVERS):
    """
    获取指定股票的历史分红配股(除权除息)数据，并完整打印字段结构。

    :param market_code: 市场代码 (0:深圳, 1:上海)
    :param stock_code: 股票代码 (字符串, 如 '600036')
    :param servers: 服务器列表
    :return: 包含完整除权除息数据的 pd.DataFrame 或 None
    """
    api = TdxHq_API()
    df_result = None

    # 遍历服务器尝试连接
    for ip, port in servers:
        print(f"正在尝试连接服务器: {ip}:{port} ...")
        if api.connect(ip, port):
            print(f" 成功连接！正在请求 {stock_code} 的除权除息数据...")
            try:
                # 获取原始数据
                raw_data = api.get_xdxr_info(market_code, stock_code)

                if not raw_data:
                    print(f"⚠️ 未获取到该股票({stock_code})的数据，请检查代码或市场代码是否正确。")
                    return None

                # 转换为 DataFrame
                df_result = api.to_df(raw_data)
                break  # 成功获取数据，跳出服务器循环

            except Exception as e:
                print(f"❌ 请求数据时发生异常 ({ip}): {e}")
            finally:
                api.disconnect()
                print("已断开服务器连接。\n" + "-" * 50)
        else:
            print(f"❌ 无法连接到服务器: {ip}:{port}\n" + "-" * 50)

    # 如果所有服务器都失败
    if df_result is None:
        print("❌ 所有服务器尝试完毕，未能成功获取数据。")
        return None

    # ---- 开始打印和分析字段 ----
    print("\n" + "=" * 20 + " 字段结构分析 " + "=" * 20)

    # 1. 打印所有列名（解决中间被 ... 省略的问题）
    all_columns = df_result.columns.tolist()
    print(f"当前 pytdx 返回的完整列名 (共 {len(all_columns)} 个字段):")
    print(all_columns)
    print("-" * 54)

    # 2. 配置 Pandas 打印选项，使其不省略列，完整横向输出
    pd.set_option('display.max_columns', None)  # 显示所有列
    pd.set_option('display.width', 1000)  # 设置足够宽的横向画布
    pd.set_option('display.unicode.ambiguous_as_wide', True)  # 辅助对齐
    pd.set_option('display.unicode.east_asian_width', True)  # 辅助对齐

    # 3. 打印前 10 行样本数据
    print("最新 10 条样本数据（完整列视图）：")
    print(df_result.head(10))
    print("=" * 54)

    return df_result


if __name__ == "__main__":
    # 测试：获取 上海(1) 招商银行(600036) 的除权除息数据
    # 如果你想试 深圳(0) 平安银行(000001)，直接修改入参即可
    df_xdxr = fetch_and_inspect_xdxr(market_code=1, stock_code='600036')
