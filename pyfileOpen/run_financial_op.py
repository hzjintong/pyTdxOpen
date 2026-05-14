from datetime import datetime
from op_tdx_financial_db import TDXFinancialDB

if __name__ == '__main__':
    CW_DIR = "d:/new_hxzq_hc/vipdoc/cw/"          # 通达信财务数据目录
    FIELD_TXT = "专业财务数据字段说明.txt"
    DB_PATH = "d:/tdx_financial.db"

    db = TDXFinancialDB(CW_DIR, FIELD_TXT, DB_PATH)

    # 第一步：创建表结构
    # db.create_table()
    # db.create_field_desc_table()  # 可选，存储字段说明
    # db.reset_financial_table()

    # 第二步：全量导入（如 2000-2025）
    # db.batch_import(start_year=1988, end_year=2027)

    # 后续增量更新（当 cw 目录下出现新的 gpcw 文件时执行）
    db.incremental_update()

    # 更新字段说明表
    db.sync_field_desc_table()

    # 新的执行增量同步，检测所有文件的变化，并输出 Excel 日志
    time_stamp = datetime.now().strftime("%Y%m%d%H%M")
    db.sync_and_log_changes(
        start_year=1988,
        end_year=2030,
        export_excel=True,
        excel_path=f"财务数据变更日志_{time_stamp}.xlsx"
    )

    # 扫描重复记录并导出 Excel
    db.scan_duplicates(
        start_year=1988,
        end_year=2030,
        output_excel=f"重复股票检测报告_{time_stamp}.xlsx",
        tolerance=1e-6  # 容忍度
    )