import os
import re
import sqlite3
from struct import unpack, calcsize
import pandas as pd
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

    def reset_financial_table(self):
        """仅删除并重建 financial_data 表及其索引，不影响数据库中的其他表"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        # 删除表（如果存在）
        cursor.execute("DROP TABLE IF EXISTS financial_data")
        conn.commit()
        conn.close()
        print("原有 financial_data 表已删除。")
        # 重新创建表结构及索引
        self.create_table()

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

    def _parse_file_stocks_dedup(self, file_path: str) -> List[Tuple[str, int]]:
        """
        解析单个 gpcw.dat 文件，返回所有股票的 (stock_code, foa) 列表。
        对于同一股票代码出现多次的重复记录，只保留最后一次出现的（后出现的值经实证为正确版本）。
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

        # ---- 去重逻辑：对同一股票代码，只保留最后一次出现的记录 ----
        seen = {}
        for code, foa in stocks:
            seen[code] = foa  # 后出现的会覆盖前面的，即保留最后一次
        return list(seen.items())

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

    def _get_existing_record(self, cursor, stock_code: str, report_date: int) -> Optional[Tuple]:
        """获取某只股票某报告期的全部字段值，不存在则返回 None"""
        cursor.execute(f"SELECT * FROM financial_data WHERE stock_code=? AND report_date=?",
                       (stock_code, report_date))
        row = cursor.fetchone()
        if row is None:
            return None
        # 返回的 row 结构为 (id, stock_code, report_date, field_1, ..., field_584)
        # 我们只需要字段值部分（index 3 开始）
        return row[3:]  # 584个值

    def sync_and_log_changes(self, start_year: int = 2000, end_year: int = 2030,
                             export_excel: bool = True, excel_path: str = "changes_log.xlsx",
                             tolerance: float = 1e-6):
        """
        同步所有财务文件，检测变化并更新，可选输出 Excel 日志。

        Args:
            start_year: 处理文件的起始年份
            end_year: 处理文件的结束年份
            export_excel: 是否导出变更日志为 Excel
            excel_path: Excel 输出路径
            tolerance: 浮点数比较容差，小于此值视为无变化
        """
        # 收集文件
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

        # 用于收集所有变更记录
        change_records = []  # 每个元素为 (文件, 股票, 报告期, 字段ID, 字段名, 旧值, 新值)
        total_inserted = 0
        total_updated = 0
        total_changed_fields = 0

        for fname, report_date in files:
            fpath = os.path.join(self.cw_dir, fname)
            print(f"正在处理文件: {fname} (报告期: {report_date})")

            # ---------- 修正点：记录处理本文件前的累计值 ----------
            total_updated_before = total_updated
            total_changed_fields_before = total_changed_fields

            # 解析文件中的股票列表，修正为 _parse_file_stocks_dedup 新增的去重版本
            stocks = self._parse_file_stocks_dedup(fpath)
            if not stocks:
                continue

            batch_insert = []  # 尚未存在，待插入
            num_file_inserted = 0
            batch_update = []  # 发生变化，待更新 (stock_code, new_values_tuple)

            for code, foa in stocks:
                new_values = self._read_stock_data(fpath, foa)
                if new_values is None:
                    continue

                existing = self._get_existing_record(cursor, code, report_date)

                if existing is None:
                    # 新股票，直接插入
                    row = [code, report_date] + list(new_values)
                    batch_insert.append(row)
                    num_file_inserted += 1
                else:
                    # 逐字段比较
                    changed = False
                    field_diffs = []  # (field_id, old, new)
                    for fid in range(1, 585):
                        old_val = existing[fid - 1]
                        new_val = new_values[fid - 1]
                        # 比较逻辑：处理None和浮点数容差
                        if old_val is None and new_val is None:
                            continue
                        elif old_val is None or new_val is None:
                            changed = True
                            field_diffs.append((fid, old_val, new_val))
                        else:
                            # 浮点数比较
                            try:
                                diff = abs(old_val - new_val)
                                if diff > tolerance:
                                    changed = True
                                    field_diffs.append((fid, old_val, new_val))
                            except TypeError:
                                if old_val != new_val:
                                    changed = True
                                    field_diffs.append((fid, old_val, new_val))

                    if changed:
                        # 记录变化日志
                        for fid, old_val, new_val in field_diffs:
                            field_name = self.field_names.get(fid, f"field_{fid}")
                            change_records.append((
                                fname, code, report_date, fid, field_name, old_val, new_val
                            ))
                        total_changed_fields += len(field_diffs)

                        # 更新数据库：用新值覆盖全部字段（简化处理，也可只更新变化的字段）
                        # 这里直接用 REPLACE 思想，执行 UPDATE SET field_1=?, ... WHERE ...
                        update_sql = f"UPDATE financial_data SET {', '.join([f'field_{i}=?' for i in range(1, 585)])} WHERE stock_code=? AND report_date=?"
                        params = list(new_values) + [code, report_date]
                        cursor.execute(update_sql, params)
                        total_updated += 1
                    # 若无变化则跳过

            # 批量插入本文件的新股票记录
            if batch_insert:
                field_cols = [f"field_{i}" for i in range(1, 585)]
                placeholders = ','.join(['?'] * (2 + 584))
                insert_sql = f"INSERT INTO financial_data (stock_code, report_date, {','.join(field_cols)}) VALUES ({placeholders})"
                cursor.executemany(insert_sql, batch_insert)
                total_inserted += num_file_inserted  #  len(batch_insert)
                conn.commit()

            # 提交更新（上面的更新已经即时执行，但为了事务安全可以累积后统一提交）
            conn.commit()

            # -------------------修正点，计算本文件的增量并输出---------------------------
            file_updated = total_updated - total_updated_before
            file_changed_fields = total_changed_fields - total_changed_fields_before
            print(f"  -> 新增 {num_file_inserted} 只股票，更新 {file_updated} 只股票，字段变化 {file_changed_fields }")
            # 记录本文件处理完后的计数，以便输出每次变化量（简化起见此处略去精确跟踪，整体统计即可）

        conn.close()

        print(f"同步完成：共新增记录 {total_inserted}，更新记录 {total_updated}，修改字段数 {total_changed_fields}")

        if export_excel and change_records:
            df_log = pd.DataFrame(change_records, columns=[
                "文件", "股票代码", "报告期", "字段ID", "字段名称", "旧值", "新值"
            ])
            df_log.to_excel(excel_path, index=False)
            print(f"变更日志已导出至: {excel_path}")
        elif not change_records:
            print("本次同步未检测到任何数据变化。")

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
            stocks = self._parse_file_stocks_dedup(fpath)  # 返回 [(code, foa), ...替换为新增的去重版本
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
            stocks = self._parse_file_stocks_dedup(fpath)  # 使用去重版本
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

    # 可选：再次同步刷新财务字段说明到数据库，便于补充新的字段说明
    def sync_field_desc_table(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        data = [(fid, f"field_{fid}", name) for fid, name in self.field_names.items()]
        cursor.executemany("INSERT OR REPLACE INTO field_description VALUES (?,?,?)", data)
        conn.commit()
        conn.close()
        print("字段说明表 field_description 已更新同步。")

    def scan_duplicates(self, start_year: int = 1988, end_year: int = 2030,
                        output_excel: str = "duplicate_stocks_log.xlsx",
                        tolerance: float = 1e-6):
        """
        扫描 gpcw*.dat 文件，检测同一文件内同一股票代码是否出现多次，
        若重复，则逐对比较所有字段，记录差异字段，并输出到 Excel。

        Args:
            start_year: 起始年份
            end_year: 结束年份
            output_excel: 输出的 Excel 路径
            tolerance: 浮点数比较容差
        """
        # 收集目标文件
        files = []
        for fname in os.listdir(self.cw_dir):
            if fname.startswith('gpcw') and fname.endswith('.dat'):
                try:
                    year = int(fname[4:8])
                    if start_year <= year <= end_year:
                        files.append(fname)
                except ValueError:
                    continue
        files.sort()
        if not files:
            print("没有找到符合年份条件的文件。")
            return

        records = []  # 每条纪录: (文件, 股票代码, FOA1, FOA2, 字段ID, 字段名, 值1, 值2)
        total_dup_codes = 0

        for fname in files:
            fpath = os.path.join(self.cw_dir, fname)
            stocks = self._parse_file_stocks_dedup(fpath)  # List[Tuple[str, int]]，使用了去重版本
            if not stocks:
                continue

            # 统计重复的股票代码
            code_to_foas = {}
            for code, foa in stocks:
                code_to_foas.setdefault(code, []).append(foa)
            dup_codes = {code: foas for code, foas in code_to_foas.items() if len(foas) > 1}
            if not dup_codes:
                continue

            for code, foa_list in dup_codes.items():
                total_dup_codes += 1
                # 读取所有重复记录的完整数据
                datas = []
                for foa in foa_list:
                    vals = self._read_stock_data(fpath, foa)
                    if vals is None:
                        datas.append(None)
                    else:
                        datas.append(vals)  # tuple of 584 floats

                # 两两比较：以第一个为基准，与后续每一个比较
                base_data = datas[0]
                if base_data is None:
                    print(f"  警告：{fname} 中 {code} 的 FOA={foa_list[0]} 无法读取，跳过")
                    continue

                for i in range(1, len(foa_list)):
                    cmp_data = datas[i]
                    if cmp_data is None:
                        print(f"  警告：{fname} 中 {code} 的 FOA={foa_list[i]} 无法读取，跳过")
                        continue

                    # 比较 584 个字段
                    for fid in range(1, 585):
                        v1 = base_data[fid - 1]
                        v2 = cmp_data[fid - 1]
                        if v1 is None and v2 is None:
                            continue
                        if v1 is None or v2 is None:
                            diff = True
                        else:
                            try:
                                diff = abs(v1 - v2) > tolerance
                            except TypeError:
                                diff = v1 != v2
                        if diff:
                            field_name = self.field_names.get(fid, f"field_{fid}")
                            records.append((
                                fname, code, foa_list[0], foa_list[i],
                                fid, field_name, v1, v2
                            ))

        if records:
            df = pd.DataFrame(records, columns=[
                "文件", "股票代码", "FOA1", "FOA2", "字段ID", "字段名称", "值1", "值2"
            ])
            df.to_excel(output_excel, index=False)
            print(f"共发现 {total_dup_codes} 只重复股票，差异记录 {len(records)} 条。")
            print(f"日志已导出至: {output_excel}")
        else:
            print("未发现任何重复股票记录。")