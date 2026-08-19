import os
import re
import sqlite3
from struct import unpack, calcsize
import pandas as pd
from typing import Dict, List, Tuple, Optional


def convert_yymmdd_to_yyyymmdd(val: Optional[float]) -> int:
    """
    将通达信原始 YYMMDD 格式的 float/int 转化为标准的 YYYYMMDD 格式整数。
    例:
        10331.0  -> "010331" -> 20010331
        630.0    -> "000630" -> 20000630
        981231.0 -> "981231" -> 19981231
        0.0 / None -> 0
    """
    if val is None or val == 0:
        return 0

    try:
        # 转为整数并补足6位（解决首位或多位0丢失问题）
        val_int = int(round(val))
        if val_int <= 0:
            return 0

        s = str(val_int).zfill(6)
        if len(s) != 6:
            return 0  # 异常格式直接置0

        yy = int(s[:2])
        # 根据年份判断世纪：80-99 判定为 19xx 年，00-79 判定为 20xx 年
        century = "19" if yy >= 80 else "20"

        yyyy_mm_dd = int(f"{century}{s}")
        return yyyy_mm_dd
    except Exception:
        return 0


class TDXFinancialDB:
    """通达信财务数据 -> SQLite 批量导入与更新 (支持 313/314/315 字段标准 YYYYMMDD 日期转换)"""

    DATE_FIELDS = {313, 314, 315}  # 需要特殊格式化为 YYYYMMDD 的日期字段

    def __init__(self, cw_dir: str, field_file: str, db_path: str = "tdx_financial.db"):
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
                match = re.match(r'(\d+)\.?--(.+)', line)
                if match:
                    fid = int(match.group(1))
                    name = match.group(2).strip()
                    self.field_names[fid] = name
        except Exception as e:
            print(f"加载字段说明文件失败: {e}")
            for i in range(1, 585):
                self.field_names[i] = f"field_{i}"

    def create_table(self):
        """创建财务数据表及索引 (调整 313, 314, 315 为 INTEGER)"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cols = ["id INTEGER PRIMARY KEY AUTOINCREMENT",
                "stock_code TEXT NOT NULL",
                "report_date INTEGER NOT NULL"]

        for fid in range(1, 585):
            col_name = f"field_{fid}"
            # 针对 313, 314, 315 设为 INTEGER 存储 YYYYMMDD
            if fid in self.DATE_FIELDS:
                cols.append(f"{col_name} INTEGER")
            else:
                cols.append(f"{col_name} REAL")

        cols.append("UNIQUE(stock_code, report_date)")

        create_sql = f"CREATE TABLE IF NOT EXISTS financial_data ({', '.join(cols)})"
        cursor.execute(create_sql)

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_fin_data_stock ON financial_data(stock_code)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_fin_data_date ON financial_data(report_date)")

        conn.commit()
        conn.close()
        print("数据库表 financial_data (已优化日期字段类型) 及索引创建完毕。")

    def reset_financial_table(self):
        """仅删除并重建 financial_data 表及其索引"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS financial_data")
        conn.commit()
        conn.close()
        print("原有 financial_data 表已删除。")
        self.create_table()

    def _parse_file_stocks_dedup(self, file_path: str) -> List[Tuple[str, int]]:
        """解析单个 gpcw.dat 文件并去重"""
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

        seen = {}
        for code, foa in stocks:
            seen[code] = foa
        return list(seen.items())

    def _read_stock_data(self, file_path: str, foa: int) -> Optional[Tuple]:
        """读取指定偏移处的 584 个值，并将 313、314、315 转换为 YYYYMMDD 格式整数"""
        try:
            with open(file_path, 'rb') as f:
                f.seek(foa)
                data_size = 584 * 4
                raw = f.read(data_size)
                if len(raw) < data_size:
                    raw = f.read(264 * 4)
                    if len(raw) < 264 * 4:
                        return None
                    values = unpack('<264f', raw)
                    raw_values = list(values) + [0.0] * (584 - 264)
                else:
                    raw_values = list(unpack('<584f', raw))

                # ---- 核心修改：对 313, 314, 315 日期字段做数据清洗与转换 ----
                for fid in self.DATE_FIELDS:
                    idx = fid - 1  # 下标从0开始
                    raw_val = raw_values[idx]
                    raw_values[idx] = convert_yymmdd_to_yyyymmdd(raw_val)

                return tuple(raw_values)
        except Exception as e:
            print(f"读取数据失败 (foa={foa}): {e}")
            return None

    def _extract_report_date(self, filename: str) -> int:
        """从文件名 gpcwYYYYMMDD.dat 中提取报告期日期 YYYYMMDD"""
        return int(filename[4:12])

    def _get_existing_record(self, cursor, stock_code: str, report_date: int) -> Optional[Tuple]:
        cursor.execute(f"SELECT * FROM financial_data WHERE stock_code=? AND report_date=?",
                       (stock_code, report_date))
        row = cursor.fetchone()
        if row is None:
            return None
        return row[3:]

    def sync_and_log_changes(self, start_year: int = 1987, end_year: int = 2030,
                             export_excel: bool = True, excel_path: str = "changes_log.xlsx",
                             tolerance: float = 1e-6):
        """同步财务文件并增量写入"""
        files = []
        for fname in os.listdir(self.cw_dir):
            if fname.startswith('gpcw') and fname.endswith('.dat'):
                try:
                    year = int(fname[4:8])
                    if start_year <= year <= end_year:
                        report_date = self._extract_report_date(fname)
                        files.append((fname, report_date))
                except ValueError:
                    continue
        files.sort(key=lambda x: x[1])

        if not files:
            print("没有找到符合条件的财务数据文件。")
            return

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        change_records = []
        total_inserted = 0
        total_updated = 0
        total_changed_fields = 0

        for fname, report_date in files:
            fpath = os.path.join(self.cw_dir, fname)
            print(f"正在处理文件: {fname} (报告期: {report_date})")

            total_updated_before = total_updated
            total_changed_fields_before = total_changed_fields

            stocks = self._parse_file_stocks_dedup(fpath)
            if not stocks:
                continue

            batch_insert = []
            num_file_inserted = 0

            for code, foa in stocks:
                new_values = self._read_stock_data(fpath, foa)
                if new_values is None:
                    continue

                existing = self._get_existing_record(cursor, code, report_date)

                if existing is None:
                    row = [code, report_date] + list(new_values)
                    batch_insert.append(row)
                    num_file_inserted += 1
                else:
                    changed = False
                    field_diffs = []
                    for fid in range(1, 585):
                        old_val = existing[fid - 1]
                        new_val = new_values[fid - 1]

                        if old_val is None and new_val is None:
                            continue
                        elif old_val is None or new_val is None:
                            changed = True
                            field_diffs.append((fid, old_val, new_val))
                        else:
                            # 日期字段按整型值强比较，其他按浮点容差比较
                            if fid in self.DATE_FIELDS:
                                if old_val != new_val:
                                    changed = True
                                    field_diffs.append((fid, old_val, new_val))
                            else:
                                try:
                                    if abs(old_val - new_val) > tolerance:
                                        changed = True
                                        field_diffs.append((fid, old_val, new_val))
                                except TypeError:
                                    if old_val != new_val:
                                        changed = True
                                        field_diffs.append((fid, old_val, new_val))

                    if changed:
                        for fid, old_val, new_val in field_diffs:
                            field_name = self.field_names.get(fid, f"field_{fid}")
                            change_records.append((
                                fname, code, report_date, fid, field_name, old_val, new_val
                            ))
                        total_changed_fields += len(field_diffs)

                        update_sql = f"UPDATE financial_data SET {', '.join([f'field_{i}=?' for i in range(1, 585)])} WHERE stock_code=? AND report_date=?"
                        params = list(new_values) + [code, report_date]
                        cursor.execute(update_sql, params)
                        total_updated += 1

            if batch_insert:
                field_cols = [f"field_{i}" for i in range(1, 585)]
                placeholders = ','.join(['?'] * (2 + 584))
                insert_sql = f"INSERT INTO financial_data (stock_code, report_date, {','.join(field_cols)}) VALUES ({placeholders})"
                cursor.executemany(insert_sql, batch_insert)
                total_inserted += num_file_inserted
                conn.commit()

            conn.commit()

            file_updated = total_updated - total_updated_before
            file_changed_fields = total_changed_fields - total_changed_fields_before
            print(f"  -> 新增 {num_file_inserted} 只股票，更新 {file_updated} 只股票，字段变化 {file_changed_fields}")

        conn.close()
        print(f"同步完成：共新增记录 {total_inserted}，更新记录 {total_updated}，修改字段数 {total_changed_fields}")

        if export_excel and change_records:
            df_log = pd.DataFrame(change_records, columns=[
                "文件", "股票代码", "报告期", "字段ID", "字段名称", "旧值", "新值"
            ])
            df_log.to_excel(excel_path, index=False)
            print(f"变更日志已导出至: {excel_path}")

    def batch_import(self, start_year: int = 1988, end_year: int = 2030, chunksize: int = 2000):
        """全量批量导入"""
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

        field_cols = [f"field_{i}" for i in range(1, 585)]
        placeholders = ','.join(['?'] * (2 + 584))
        insert_sql = f"INSERT OR REPLACE INTO financial_data (stock_code, report_date, {','.join(field_cols)}) VALUES ({placeholders})"

        total_inserted = 0
        for fname, report_date in files:
            fpath = os.path.join(self.cw_dir, fname)
            print(f"处理文件: {fname} (报告期: {report_date})")
            stocks = self._parse_file_stocks_dedup(fpath)
            if not stocks:
                continue

            batch_data = []
            for code, foa in stocks:
                values = self._read_stock_data(fpath, foa)
                if values is None:
                    continue
                row = [code, report_date] + list(values)
                batch_data.append(row)

                if len(batch_data) >= chunksize:
                    cursor.executemany(insert_sql, batch_data)
                    conn.commit()
                    total_inserted += len(batch_data)
                    batch_data.clear()

            if batch_data:
                cursor.executemany(insert_sql, batch_data)
                conn.commit()
                total_inserted += len(batch_data)

            print(f"  -> 已导入 {len(stocks)} 只股票，累计提交 {total_inserted} 条记录")

        conn.close()
        print(f"批量导入完成，共插入/更新 {total_inserted} 条记录。")

    def create_field_desc_table(self):
        """创建/刷新字段说明表"""
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
        print("字段说明表 field_description 已创建/更新。")