import os
import re
import sqlite3
from struct import unpack, calcsize
from datetime import datetime
from typing import Dict, List, Tuple, Optional


class TDXFinancialDB:
    """通达信财务数据 -> SQLite 批量导入与更新"""

    def __init__(self, cw_dir: str, field_file: str, db_path: str = "tdx_financial.db"):
        """
        Args:
            cw_dir: 通达信财务数据目录 (含 gpcw*.dat)
            field_file: 专业财务数据字段说明.txt 路径
            db_path: SQLite 数据库文件路径
        """
        self.cw_dir = cw_dir
        self.field_file = field_file
        self.db_path = db_path
        self.field_names: Dict[int, str] = {}
        self._load_field_names()

    def _load_field_names(self):
        """解析字段说明文件，得到 field_id -> 字段名 的映射"""
        try:
            with open(self.field_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                # 匹配 "数字--字段名" 或 "数字.--字段名"
                match = re.match(r'(\d+)\.?--(.+)', line)
                if match:
                    fid = int(match.group(1))
                    name = match.group(2).strip()
                    self.field_names[fid] = name
        except Exception as e:
            print(f"加载字段说明文件失败: {e}")
            # 备用：全部命名为 field_N
            for i in range(1, 585):
                self.field_names[i] = f"field_{i}"

    def create_table(self):
        """创建财务数据表及索引"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # 构建所有字段的列定义
        cols = ["id INTEGER PRIMARY KEY AUTOINCREMENT",
                "stock_code TEXT NOT NULL",
                "report_date INTEGER NOT NULL"]
        for fid in range(1, 585):
            # 列名统一为 field_编号，避免特殊字符
            col_name = f"field_{fid}"
            cols.append(f"{col_name} REAL")
        cols.append("UNIQUE(stock_code, report_date)")

        create_sql = f"CREATE TABLE IF NOT EXISTS financial_data ({', '.join(cols)})"
        cursor.execute(create_sql)

        # 建立索引
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_fin_data_stock ON financial_data(stock_code)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_fin_data_date ON financial_data(report_date)")

        conn.commit()
        conn.close()
        print("数据库表 financial_data 及索引创建完毕。")

    def _parse_file_stocks(self, file_path: str) -> List[Tuple[str, int]]:
        """
        解析单个 gpcw.dat 文件，返回所有股票的 (stock_code, foa) 列表
        """
        stocks = []
        try:
            with open(file_path, 'rb') as f:
                header_size = calcsize("<3h1H3L")
                header = f.read(header_size)
                stock_header = unpack("<3h1H3L", header)
                max_count = stock_header[3]

                stock_item_size = calcsize("<6s1c1L")
                for i in range(max_count):
                    f.seek(header_size + i * stock_item_size)
                    data = f.read(stock_item_size)
                    if len(data) < stock_item_size:
                        break
                    code_bytes, flag, foa = unpack("<6s1c1L", data)
                    code = code_bytes.decode('gbk', errors='ignore').strip('\x00')
                    stocks.append((code, foa))
        except Exception as e:
            print(f"解析文件索引失败 {file_path}: {e}")
        return stocks

    def _read_stock_data(self, file_path: str, foa: int) -> Optional[Tuple[float, ...]]:
        """读取指定偏移处的 584 个 float"""
        try:
            with open(file_path, 'rb') as f:
                f.seek(foa)
                # 先尝试读取 584 个 float
                data_size = 584 * 4
                raw = f.read(data_size)
                if len(raw) < data_size:
                    # 降级至 264 个 float，不足补 0
                    raw = f.read(264 * 4)
                    if len(raw) < 264 * 4:
                        return None
                    values = unpack('<264f', raw)
                    values = tuple(values) + (0.0,) * (584 - 264)
                else:
                    values = unpack('<584f', raw)
                return values
        except Exception as e:
            print(f"读取数据失败 (foa={foa}): {e}")
            return None

    def _extract_report_date(self, filename: str) -> int:
        """从文件名 gpcwYYYYMMDD.dat 中提取报告期日期 YYYYMMDD"""
        date_str = filename[4:12]
        return int(date_str)

    def batch_import(self, start_year: int = 2000, end_year: int = 2030, chunksize: int = 2000):
        """
        批量导入指定年份区间的所有财务数据
        Args:
            start_year: 起始年份
            end_year: 结束年份
            chunksize: 每多少条数据提交一次事务
        """
        # 收集符合条件的文件，按日期排序
        files = []
        for fname in os.listdir(self.cw_dir):
            if fname.startswith('gpcw') and fname.endswith('.dat'):
                try:
                    year = int(fname[4:8])
                    if start_year <= year <= end_year:
                        files.append((fname, self._extract_report_date(fname)))
                except ValueError:
                    continue
        files.sort(key=lambda x: x[1])

        if not files:
            print("未找到符合条件的财务数据文件。")
            return

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # 构建 INSERT 语句，字段顺序固定
        field_cols = [f"field_{i}" for i in range(1, 585)]
        placeholders = ','.join(['?'] * (2 + 584))  # stock_code, report_date, 584 values
        insert_sql = f"INSERT OR REPLACE INTO financial_data (stock_code, report_date, {','.join(field_cols)}) VALUES ({placeholders})"

        total_inserted = 0
        for fname, report_date in files:
            fpath = os.path.join(self.cw_dir, fname)
            print(f"处理文件: {fname} (报告期: {report_date})")
            stocks = self._parse_file_stocks(fpath)
            if not stocks:
                print(f"  -> 文件无有效股票数据")
                continue

            batch_data = []
            for code, foa in stocks:
                values = self._read_stock_data(fpath, foa)
                if values is None:
                    continue
                # 构造插入参数：stock_code, report_date, *field_values
                row = [code, report_date] + list(values)
                batch_data.append(row)

                if len(batch_data) >= chunksize:
                    cursor.executemany(insert_sql, batch_data)
                    conn.commit()
                    total_inserted += len(batch_data)
                    batch_data.clear()

            # 提交剩余数据
            if batch_data:
                cursor.executemany(insert_sql, batch_data)
                conn.commit()
                total_inserted += len(batch_data)

            print(f"  -> 已导入 {len(stocks)} 只股票，累计提交 {total_inserted} 条记录")

        conn.close()
        print(f"批量导入完成，共插入/更新 {total_inserted} 条记录。")

    def incremental_update(self):
        """
        增量更新：查找数据库中不存在的报告期文件，并导入
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT report_date FROM financial_data")
        existing_dates = {row[0] for row in cursor.fetchall()}
        conn.close()

        files_to_import = []
        for fname in os.listdir(self.cw_dir):
            if fname.startswith('gpcw') and fname.endswith('.dat'):
                rd = self._extract_report_date(fname)
                if rd not in existing_dates:
                    files_to_import.append((fname, rd))

        if not files_to_import:
            print("没有新的报告期文件。")
            return

        files_to_import.sort(key=lambda x: x[1])
        print(f"发现 {len(files_to_import)} 个新报告期文件，准备导入...")
        # 复用批量导入的部分逻辑，这里采用单文件逐批插入
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        field_cols = [f"field_{i}" for i in range(1, 585)]
        placeholders = ','.join(['?'] * (2 + 584))
        insert_sql = f"INSERT OR REPLACE INTO financial_data (stock_code, report_date, {','.join(field_cols)}) VALUES ({placeholders})"

        total = 0
        for fname, report_date in files_to_import:
            fpath = os.path.join(self.cw_dir, fname)
            print(f"更新文件: {fname}")
            stocks = self._parse_file_stocks(fpath)
            batch = []
            for code, foa in stocks:
                values = self._read_stock_data(fpath, foa)
                if values is None:
                    continue
                row = [code, report_date] + list(values)
                batch.append(row)
                if len(batch) >= 2000:
                    cursor.executemany(insert_sql, batch)
                    conn.commit()
                    total += len(batch)
                    batch.clear()
            if batch:
                cursor.executemany(insert_sql, batch)
                conn.commit()
                total += len(batch)
        conn.close()
        print(f"增量更新完成，新增 {total} 条记录。")

    def get_field_info(self, field_id: int) -> Optional[str]:
        """根据字段编号获取字段中文名"""
        return self.field_names.get(field_id)

    # 可选：导出字段说明到数据库，便于查询
    def create_field_desc_table(self):
        """创建字段说明辅助表"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS field_description (
                field_id INTEGER PRIMARY KEY,
                field_name TEXT,
                description TEXT
            )
        """)
        data = [(fid, f"field_{fid}", name) for fid, name in self.field_names.items()]
        cursor.executemany("INSERT OR REPLACE INTO field_description VALUES (?,?,?)", data)
        conn.commit()
        conn.close()
        print("字段说明表 field_description 已创建。")