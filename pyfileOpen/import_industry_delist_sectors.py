import os
import sqlite3
import pandas as pd
from tqdm import tqdm

# 🎯 核心路径配置
DB_PATH = "E:/tdx_financial.db"
TXT_PATH = "D:/行业板块.txt"  # 定期更新的通达信行业文本
CSV_PATH = "D:/A股退市清单.csv"  # 定期更新的退市股票清单 CSV


def guess_market_prefix(code: str) -> str:
    """根据股票代码推断交易所前缀"""
    code = str(code).strip().zfill(6)
    if code.startswith(('60', '68', '88', '900')):
        return "SH" + code
    elif code.startswith(('00', '30', '200', '400', '430')):
        return "SZ" + code
    elif code.startswith(('83', '87', '88')):
        return "BJ" + code
    return "SZ" + code


def upgrade_and_init_db():
    """
    【防暴平滑升级引擎】
    安全升级数据库表结构：不丢弃原数据，自动补充缺失字段，重建联合主键索引
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 1. 创建底层表结构（如果不存在）
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS dataset_industry_sectors (
            industry_code TEXT NOT NULL,
            industry_name TEXT NOT NULL,
            stock_code TEXT NOT NULL,
            stock_name TEXT NOT NULL,
            full_stock_code TEXT NOT NULL,
            is_active INTEGER DEFAULT 1,
            list_date INTEGER,
            delist_date INTEGER,
            delist_reason TEXT,
            PRIMARY KEY (stock_code, industry_code)
        )
    """)

    # 2. 动态防守：检查并安全补充可能缺失的字段（兼容旧表数据）
    cursor.execute("PRAGMA table_info(dataset_industry_sectors);")
    existing_cols = [col[1] for col in cursor.fetchall()]

    needed_cols = {
        'list_date': 'INTEGER',
        'delist_date': 'INTEGER',
        'delist_reason': 'TEXT'
    }

    for col_name, col_type in needed_cols.items():
        if col_name not in existing_cols:
            print(f"⚙️ 检测到缺失字段 [{col_name}]，正在动态扩展表结构...")
            cursor.execute(f"ALTER TABLE dataset_industry_sectors ADD COLUMN {col_name} {col_type};")

    # 3. 创建核心高效查询索引
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_stock_code ON dataset_industry_sectors (stock_code);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_industry_code ON dataset_industry_sectors (industry_code);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_active_status ON dataset_industry_sectors (is_active);")

    conn.commit()
    conn.close()
    print("✅ 数据库表结构兼容性检查与平滑升级完成。")


def import_industry_txt():
    """
    🎯 功能一：导入/更新最新的行业板块 TXT 文本
    能够保留历史维护的上市/退市时间字段，只覆盖更新行业和股票基本信息
    """
    if not os.path.exists(TXT_PATH):
        print(f"⚠️ 警告：未找到行业文本文件 {TXT_PATH}，跳过行业 TXT 导入。")
        return

    print(f"\n📖 正在解析最新的通达信行业板块文本: {TXT_PATH} ...")
    try:
        df = pd.read_csv(TXT_PATH, sep=',', header=None,
                         names=['industry_code', 'industry_name', 'stock_code', 'stock_name'],
                         dtype=str, encoding='gbk')
    except UnicodeDecodeError:
        df = pd.read_csv(TXT_PATH, sep=',', header=None,
                         names=['industry_code', 'industry_name', 'stock_code', 'stock_name'],
                         dtype=str, encoding='utf-8')

    if df.empty:
        print("⚠️ 行业文本中无有效数据。")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 优化更新逻辑：使用事务增量写入
    updated_count = 0
    for _, row in tqdm(df.iterrows(), total=len(df), desc="更新行业分类数据"):
        ind_code = str(row['industry_code']).strip()
        ind_name = str(row['industry_name']).strip()
        stk_code = str(row['stock_code']).strip().zfill(6)
        stk_name = str(row['stock_name']).strip()

        if not ind_code or not stk_code:
            continue

        full_code = guess_market_prefix(stk_code)

        # UPSERT 逻辑：如果存在则更新行业名称、股票名称，同时保留已有的退市/上市日期
        cursor.execute("""
            INSERT INTO dataset_industry_sectors (industry_code, industry_name, stock_code, stock_name, full_stock_code, is_active)
            VALUES (?, ?, ?, ?, ?, 1)
            ON CONFLICT(stock_code, industry_code) DO UPDATE SET
                industry_name = excluded.industry_name,
                stock_name = excluded.stock_name,
                full_stock_code = excluded.full_stock_code,
                is_active = COALESCE(dataset_industry_sectors.is_active, 1);
        """, (ind_code, ind_name, stk_code, stk_name, full_code))

        updated_count += 1

    conn.commit()
    conn.close()
    print(f"🎉 行业分类文本更新成功，共处理记录 {updated_count} 条。")


