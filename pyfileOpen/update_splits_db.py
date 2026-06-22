import os
import sqlite3
import pandas as pd
from tqdm import tqdm
from pytdx.hq import TdxHq_API
import warnings

warnings.filterwarnings("ignore")

# 数据库文件路径
DB_PATH = r"D:\wsSHSZ_Data.db"


def init_database():
    """
    初始化 SQLite 数据库，建立标准的权息要素表与高性能联合索引
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 创建权息表 (完美包含：代码、日期、送股、配股、配股价、红利)
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

    # 建立联合主键索引，确保未来量化回测时根据[代码+日期]查询达到微秒级速度
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_code_date ON stock_splits (code, date);")
    conn.commit()
    conn.close()
    print(f"✅ SQLite 数据库 {DB_PATH} 及其权息索引表初始化/检查完毕。")


def fetch_all_active_stocks_from_tdx(api):
    """
    利用 PyTDX 直接调阅通达信服务器，安全抓取全市场 A 股代码清单
    """
    stock_list = []

    # 市场代码映射：0 代表深圳(SZ), 1 代表上海(SH)
    for market_id in [0, 1]:
        # 通达信单次最大拉取 1000 条，循环拉取直到取完
        start_idx = 0
        while True:
            df_block = api.get_security_list(market_id, start_idx)
            if df_block is None or len(df_block) == 0:
                break

            for item in df_block:
                code = item['code']
                # 过滤出正股群落（沪深主板、科创板、创业板、北交所）
                # 过滤掉债券、期权等（如果你未来需要补充债券分红，可以放开这里的过滤）
                if market_id == 0:
                    # 深圳股票过滤
                    if code.startswith(('00', '30', '002', '300', '000', '001', '003')):
                        stock_list.append((market_id, code, "SZ" + code))
                elif market_id == 1:
                    # 上海股票过滤
                    if code.startswith(('60', '68', '900')):
                        stock_list.append((market_id, code, "SH" + code))

            if len(df_block) < 1000:
                break
            start_idx += 1000

    return stock_list


def update_splits_from_tdx():
    """
    【PyTDX + SQLite 双引擎版】1992-2026 全要素权息数据全量补齐引擎
    """
    init_database()

    # 建立 PyTDX 高速连接通道 (使用通达信官方最稳定的主行情服务器)
    api = TdxHq_API(raise_exception=False)
    print("正在连接通达信高速二进制网络服务器...")

    # 尝试连接官方主服务器，如果失败可更换为 119.147.212.81
    if not api.connect('103.251.85.58', 7709):
        print("❌ 错误：无法连接通达信行情服务器，请检查网络或更换服务器IP。")
        return

    try:
        # 1. 安全获取全市场正股清单
        all_stocks = fetch_all_active_stocks_from_tdx(api)
        print(f"成功通过 PyTDX 获取全市场有效正股标的共: {len(all_stocks)} 只。")

        # 2. 连接本地数据库准备写入
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        success_count = 0
        insert_records_count = 0

        # 3. 循环个股调阅完整权息矩阵
        pbar = tqdm(all_stocks, desc="通达信权息全量同步中")
        for market_id, short_code, full_code in pbar:
            pbar.set_postfix(当前股票=full_code, 已成功拉取=success_count)

            # 关键高级接口：获取除权除息要素 (Get_XDXR_Info)
            # 该接口会一口气吐出该股票自上市第一天以来的所有历史分红、送股、配股明细！
            xdxr_data = api.get_xdxr_info(market_id, short_code)

            if xdxr_data is None or len(xdxr_data) == 0:
                continue

            # 提取并解析通达信标准二进制权息字段
            for row in xdxr_data:
                # 过滤并清洗出 YYYYMMDD 格式的整数日期
                year = row.get('year')
                month = row.get('month')
                day = row.get('day')
                if not year or not month or not day:
                    continue
                date_int = int(f"{year}{str(month).zfill(2)}{str(day).zfill(2)}")

                # 🎯【核心飞跃】完美捕获通达信标准5大除权因子（对应你的全部疑问）：
                song_ratio = float(row.get('song_ratio', 0.0))  # 每股送股/转增股数
                peigu_ratio = float(row.get('peigu_ratio', 0.0))  # 每股配股比例
                peigu_price = float(row.get('peigu_price', 0.0))  # 真实的配股价(元)
                dividend = float(row.get('fenhong', 0.0))  # 每股现金分红(税前/元)

                # 过滤掉没有任何股权变动的无意义噪音行
                if song_ratio == 0 and peigu_ratio == 0 and peigu_price == 0 and dividend == 0:
                    continue

                # 🛡️ 工业级写入：使用 INSERT OR REPLACE
                # 如果代码和日期已经存在，会自动用最新的官方二进制数据更新；如果不存在，则无缝追加
                cursor.execute("""
                    INSERT OR REPLACE INTO stock_splits 
                    (code, date, song_ratio, peigu_ratio, peigu_price, dividend)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (full_code, date_int, song_ratio, peigu_ratio, peigu_price, dividend))

                insert_records_count += 1

            success_count += 1

            # 💡 提示：通达信 TCP 二进制底层非常强悍且不封 IP，我们可以不加延时全力奔跑！
            # 如果你担心本地磁盘频繁 I/O，可以在循环外部统一 commit
            if success_count % 100 == 0:
                conn.commit()

        # 4. 收尾并提交所有事务
        conn.commit()

        # 统计当前数据库总战果
        cursor.execute("SELECT COUNT(*) FROM stock_splits;")
        total_in_db = cursor.fetchone()[0]
        conn.close()

        print(f"\n【🎉 转型大成功】通达信二进制历史权息数据已全量灌入本地 SQLite 数据库！")
        print(f"本次扫描处理了 {success_count} 只股票，在数据库中写入/更新了 {insert_records_count} 条权息链。")
        print(f"📊 当前数据库中总计储存权息记录：{total_in_db} 条。")

    except Exception as e:
        print(f"\n❌ 运行中发生非预期重大错误: {e}")
    finally:
        api.close()


