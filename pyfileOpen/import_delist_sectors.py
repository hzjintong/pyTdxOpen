import os
import sqlite3
import pandas as pd
from tqdm import tqdm

# 🎯 核心路径配置
DB_PATH = "E:/tdx_financial.db"
CSV_PATH = "./A股退市清单.csv"  # 请确保该 csv 放在脚本同级目录下，或指定绝对路径


def guess_market_prefix(code: str) -> str:
    code = str(code).strip().zfill(6)
    if code.startswith(('60', '68', '88', '900')):
        return "SH" + code
    elif code.startswith(('00', '30', '200', '400', '430')):
        return "SZ" + code
    return "SZ" + code


def merge_delist_list_to_industry_base():
    """
    🎯 核心策略：将退市清单中的股票融合、清洗，并注入到 dataset_industry_sectors 行业底座表中
    实现上市日期、退市日期、退市原因（备注）的全面要素集中化管理
    """
    if not os.path.exists(CSV_PATH):
        print(f"❌ 错误：未找到退市清单文件：{CSV_PATH}")
        return

    # 1. 读取 DeepSeek 提供的退市清单
    print("📖 正在加载退市清单种子池...")
    try:
        df_delist = pd.read_csv(CSV_PATH, encoding='utf-8', dtype={'代码': str})
    except UnicodeDecodeError:
        df_delist = pd.read_csv(CSV_PATH, encoding='gbk', dtype={'代码': str})

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 2. 动态检查并扩展表结构，为行业表追加退市原因备注字段（delist_reason）
    try:
        cursor.execute("ALTER TABLE dataset_industry_sectors ADD COLUMN delist_reason TEXT;")
        conn.commit()
        print("💡 提示：成功为行业底座表动态追加 [delist_reason (退市原因)] 因子字段。")
    except sqlite3.OperationalError:
        # 如果字段已存在，则静默跳过
        pass

    print("🚀 开始多源数据合流与时空要素对齐...")
    merge_count = 0

    # 3. 循环清洗并注入
    for _, row in tqdm(df_delist.iterrows(), total=len(df_delist), desc="退市资产要素并入中"):
        raw_code = str(row['代码']).strip().zfill(6)
        name = str(row['简称']).strip()
        reason = str(row['备注']).strip() if not pd.isna(row['备注']) else "未知原因退市"
        delist_year = str(row['退市年份']).strip()

        full_code = guess_market_prefix(raw_code)

        # 🔍 核心逻辑 A：先检查该退市股票是否已经在现有的行业表里了（针对近期退市但通达信txt还没剔除的）
        cursor.execute("SELECT industry_code, industry_name FROM dataset_industry_sectors WHERE stock_code=?", (raw_code,))
        industry_rows = cursor.fetchall()

        if industry_rows:
            # 如果存在，说明行业关系已知，更新其状态为退市(is_active=0)，并补齐退市原因
            for ind_code, ind_name in industry_rows:
                cursor.execute("""
                    UPDATE dataset_industry_sectors 
                    SET is_active = 0,
                        delist_reason = ?
                    WHERE industry_code = ? AND stock_code = ?
                """, (reason, ind_code, raw_code))
            merge_count += 1
        else:
            # 🔍 核心逻辑 B：如果不存在（如较久远的退市股“湘火炬A”），将其作为独立的退市种子归入“历史退市待定板块”
            # 方便您后期在同一个表里统一进行全要素的横向维护，绝不发生幸存者偏差的漏网
            # 默认给一个通用的历史退市板块代码：'889999'，名称：'历史退市摘牌池'
            cursor.execute("""
                INSERT OR REPLACE INTO dataset_industry_sectors 
                (industry_code, industry_name, stock_code, stock_name, full_stock_code, is_active, delist_reason)
                VALUES (?, ?, ?, ?, ?, 0, ?)
            """, ('889999', '历史退市摘牌池', raw_code, name, full_code, reason))
            merge_count += 1

    conn.commit()

    # 4. 统计合流后的成果
    cursor.execute("SELECT COUNT(*) FROM dataset_industry_sectors WHERE is_active = 0;")
    total_delist_in_db = cursor.fetchone()[0]
    conn.close()

    print(f"\n【🎉 核心量化退市资产链合流成功】")
    print(f"📊 数据库（{DB_PATH}）内：")
    print(f"  └─ 本次成功融合/清洗退市种子：{merge_count} 只")
    print(f"  └─ 当前底座表中已安全隔离、打上退市标记的非幸存者股票总量：{total_delist_in_db} 只")
    print(f"💡 后续行动建议：现在您可以直接通过一条 SQL，一键调出所有包含退市原因的股票池进行因子过滤了！")


if __name__ == "__main__":
    merge_delist_list_to_industry_base()