def import_delist_csv():
    """
    🎯 功能二：导入/更新退市股票清单 CSV
    精准匹配库内股票，将其标记为 is_active = 0，并补齐退市原因及时间
    """
    if not os.path.exists(CSV_PATH):
        print(f"⚠️ 警告：未找到退市清单文件 {CSV_PATH}，跳过退市数据更新。")
        return

    print(f"\n📖 正在加载退市股票清单 CSV: {CSV_PATH} ...")
    try:
        df_delist = pd.read_csv(CSV_PATH, encoding='utf-8', dtype={'代码': str})
    except UnicodeDecodeError:
        df_delist = pd.read_csv(CSV_PATH, encoding='gbk', dtype={'代码': str})

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    delist_count = 0
    for _, row in tqdm(df_delist.iterrows(), total=len(df_delist), desc="同步退市资产标志"):
        raw_code = str(row['代码']).strip().zfill(6)
        stk_name = str(row['简称']).strip() if '简称' in row and not pd.isna(row['简称']) else "已退市股"
        reason = str(row['备注']).strip() if '备注' in row and not pd.isna(row['备注']) else "退市摘牌"

        # 提取退市年份（若有）
        delist_date = None
        if '退市年份' in row and not pd.isna(row['退市年份']):
            try:
                delist_date = int(str(row['退市年份']).strip() + "1231")
            except ValueError:
                delist_date = None

        full_code = guess_market_prefix(raw_code)

        # 检查该股票是否已经在表中
        cursor.execute("SELECT COUNT(*) FROM dataset_industry_sectors WHERE stock_code=?", (raw_code,))
        exists = cursor.fetchone()[0]

        if exists > 0:
            # 在原记录上打上退市标记并补齐原因
            cursor.execute("""
                UPDATE dataset_industry_sectors
                SET is_active = 0,
                    delist_reason = ?,
                    delist_date = COALESCE(?, delist_date)
                WHERE stock_code = ?
            """, (reason, delist_date, raw_code))
        else:
            # 较久远的历史退市股，插入到默认历史退市池
            cursor.execute("""
                INSERT INTO dataset_industry_sectors 
                (industry_code, industry_name, stock_code, stock_name, full_stock_code, is_active, delist_date, delist_reason)
                VALUES ('889999', '历史退市摘牌池', ?, ?, ?, 0, ?, ?)
                ON CONFLICT(stock_code, industry_code) DO UPDATE SET
                    is_active = 0,
                    delist_reason = excluded.delist_reason;
            """, (raw_code, stk_name, full_code, delist_date, reason))

        delist_count += 1

    conn.commit()
    conn.close()
    print(f"🎉 退市股票清单同步成功，共处理退市标记 {delist_count} 条。")


if __name__ == "__main__":
    print("🚀 开始执行数据库结构升级与常态化数据导入流程...")

    # 1. 表结构升级检查
    upgrade_and_init_db()

    # 2. 定期导入/更新行业分类
    import_industry_txt()

    # 3. 定期导入/更新退市股票信息
    import_delist_csv()

    print("\n✨ 全部任务执行完毕！现在表结构已支持完美的历史退市与行业映射同步。")