def migrate_old_txt_backup_to_db(old_txt_path="wsSHSZ_SPLITs-old.txt"):
    """
    【救灾辅助工具】用于一键将你备份的包含‘债券和基金’的原始老文本，完好无损地合流到 SQLite 数据库中
    """
    if not os.path.exists(old_txt_path):
        print(f"未发现老备份文件 {old_txt_path}，跳过合流。")
        return

    print(f"发现含有债券/基金的历史备份文件 {old_txt_path}，正在执行跨架构合并...")
    try:
        # 自动探测编码并加载原文本
        df_old = None
        for enc in ['gbk', 'utf-8', 'gb18030', 'ansi']:
            try:
                df_old = pd.read_csv(old_txt_path, encoding=enc)
                df_old.columns = ['代码', '日期', '每股送股', '每股配股', '配股价', '每股红利']
                break
            except:
                continue

        if df_old is None or df_old.empty:
            print("读取备份文本失败，合流中止。")
            return

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        migrate_count = 0
        for _, row in df_old.iterrows():
            code = str(row['代码']).strip()
            date = int(row['日期'])

            # 如果是债券（如SH10... SH12...）或基金，它们不在 PyTDX 正股扫描名单里，正好在这里完美合流
            cursor.execute("""
                INSERT OR IGNORE INTO stock_splits 
                (code, date, song_ratio, peigu_ratio, peigu_price, dividend)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (code, date, float(row['每股送股']), float(row['每股配股']), float(row['配股价']),
                  float(row['每股红利'])))
            if cursor.rowcount > 0:
                migrate_count += 1

        conn.commit()
        conn.close()
        print(f"【🎉 救灾合流成功】已成功将老文件中的 {migrate_count} 条珍贵债券/基金历史合并入 SQLite 数据库中！")
    except Exception as e:
        print(f"合流备份时失败: {e}")


if __name__ == "__main__":
    # 执行全量升级
    update_splits_from_tdx()

    # 【可选】如果你想把之前的完整历史备份文本（含债券/基金）也安全地并进数据库，解开下面这行的注释运行一次即可：
    # migrate_old_txt_backup_to_db("wsSHSZ_SPLITs-old.txt")