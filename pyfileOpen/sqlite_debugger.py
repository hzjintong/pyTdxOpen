import os
import sqlite3
import sys


def print_divider(char="-", length=80):
    print(char * length)


def get_db_schema(conn):
    """获取数据库中的所有表和索引信息"""
    cursor = conn.cursor()

    # 查询所有表
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';"
    )
    tables = [row[0] for row in cursor.fetchall()]

    # 查询所有索引
    cursor.execute(
        "SELECT name, tbl_name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%';"
    )
    indexes = cursor.fetchall()

    return tables, indexes


def display_schema(tables, indexes):
    """美化显示结构信息"""
    print("\n" + "=" * 40)
    print(f" 📊 数据库结构信息 (Tables & Indexes)")
    print("=" * 40)

    print("\n[ 数据表 (Tables) ]")
    if tables:
        for i, table in enumerate(tables, 1):
            print(f"  {i}. {table}")
    else:
        print("  (无数据表)")

    print("\n[ 索引 (Indexes) ]")
    if indexes:
        for i, (idx, tbl) in enumerate(indexes, 1):
            print(f"  {i}. {idx} -> 作用于表: {tbl}")
    else:
        print("  (无索引)")
    print_divider("=", 40)
    print()


def pretty_print_results(headers, rows):
    """美化打印前20行数据（自动对齐）"""
    if not rows:
        print("\n查询成功，但未返回任何记录。")
        return

    # 计算每列的最大宽度，确保标题和内容都能对齐
    col_widths = [len(str(h)) for h in headers]
    for row in rows:
        for idx, cell in enumerate(row):
            val_str = str(cell) if cell is not None else "NULL"
            if len(val_str) > col_widths[idx]:
                col_widths[idx] = len(val_str)

    # 限制单列最大宽度，防止某列文本过长导致刷屏
    col_widths = [min(width, 30) for width in col_widths]

    # 构建行打印格式
    format_str = (
        " | ".join([f"{{:<{width}}}" for width in col_widths])
    ) + " |"
    format_str = "| " + format_str

    print_divider("-")
    # 打印表头
    print(format_str.format(*[str(h)[:30] for h in headers]))
    print_divider("-")

    # 打印数据
    for row in rows:
        clean_row = []
        for cell in row:
            val_str = str(cell) if cell is not None else "NULL"
            # 截断过长内容
            if len(val_str) > 30:
                val_str = val_str[:27] + "..."
            clean_row.append(val_str)
        print(format_str.format(*clean_row))

    print_divider("-")


def main():
    print("欢迎使用 SQLite 交互式 SQL 调试工具！")
    print_divider("=")

    # 1. 获取并验证数据库路径
    while True:
        db_path = input("请输入 SQLite 数据库文件路径 (如: ./data.db): ").strip()

        # 去除用户可能不小心输入的两端引号
        db_path = db_path.strip("'\"")

        if not db_path:
            print("路径不能为空，请重新输入。")
            continue

        if not os.path.exists(db_path):
            print(f"❌ 错误: 文件 '{db_path}' 不存在，请检查路径。")
            continue

        # 尝试连接
        conn = sqlite3.connect(db_path)

        try:
            # 测试连接
            # 尝试执行一个简单查询验证它确实是数据库文件
            conn.execute("SELECT 1")
            break
        except sqlite3.DatabaseError:
            print(
                "❌ 错误: 该文件似乎不是一个有效的 SQLite 数据库文件，请重新输入。"
            )
            if "conn" in locals():
                conn.close()

    # 2. 列出表和索引
    try:
        tables, indexes = get_db_schema(conn)
        display_schema(tables, indexes)
    except Exception as e:
        print(f"读取数据库结构时出错: {e}")

    # 3. 进入 SQL 交互循环
    print("💡 提示:")
    print("   - 输入完成按 [回车] 键执行 SQL 语句。")
    print("   - 无论输错与否，均不会崩溃，可继续输入。")
    print("   - 随时按 [Ctrl + Q] 再按 [回车]（或直接输入 exit）退出。")
    print_divider("=")

    while True:
        try:
            sql = input("\nSQL> ").strip()
        except (KeyboardInterrupt, EOFError):
            # 捕捉常见的 Ctrl+C 或 Ctrl+D 优雅提示退出
            sql = "exit"

        # 处理退出逻辑
        # 注：在标准的 Windows/Linux 控制台中，Ctrl+Q 组合键在 Python 的 input() 中
        # 通常会表现为特定字符（如 \x11），或者用户可能会直接输入 'ctrl+q'。
        # 这里做了兼容处理：支持输入 exit、quit、\x11 或是 字母 ctrl+q
        if (
            sql.lower() in ("exit", "quit", "ctrl+q")
            or sql == "\x11"
            or sql.lower() == "ctrl+q"
        ):
            confirm = input("确定要退出工具吗？(y/n): ").strip().lower()
            if confirm == "y":
                print("谢谢使用，再见！")
                conn.close()
                sys.exit(0)
            else:
                continue

        if not sql:
            continue

        # 执行 SQL
        cursor = conn.cursor()
        try:
            cursor.execute(sql)

            # 判断是否是查询语句 (有返回数据)
            if cursor.description:
                headers = [description[0] for description in cursor.description]
                # 仅获取前 20 行记录
                rows = cursor.fetchmany(20)

                print(f"\n===== 查询结果 (展示前 20 行) =====")
                pretty_print_results(headers, rows)

                # 给出总数提示（如果在前20行拿完了，顺便打印出来）
                if len(rows) < 20:
                    print(f"总计返回记录数: {len(rows)} 条")
                else:
                    print("⚠️ 注意: 结果可能超过 20 行，以上仅展示前 20 行。")

            else:
                # DDL 或 DML 语句 (如 INSERT, UPDATE, CREATE 等)
                conn.commit()
                print(
                    f"\n✅ 执行成功。影响行数: {cursor.rowcount} 行。数据已提交 (Commit)。"
                )

        except sqlite3.Error as e:
            print(f"\n❌ SQL 执行错误: {e}")
        except Exception as e:
            print(f"\n❌ 系统错误: {e}")
        finally:
            cursor.close()


if __name__ == "__main__":
    main()