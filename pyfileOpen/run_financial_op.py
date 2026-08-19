from datetime import datetime
from op_tdx_financial_db import TDXFinancialDB

if __name__ == '__main__':
    CW_DIR = "d:/new_hxzq_hc/vipdoc/cw/"          # 通达信财务数据目录
    FIELD_TXT = "专业财务数据字段说明.txt"
    DB_PATH = "E:/tdx_financial.db"

    db = TDXFinancialDB(CW_DIR, FIELD_TXT, DB_PATH)

    print("=== 开始重构并清洗财务数据库 ===")

    # 第一步：清空旧表并重新创建具备 INTEGER 类型日期字段的新表
    # db.reset_financial_table()
    # db.create_field_desc_table()

    # 第二步：全量清洗导入历史财务二进制文件（1988-2027）
    # 在导入过程中，field_313, 314, 315 会被自动转换为标准 20xxxxxx / 19xxxxxx 的 8位整数
    # db.batch_import(start_year=1988, end_year=2027)

    # 第三步：后续日常可直接运行的增量同步检测与变化日志导出
    time_stamp = datetime.now().strftime("%Y%m%d%H%M")
    db.sync_and_log_changes(
        start_year=1987,
        end_year=2030,
        export_excel=True,
        excel_path=f"E:/分析日志/财务数据变更日志_{time_stamp}.xlsx"
    )

    print("=== 财务数据格式化清洗与重构完成 ===")