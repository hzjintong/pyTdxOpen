from datetime import datetime
from op_pg_financial_db import PGFinancialDB

if __name__ == '__main__':
    print("=== 开始运行 PostgreSQL 17 财务数据运维与同步系统 ===")

    # 初始化 DB 引擎 (自动加载 config.json 并开启 psycopg3 连接池)
    db = PGFinancialDB(config_path="config.json")

    # 1. 确保 PostgreSQL 核心数据表、全量 DATE 规范类型及索引建立
    db.create_tables()

    # 2. 同步完整覆盖的 584 项专业财务字段字典表
    db.sync_field_description()

    # 3. 如果已有数据表是从 SQLite 迁移过来且 313/314/315 仍为 INTEGER，执行无损一键转换为 DATE 类型
    db.migrate_field_date_types()

    # 4. 执行高并发增量同步与变动审计日志导出
    time_stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    excel_log_path = f"E:/分析日志/PostgreSQL_财务变动日志_{time_stamp}.xlsx"

    db.sync_and_log_changes(
        start_year=1987,
        end_year=2030,
        export_excel=True,
        excel_path=excel_log_path
    )

    # 5. 安全释放连接池
    db.close()
    print("=== PostgreSQL 财务数据运维与格式清洗工作全部完成 ===")