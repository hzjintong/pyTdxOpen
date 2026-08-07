import os
import sqlite3
import pandas as pd
from tqdm import tqdm
from pytdx.hq import TdxHq_API
import warnings

warnings.filterwarnings("ignore")

# 🎯 你的共享财务数据库路径
DB_PATH = "E:/tdx_financial.db"

# 你测试验证通过的高速行情服务器列表
SERVERS = [
    ('103.251.85.58', 7709),
    ('103.251.85.28', 7709),
    ('218.75.126.9', 7709)
]


def init_splits_table_in_financial_db():
    """
    检查并挂载权息扩展表
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stock_splits (
            code TEXT NOT NULL,
            date INTEGER NOT NULL,
            song_ratio REAL DEFAULT 0.0,
            peigu_ratio REAL DEFAULT 0.0,
            peigu_price REAL DEFAULT 0.0,
            dividend REAL DEFAULT 0.0,
            PRIMARY KEY (code, date)
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_splits_code_date ON stock_splits (code, date);")
    conn.commit()
    conn.close()


def safe_float(value) -> float:
    """🛡️ 空值安全防御底座：防止 float(None) 崩溃"""
    if value is None or pd.isna(value):
        return 0.0
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0


def extract_full_stocks_from_local_cw() -> list:
    """
    🎯【核心重构】100% 对齐你的真实财务数据库结构
    直接拉取你本地导入的所有 A 股股票种子清单，通过代码首位智能划分市场
    """
    stock_pool = set()

    if os.path.exists(DB_PATH):
        try:
            conn = sqlite3.connect(DB_PATH)
            # 🎯 1. 对齐你的真实字段名 stock_code 和表名 financial_data
            # df_codes = pd.read_sql("SELECT DISTINCT stock_code FROM financial_data WHERE stock_code IS NOT NULL", conn)
            df_codes = pd.read_sql("SELECT DISTINCT stock_code FROM dataset_industry_sectors WHERE stock_code IS NOT NULL", conn)
            conn.close()

            raw_codes = df_codes['stock_code'].astype(str).str.strip().tolist()

            for code in raw_codes:
                if not code or len(code) != 6:
                    continue

                # 🎯 2. 智能化市场划分法则：
                # 沪市主板(60)、科创板(68) -> 上海(market_id=1, 存入叫 SHxxxxxx)
                if code.startswith(('60', '68')):
                    stock_pool.add((1, code, "SH" + code))
                # 北交所上市正股(83, 87, 88) -> 底层属于上海流传输(market_id=1, 存入叫 BJxxxxxx 方便你识别)
                elif code.startswith(('83', '87', '88')):
                    stock_pool.add((1, code, "BJ" + code))
                # 深市主板(00)、创业板(30) -> 深圳(market_id=0, 存入叫 SZxxxxxx)
                elif code.startswith(('00', '30')):
                    stock_pool.add((0, code, "SZ" + code))
                # 其余特例或老三板等统归入深圳流探测
                else:
                    stock_pool.add((0, code, "SZ" + code))

            if stock_pool:
                print(f"📁 [策略 A 提取成功]：已成功从本地财务表中捞出 {len(stock_pool)} 只唯一股票种子代码！")
                return sorted(list(stock_pool))
        except Exception as e:
            print(f"⚠️ [策略 A 尝试失败]: {e}")

    print("⚠️ 无法读取财务表，启动 [策略 B] 网络兜底...")
    return []


def fetch_all_active_stocks_by_market_scan(api):
    """
    【策略 B 网络兜底】多页分页扫描
    """
    stock_list = []
    for market_id in [0, 1]:
        for page in range(10):
            start_idx = page * 1000
            df_block = api.get_security_list(market_id, start_idx)
            if df_block is None or len(df_block) == 0:
                break
            for item in df_block:
                code = str(item['code']).strip()
                if market_id == 0 and code.startswith(('00', '30')):
                    stock_list.append((market_id, code, "SZ" + code))
                elif market_id == 1:
                    if code.startswith(('60', '68')):
                        stock_list.append((market_id, code, "SH" + code))
                    elif code.startswith(('83', '87', '88')):
                        stock_list.append((market_id, code, "BJ" + code))
            if len(df_block) < 1000:
                break
    return sorted(list(set(stock_list)))


def main_sync_splits_to_db():
    # 1. 挂载或创建表
    init_splits_table_in_financial_db()

    # 2. 从本地数据资产库提取最完整股票列表
    todo_stocks = extract_full_stocks_from_local_cw()

    api = TdxHq_API(raise_exception=False)
    connected = False

    print("正在连接通达信高速二进制网络服务器...")
    for ip, port in SERVERS:
        if api.connect(ip, port):
            print(f" 成功建立专属长连接通道！")
            connected = True
            break

    if not connected:
        print("❌ 错误：无法连接通达信行情服务器。")
        return

    try:
        # 如果策略 A 没提取到，才用策略 B
        if not todo_stocks:
            todo_stocks = fetch_all_active_stocks_by_market_scan(api)

        print(f"📊 最终锁定的全市场有效正股总数: {len(todo_stocks)} 只。")

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        success_count = 0
        insert_records_count = 0

        # 3. 循环拉取除权数据
        pbar = tqdm(todo_stocks, desc="权息合流同步中")
        for market_id, short_code, full_code in pbar:
            pbar.set_postfix(当前股票=full_code, 已成功拉取=success_count)

            # 通达信网络底层协议：无论是 SH 还是 BJ 股票，网络请求时 market_id 必须为 1
            xdxr_data = api.get_xdxr_info(market_id, short_code)

            if xdxr_data is None or len(xdxr_data) == 0:
                continue

            for row in xdxr_data:
                year = row.get('year')
                month = row.get('month')
                day = row.get('day')
                if not year or not month or not day:
                    continue
                date_int = int(f"{year}{str(month).zfill(2)}{str(day).zfill(2)}")

                song_ratio = safe_float(row.get('songzhuangu'))
                peigu_ratio = safe_float(row.get('peigu'))
                peigu_price = safe_float(row.get('peigujia'))
                dividend = safe_float(row.get('fenhong'))

                # 过滤掉非分配日的空数据噪音
                if song_ratio == 0.0 and peigu_ratio == 0.0 and peigu_price == 0.0 and dividend == 0.0:
                    continue

                # INSERT OR REPLACE 确保增量更新和去重覆盖
                cursor.execute("""
                    INSERT OR REPLACE INTO stock_splits 
                    (code, date, song_ratio, peigu_ratio, peigu_price, dividend)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (full_code, date_int, song_ratio, peigu_ratio, peigu_price, dividend))

                insert_records_count += 1

            success_count += 1
            if success_count % 100 == 0:
                conn.commit()

        conn.commit()

        cursor.execute("SELECT COUNT(*) FROM stock_splits;")
        total_in_db = cursor.fetchone()[0]
        conn.close()

        print(f"\n【🎉 完美合流大成功】全量历史权息数据已成功归于财务数据库中！")
        print(f"📊 数据库（{DB_PATH}）内：")
        print(f"  └─ 本次扫描处理个股：{success_count} 只")
        print(f"  └─ 本次新灌入/修正权息链：{insert_records_count} 条")
        print(f"  └─ 当前权息扩展表总记录数：{total_in_db} 条")

    except Exception as e:
        print(f"\n❌ 运行中发生未预料的重大错误: {e}")
    finally:
        api.close()


if __name__ == "__main__":
    main_sync_splits_to_db()