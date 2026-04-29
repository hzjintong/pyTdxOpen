from op_tdx_financial_db import TDXFinancialDB

if __name__ == '__main__':
    CW_DIR = "d:/new_hxzq_hc/vipdoc/cw/"          # 通达信财务数据目录
    FIELD_TXT = "专业财务数据字段说明.txt"
    DB_PATH = "d:/tdx_financial.db"

    db = TDXFinancialDB(CW_DIR, FIELD_TXT, DB_PATH)

    # 第一步：创建表结构
    db.create_table()
    db.create_field_desc_table()  # 可选，存储字段说明

    # 第二步：全量导入（如 2000-2025）
    db.batch_import(start_year=1988, end_year=2026)

    # 后续增量更新（当目录下出现新的 gpcw 文件时执行）
    # db.incremental_update()