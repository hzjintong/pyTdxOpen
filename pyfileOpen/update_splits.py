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
    【安全极简接口】获取全市场 A 股股票清单
    """
    print("正在获取全市场 A 股股票清单...")
    for attempt in range(1, 4):
        try:
            df_info = ak.stock_info_a_code_name()
            if df_info is not None and not df_info.empty:
                codes = df_info['code'].astype(str).str.zfill(6).tolist()
                print(f"成功获取全市场共 {len(codes)} 只上市股票代码。")
                return codes
        except Exception as e:
            print(f"第 {attempt} 次获取股票清单失败，原因: {e}，正在尝试重连...")
            time.sleep(random.uniform(2, 4))

    print("❌ 严重错误：无法连接网络获取股票清单，请检查网络。")
    return []


def update_all_history_splits(local_file="wsSHSZ_SPLITs.txt"):
    """
    【带深度排错日志版】全量追溯引擎
    """
    df_local = None
    existing_stocks = set()

    # 1. 自适应编码读取本地已有权息文件
    if os.path.exists(local_file):
        print(f"发现本地文件 {local_file}，正在尝试读取...")
        for encoding in ['utf-8', 'gbk', 'gb18030', 'ansi']:
            try:
                df_local = pd.read_csv(local_file, encoding=encoding)
                if df_local.empty:
                    df_local = pd.DataFrame(columns=['代码', '日期', '每股送股', '每股配股', '配股价', '每股红利'])
                else:
                    df_local.columns = ['代码', '日期', '每股送股', '每股配股', '配股价', '每股红利']
                print(f"成功加载本地历史数据，共 {len(df_local)} 条记录。")
                break
            except:
                continue

        if df_local is None:
            print("【❌ 错误】本地文件存在但无法解析，程序紧急退出。")
            return

        if not df_local.empty:
            df_local['pure_code'] = df_local['代码'].str.replace('SH', '').str.replace('SZ', '').str.strip()
            existing_stocks = set(df_local['pure_code'].unique())
    else:
        print(f"未找到本地文件，将从零创建全新库: {local_file}")
        df_local = pd.DataFrame(columns=['代码', '日期', '每股送股', '每股配股', '配股价', '每股红利'])

    # 2. 获取股票列表
    stock_list = fetch_all_active_stocks_safe()
    if not stock_list:
        print("无法获取股票清单，维护中止。")
        return

    todo_stocks = [code for code in stock_list if code not in existing_stocks]
    print(f"全市场共有 {len(stock_list)} 只股票。本地已包含 {len(existing_stocks)} 只股票的历史。")
    print(f"本次需要为剩余的 【{len(todo_stocks)}】 只股票追溯历史分红...")

    if not todo_stocks:
        print("🎉 本地股票全量历史数据已经是最新状态，无需补齐。")
        return

    # 3. 循环个股爬取全量历史
    new_records = []
    success_count = 0
    error_logged = False  # 限制报错打印次数，防止刷屏

    pbar = tqdm(todo_stocks, desc="历史数据追溯中")
    for stock_code in pbar:
        pbar.set_postfix(当前股票=stock_code, 已成功拉取=success_count)

        try:
            # 调用个股历史分红实施接口
            df_history = ak.stock_history_dividend(stock=stock_code)

            # 【诊断哨点 1】如果拉回来的数据本身就是空，记录下来
            if df_history is None or df_history.empty:
                if not error_logged:
                    print(
                        f"\n[⚠️ 诊断警告] 股票 {stock_code} 接口返回了空数据(None或EmptyDataFrame)，可能是接口失效或触发反爬。")
                continue

            if stock_code.startswith('6') or stock_code.startswith('68') or stock_code.startswith('9'):
                full_code = "SH" + stock_code
            else:
                full_code = "SZ" + stock_code

            for _, row in df_history.iterrows():
                ex_date = row.get("除权除息日")
                if pd.isna(ex_date) or str(ex_date).strip() == "-" or not ex_date:
                    continue

                # 🛡️ 日期清洗
                date_clean = str(ex_date).split(" ")[0].replace("-", "").replace("/", "").strip()
                date_int = int(date_clean)

                # 🎯 尝试寻找最新变动后的可能字段名（多重组合防御）
                sg = float(row.get("送股比例(每10股)") or row.get("送股(股)") or 0)
                zr = float(row.get("转增比例(每10股)") or row.get("转增(股)") or 0)
                px = float(row.get("派息(每10股/元)") or row.get("派息(税前)(元)") or 0)

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

            # 控制频率，防止过快被封
            time.sleep(random.uniform(0.1, 0.2))

            # 定时批量落盘
            if success_count % 50 == 0 and new_records:
                df_batch = pd.DataFrame(new_records)
                if df_local is not None and not df_local.empty:
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
            # 【诊断哨点 2】关键致命处：如果发生未捕获异常，彻底打印出来，绝不悄悄死掉
            if not error_logged:
                print(f"\n[❌ 致命错误] 股票 {stock_code} 在解析时发生异常!")
                print(f"错误类型: {type(e).__name__}, 错误具体原因: {e}")
                if 'df_history' in locals() and df_history is not None and not df_history.empty:
                    print(f"当前接口返回的真实列名实际为: {list(df_history.columns)}")
                    print(f"当前第一行数据样板为:\n{df_history.iloc[0]}")
                error_logged = True  # 只打印前几次，避免刷屏崩溃
            continue

    # 4. 最终收尾拼合
    if df_local is not None and 'pure_code' in df_local.columns:
        df_local.drop(['pure_code'], axis=1, inplace=True)

    if new_records:
        df_final_new = pd.DataFrame(new_records)
        if df_local is not None and not df_local.empty:
            df_combined = pd.concat([df_local, df_final_new], ignore_index=True)
        else:
            df_combined = df_final_new
    else:
        df_combined = df_local

    if df_combined is not None and not df_combined.empty:
        df_combined.drop_duplicates(subset=['代码', '日期'], keep='last', inplace=True)
        df_combined.sort_values(by=['代码', '日期'], ascending=[True, False], inplace=True)
        df_combined.to_csv(local_file, index=False, encoding='utf-8')

    print(f"\n【🎉 流程结束】当前本地文本库总计记录数: {len(df_combined)} 条。")


if __name__ == "__main__":
    update_all_history_splits("wsSHSZ_SPLITs.txt")