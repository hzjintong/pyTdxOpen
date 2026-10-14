import os
import re
import json
from datetime import datetime, date
from struct import unpack, calcsize
from typing import Dict, List, Tuple, Optional, Any
import pandas as pd
import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


def convert_yymmdd_to_date(val: Optional[float]) -> Optional[date]:
    """
    将通达信原始 YYMMDD 格式的 float/int 转化为 Python datetime.date 对象。
    例:
        10331.0  -> "010331" -> 2001-03-31
        630.0    -> "000630" -> 2000-06-30
        981231.0 -> "981231" -> 1998-12-31
        0.0 / None -> None
    """
    if val is None or val == 0:
        return None

    try:
        val_int = int(round(val))
        if val_int <= 0:
            return None

        s = str(val_int).zfill(6)
        if len(s) != 6:
            return None

        yy = int(s[:2])
        mm = int(s[2:4])
        dd = int(s[4:6])

        # 月份和日期有效性校验
        if not (1 <= mm <= 12 and 1 <= dd <= 31):
            return None

        century = 1900 if yy >= 80 else 2000
        year = century + yy

        return date(year, mm, dd)
    except Exception:
        return None


def convert_yyyymmdd_filename_to_date(filename: str) -> date:
    """从文件名 gpcwYYYYMMDD.dat 中提取报告期日期并转化为 datetime.date"""
    s = filename[4:12]
    return date(int(s[:4]), int(s[4:6]), int(s[6:8]))


