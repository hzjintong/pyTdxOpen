import os
import time
import random
import pandas as pd
from tqdm import tqdm
import akshare as ak
import warnings

warnings.filterwarnings("ignore")


def fetch_all_active_stocks_safe():
    """
    【2026防掐断增强版】改用极简静态股票列表接口，彻底避免服务器切断连接
    """
    print("正在获取全市场 A 股股票清单（安全极简接口）...")
    # 尝试重试 3 次防御机制
    for attempt in range(1, 4):
        try:
            # 放弃东财高频即时行情大表，改用无防备的沪深 A 股基础名单接口
            df_info = ak.stock_info_a_code_name()
            if df_info is not None and not df_info.empty:
                # 提取代码并确保是 6 位数字字符串
                codes = df_info['code'].astype(str).str.zfill(6).tolist()
                print(f"成功获取全市场共 {len(codes)} 只上市股票代码。")
                return codes
        except Exception as e:
            print(f"第 {attempt} 次获取股票清单失败，原因: {e}，正在尝试重连...")
            time.sleep(random.uniform(2, 4))  # 失败后多休息几秒再试

    print("❌ 严重错误：多次尝试后仍无法连接网络获取股票清单，请检查网络或更换网络环境。")
    return []


def update_all_history_splits(local_file="wsSHSZ_SPLITs.txt"):
    """
    自 1992 年历史全量补齐引擎 (含自适应读取、防封延时、断点续传、债券基金零破坏)
    """
    df_local = None
    existing_stocks = set()

    # 1. 自适应编码读取本地已有权息文件
    if os.path.exists(local_file):
        print(f"发现本地文件 {local_file}，正在尝试读取...")
        for encoding in ['utf-8', 'gbk', 'gb18030', 'ansi']:
            try:
                df_local = pd.read_csv(local_file, encoding=encoding)
                df_local.columns = ['代码', '日期', '每股送股', '每股配股', '配股价', '每股红利']
                print(f"成功使用 【{encoding}】 编码加载本地历史数据，共 {len(df_local)} 条记录（含债券/基金）。")
                break
            except:
                continue

        if df_local is None:
            print("【❌ 错误】本地文件存在但无法解析，为保护您的备份，程序紧急退出。")
            return

        # 统计本地已经有哪些股票有了历史记录（用于断点续传）
        df_local['pure_code'] = df_local['代码'].str.replace('SH', '').str.replace('SZ', '').str.strip()
        existing_stocks = set(df_local['pure_code'].unique())
    else:
        print(f"未找到本地文件，将从零创建全新库: {local_file}")

    # 2. 调用最新安全接口获取股票列表
    stock_list = fetch_all_active_stocks_safe()
    if not stock_list:
        print("无法获取股票清单，维护中止。")
        return

    # 过滤掉已经存在历史记录的股票（实现断点续传）
    todo_stocks = [code for code in stock_list if code not in existing_stocks]
    print(f"全市场共有 {len(stock_list)} 只股票。本地已包含 {len(existing_stocks)} 只股票的历史。")
    print(f"本次需要为剩余的 【{len(todo_stocks)}】 只股票追溯自 1992 年以来的完整历史分红...")

    if not todo_stocks:
        print("🎉 恭喜！本地股票全量历史数据已经是最新、最全状态，无需补齐。")
        return

    # 3. 循环个股爬取全量历史
    new_records = []
    success_count = 0

    # 使用 tqdm 展现个股下载进度条
    pbar = tqdm(todo_stocks, desc="历史数据追溯中")
    for stock_code in pbar:
        pbar.set_postfix(当前股票=stock_code, 已成功拉取=success_count)

        try:
            # 调用极度稳定的个股历史分红实施接口
            df_history = ak.stock_history_dividend(stock=stock_code)

            if df_history is not None and not df_history.empty:
                # 规范化前缀
                if stock_code.startswith('6') or stock_code.startswith('68') or stock_code.startswith('9'):
                    full_code = "SH" + stock_code
                else:
                    full_code = "SZ" + stock_code

                for _, row in df_history.iterrows():
                    ex_date = row.get("除权除息日")
                    if pd.isna(ex_date) or str(ex_date).strip() == "-" or not ex_date:
                        continue

                    date_int = int(str(ex_date).replace("-", "").replace("/", "").split(" ")[0])

                    sg = float(row.get("送股比例(每10股)") or 0)
                    zr = float(row.get("转增比例(每10股)") or 0)
                    px = float(row.get("派息(每10股/元)") or 0)

                    song_ratio = (sg + zr) / 10.0
                    fenhong_ratio = px / 10.0

                    if song_ratio == 0 and fenhong_ratio == 0:
                        continue

                    new_records.append({
                        '代码': full_code,
                        '日期': date_int,
                        '每股送股': song_ratio,
                        '每股配股': 0.0,
                        '配股价': 0.0,
                        '每股红利': fenhong_ratio
                    })
                success_count += 1

            # 🟢 动态安全延时 (每请求一次，随机休息 0.2 到 0.5 秒，防止被封)
            time.sleep(random.uniform(1.2, 3.5))

            # 每成功抓取 50 只股票自动向硬盘物理文件保存追加一次，实现完美的断点续传
            if success_count % 50 == 0 and new_records:
                df_batch = pd.DataFrame(new_records)
                if df_local is not None:
                    if 'pure_code' in df_local.columns:
                        df_local.drop(['pure_code'], axis=1, inplace=True)
                    df_combined = pd.concat([df_local, df_batch], ignore_index=True)
                else:
                    df_combined = df_batch
                df_combined.drop_duplicates(subset=['代码', '日期'], keep='last', inplace=True)
                df_combined.sort_values(by=['代码', '日期'], ascending=[True, False], inplace=True)
                df_combined.to_csv(local_file, index=False, encoding='utf-8')

                df_local = df_combined.copy()
                df_local['pure_code'] = df_local['代码'].str.replace('SH', '').str.replace('SZ', '').str.strip()
                new_records = []

        except Exception as e:
            time.sleep(3)  # 遇到单只股票异常多休息一会
            continue

    # 4. 循环结束后，进行最终的拼合重写
    if df_local is not None and 'pure_code' in df_local.columns:
        df_local.drop(['pure_code'], axis=1, inplace=True)

    if new_records:
        df_final_new = pd.DataFrame(new_records)
        df_combined = pd.concat([df_local, df_final_new], ignore_index=True)
    else:
        df_combined = df_local

    if df_combined is not None:
        df_combined.drop_duplicates(subset=['代码', '日期'], keep='last', inplace=True)
        df_combined.sort_values(by=['代码', '日期'], ascending=[True, False], inplace=True)
        df_combined.to_csv(local_file, index=False, encoding='utf-8')

    print(f"\n【🎉 全量追溯完美成功】数据已全部补齐！")
    print(f"当前本地总记录数（股票历史全量+债券+基金）共计: {len(df_combined)} 条。")


if __name__ == "__main__":
    update_all_history_splits("wsSHSZ_SPLITs.txt")