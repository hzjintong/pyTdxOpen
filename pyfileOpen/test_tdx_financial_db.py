import sqlite3


def inspect_db_structure():
    conn = sqlite3.connect("D:/tdx_financial.db")
    cursor = conn.cursor()

    # 1. 打印数据库里所有的表名
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [r[0] for r in cursor.fetchall()]
    print("📊 您的数据库中包含以下表格:", tables)

    # 找到包含财务数据的表
    target_table = None
    for t in tables:
        if "financial" in t or "data" in t or "cw" in t:
            target_table = t
            break

    if not target_table:
        print("❌ 未找到明显的财务数据表，请检查是否尚未成功导入财务数据。")
        conn.close()
        return

    print(f"\n🔍 正在分析财务表 `{target_table}` 的前 2 条原始数据和字段名...")

    # 2. 获取表结构和样本
    cursor.execute(f"PRAGMA table_info({target_table});")
    columns = [col[1] for col in cursor.fetchall()]

    cursor.execute(f"SELECT * FROM {target_table} LIMIT 2;")
    rows = cursor.fetchall()

    if not rows:
        print(f"⚠️ 表 `{target_table}` 存在，但是里面是空的（没有数据）！")
    else:
        for row in rows:
            # 组装成字典打印，方便看哪个字段存了什么
            row_dict = dict(zip(columns, row))
            # 只打印前几个关键字段，防止 584 个字段刷屏
            mini_dict = {
                k: row_dict[k]
                for k in list(row_dict.keys())[:10]
                if k in row_dict
            }
            print("样本数据:", mini_dict)

    conn.close()


if __name__ == "__main__":
    inspect_db_structure()