class PGFinancialDB:
    """PostgreSQL 17 财务数据运维与同步引擎 (基于 psycopg3 连接池与行级锁)"""

    DATE_FIELDS = {313, 314, 315}  # 特殊转换为 PG DATE 类型的公告日期字段

    def __init__(self, config_path: str = "config.json"):
        self.config_path = config_path
        self.config = self._load_config()
        self.cw_dir = self.config.get("cw_dir", "d:/new_hxzq_hc/vipdoc/cw/")
        self.field_file = self.config.get("field_file", "专业财务数据字段说明.txt")

        # 初始化 psycopg3 连接池
        pg_cfg = self.config["postgres"]
        conninfo = (
            f"host={pg_cfg['host']} port={pg_cfg['port']} dbname={pg_cfg['dbname']} "
            f"user={pg_cfg['user']} password={pg_cfg['password']}"
        )
        self.pool = ConnectionPool(conninfo=conninfo, min_size=2, max_size=10, open=True)

        self.field_names: Dict[int, str] = {}
        self._load_field_names()

    def _load_config(self) -> Dict[str, Any]:
        """读取外部配置文件，实现环境解耦与密钥隔离"""
        default_config = {
            "cw_dir": "d:/new_hxzq_hc/vipdoc/cw/",
            "field_file": "专业财务数据字段说明.txt",
            "postgres": {
                "host": "localhost",
                "port": 5432,
                "dbname": "quant_db",
                "user": "postgres",
                "password": "your_password"
            }
        }
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"[警告] 加载配置文件失败，将使用默认配置: {e}")
        return default_config

    def _load_field_names(self):
        """解析字段说明文件，精准补全 1~584 全部字段（共 584 项完整覆盖）"""
        raw_dict = {}
        try:
            if os.path.exists(self.field_file):
                with open(self.field_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    # 匹配 "1--基本每股收益" 或 "8.--货币资金"
                    match = re.match(r'^\s*(\d+)[\.\s]*--\s*(.+)$', line)
                    if match:
                        fid = int(match.group(1))
                        name = match.group(2).strip()
                        raw_dict[fid] = name
        except Exception as e:
            print(f"[错误] 加载字段说明文件失败: {e}")

        # 补全 1~584 全部编号，缺失的填入预留说明
        for fid in range(1, 585):
            if fid in raw_dict:
                self.field_names[fid] = raw_dict[fid]
            else:
                self.field_names[fid] = f"保留/未定义字段_{fid}"

    def create_tables(self):
        """创建/确保 PostgreSQL 数据表与高频索引（规范 DATE 类型）"""
        with self.pool.connection() as conn:
            with conn.cursor() as cursor:
                # 1. 建立核心财务表 financial_data
                cols = [
                    "stock_code VARCHAR(16) NOT NULL",
                    "report_date DATE NOT NULL"
                ]
                for fid in range(1, 585):
                    col_name = f"field_{fid}"
                    if fid in self.DATE_FIELDS:
                        cols.append(f"{col_name} DATE")
                    else:
                        cols.append(f"{col_name} DOUBLE PRECISION")

                # 2. 补全自定义评分与评级持久化字段
                cols.append("custom_score DOUBLE PRECISION")
                cols.append("custom_rating VARCHAR(32)")

                # 3. 显式指定复合主键（解决 ON CONFLICT 报错的关键）
                cols.append("PRIMARY KEY (stock_code, report_date)")

                create_sql = f"CREATE TABLE IF NOT EXISTS financial_data ({', '.join(cols)});"
                cursor.execute(create_sql)

                # 高频索引
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_fin_data_stock ON financial_data(stock_code);")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_fin_data_date ON financial_data(report_date DESC);")

                # 2. 建立字段字典表 field_description
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS field_description (
                        field_id INTEGER PRIMARY KEY,
                        field_name VARCHAR(50) NOT NULL,
                        description TEXT
                    );
                """)
                conn.commit()
        print("PostgreSQL 表 financial_data 与 field_description 及索引已建立/确认。")

    def sync_field_description(self):
        """精准全量写入 584 条字段说明字典数据"""
        data = [(fid, f"field_{fid}", desc) for fid, desc in self.field_names.items()]
        upsert_sql = """
            INSERT INTO field_description (field_id, field_name, description)
            VALUES (%s, %s, %s)
            ON CONFLICT (field_id) DO UPDATE 
            SET field_name = EXCLUDED.field_name,
                description = EXCLUDED.description;
        """
        with self.pool.connection() as conn:
            with conn.cursor() as cursor:
                cursor.executemany(upsert_sql, data)
                conn.commit()
        print(f"字典表 field_description 已同步 584 条完整描述记录（含预留项）。")

    def migrate_field_date_types(self):
        """一键平滑无损迁移：将旧 PG 表中的 field_313/314/315 INTEGER 类型修改为 DATE 类型"""
        alter_sql = """
            ALTER TABLE financial_data 
              ALTER COLUMN field_313 TYPE DATE USING (
                CASE WHEN field_313 IS NULL OR field_313::text = '0' THEN NULL 
                     ELSE to_date(field_313::text, 'YYYYMMDD') END
              ),
              ALTER COLUMN field_314 TYPE DATE USING (
                CASE WHEN field_314 IS NULL OR field_314::text = '0' THEN NULL 
                     ELSE to_date(field_314::text, 'YYYYMMDD') END
              ),
              ALTER COLUMN field_315 TYPE DATE USING (
                CASE WHEN field_315 IS NULL OR field_315::text = '0' THEN NULL 
                     ELSE to_date(field_315::text, 'YYYYMMDD') END
              );
        """
        try:
            with self.pool.connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(alter_sql)
                    conn.commit()
            print("【类型无损迁移成功】field_313, field_314, field_315 已成功转换为原生 DATE 类型！")
        except Exception as e:
            print(f"[提示] 类型迁移未执行或已是 DATE 类型: {e}")

    def _parse_file_stocks_dedup(self, file_path: str) -> List[Tuple[str, int]]:
        """解析通达信 gpcw.dat 二进制文件索引段并去重"""
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
        """读取单只股票 584 个字段，并将 313/314/315 精准清洗为 date 对象"""
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

                # 数据清洗转换：313, 314, 315 -> date 对象，其他保持 float
                processed_values = []
                for fid_idx, raw_val in enumerate(raw_values, start=1):
                    if fid_idx in self.DATE_FIELDS:
                        processed_values.append(convert_yymmdd_to_date(raw_val))
                    else:
                        processed_values.append(float(raw_val) if raw_val is not None else 0.0)

                return tuple(processed_values)
        except Exception as e:
            print(f"读取数据失败 (foa={foa}): {e}")
            return None

    def sync_and_log_changes(self, start_year: int = 1987, end_year: int = 2030,
                             export_excel: bool = True, excel_path: str = "changes_log.xlsx",
                             tolerance: float = 1e-6):
        """采用 PostgreSQL 行级锁与对比池，高并发安全地进行增量同步并记录变动日志"""
        files = []
        for fname in os.listdir(self.cw_dir):
            if fname.startswith('gpcw') and fname.endswith('.dat'):
                try:
                    year = int(fname[4:8])
                    if start_year <= year <= end_year:
                        report_date = convert_yyyymmdd_filename_to_date(fname)
                        files.append((fname, report_date))
                except ValueError:
                    continue
        files.sort(key=lambda x: x[1])

        if not files:
            print("没有找到符合条件的财务数据文件。")
            return

        field_cols = [f"field_{i}" for i in range(1, 585)]
        select_sql = f"SELECT {','.join(field_cols)} FROM financial_data WHERE stock_code=%s AND report_date=%s"

        # 批量 Upsert SQL，充分利用 PG 行级锁
        set_clauses = [f"{col}=EXCLUDED.{col}" for col in field_cols]
        upsert_sql = f"""
            INSERT INTO financial_data (stock_code, report_date, {','.join(field_cols)})
            VALUES (%s, %s, {','.join(['%s'] * 584)})
            ON CONFLICT (stock_code, report_date) DO UPDATE
            SET {','.join(set_clauses)};
        """

        change_records = []
        total_inserted = 0
        total_updated = 0
        total_changed_fields = 0

        with self.pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cursor:
                for fname, report_date in files:
                    fpath = os.path.join(self.cw_dir, fname)
                    print(f"正在对比与同步文件: {fname} (报告期: {report_date})")

                    stocks = self._parse_file_stocks_dedup(fpath)
                    if not stocks:
                        continue

                    batch_upsert = []
                    file_inserted = 0
                    file_updated = 0
                    file_changed_fields = 0

                    for code, foa in stocks:
                        new_values = self._read_stock_data(fpath, foa)
                        if new_values is None:
                            continue

                        cursor.execute(select_sql, (code, report_date))
                        existing_row = cursor.fetchone()

                        if existing_row is None:
                            file_inserted += 1
                            batch_upsert.append([code, report_date] + list(new_values))
                        else:
                            # 比对字段变动
                            changed = False
                            field_diffs = []
                            for fid in range(1, 585):
                                col_name = f"field_{fid}"
                                old_val = existing_row[col_name]
                                new_val = new_values[fid - 1]

                                if old_val is None and new_val is None:
                                    continue
                                elif old_val is None or new_val is None:
                                    changed = True
                                    field_diffs.append((fid, old_val, new_val))
                                else:
                                    if fid in self.DATE_FIELDS:
                                        if old_val != new_val:
                                            changed = True
                                            field_diffs.append((fid, old_val, new_val))
                                    else:
                                        if abs(float(old_val) - float(new_val)) > tolerance:
                                            changed = True
                                            field_diffs.append((fid, old_val, new_val))

                            if changed:
                                file_updated += 1
                                file_changed_fields += len(field_diffs)
                                for fid, old_v, new_v in field_diffs:
                                    change_records.append((
                                        fname, code, str(report_date), fid,
                                        self.field_names.get(fid, f"field_{fid}"),
                                        str(old_v), str(new_v)
                                    ))
                                batch_upsert.append([code, report_date] + list(new_values))

                    if batch_upsert:
                        cursor.executemany(upsert_sql, batch_upsert)
                        conn.commit()

                    total_inserted += file_inserted
                    total_updated += file_updated
                    total_changed_fields += file_changed_fields

                    print(f"  -> 新增 {file_inserted} 只，更新 {file_updated} 只，变动字段 {file_changed_fields} 个")

        print(f"\n[同步完成] 共新增 {total_inserted} 条，更新 {total_updated} 条，累计变动字段 {total_changed_fields} 个")

        if export_excel and change_records:
            df_log = pd.DataFrame(change_records, columns=[
                "源文件", "股票代码", "报告期", "字段ID", "字段名称", "旧值", "新值"
            ])
            # 自动创建目录
            os.makedirs(os.path.dirname(os.path.abspath(excel_path)), exist_ok=True)
            df_log.to_excel(excel_path, index=False)
            print(f"变动审计日志已成功导出至: {excel_path}")

    def close(self):
        """优雅关闭连接池"""
        self.pool.close()