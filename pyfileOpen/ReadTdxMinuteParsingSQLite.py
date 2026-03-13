import csv
import ast
import struct
import os
import shutil
import sqlite3
import keyboard
import math
from collections import defaultdict

# ===== 配置 =====
ERROR_LOG_CSV = r"G:\pyfileOpen-20251230\pyfileOpen\tdx_parsing_errors.csv"
BACKUP_BEFORE_RESTORE = True
DB_PATH = "recovery_temp.db"          # 临时 SQLite 数据库文件
BATCH_SIZE = 10000                     # 每批插入的记录数
# ================

def check_for_exit():
    """检查是否按下了退出键"""
    # if keyboard.is_pressed('CTRL+q') or keyboard.is_pressed('esc'):
    if keyboard.is_pressed('CTRL+q') :
        return True
    return False

def parse_record_str(record_str):
    """安全地将字符串表示的字典转换为真实字典，并提取各字段"""
    # 方法1：尝试用 ast.literal_eval 快速解析（适用于不包含 nan/inf 的干净字符串）
    try:
        rec = ast.literal_eval(record_str)
    except Exception as er:
        print(er)
        # 方法2：使用安全的 eval，将 nan, inf 等映射为浮点数
        try:
            # 定义安全命名空间，仅包含需要的常量
            safe_names = {
                'nan': float('nan'),
                'inf': float('inf'),
                '-inf': float('-inf'),
                'true': True,
                'false': False,
                'null': None,
            }
            # 禁止所有内置函数，只允许 safe_names 中的名称
            rec = eval(record_str, {"__builtins__": {}}, safe_names)
        except Exception as e:
            print(f"解析记录失败: {e}\n记录内容: {record_str}")
            return None

    # 检查所有必要字段是否存在
    required = ('datetime', 'timestamp', 'open', 'high', 'low', 'close', 'amount', 'volume', 'spare')
    if not all(k in rec for k in required):
        print(f"记录缺少必要字段: {record_str}")
        return None
    return rec

def init_db():
    """创建 SQLite 数据库和表，建立索引"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path TEXT,
            datetime_code INTEGER,
            timestamp INTEGER,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            amount REAL,
            volume INTEGER,
            spare INTEGER
        )
    ''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_file_path ON records(file_path)')
    conn.commit()
    return conn

def import_csv_to_db(conn):
    """流式读取 CSV，将符合条件的记录分批插入数据库"""
    cur = conn.cursor()
    batch = []
    total_inserted = 0

    with open(ERROR_LOG_CSV, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            error_msg = row.get('错误信息', '')

            # 只处理日期解析格式错误（可调整关键字）
            if '日期解析异常（大于当前日期）' not in error_msg: # 几种错误关键字‘日期解析异常（大于当前日期）’，'does not match format'
                continue

            file_path = row.get('文件完整路径')
            if not file_path:
                continue

            record_str = row.get('原始记录全量')
            if not record_str:
                continue

            rec = parse_record_str(record_str)
            if rec is None:
                continue

            batch.append((
                file_path,
                rec['datetime'],
                rec['timestamp'],
                rec['open'],
                rec['high'],
                rec['low'],
                rec['close'],
                rec['amount'],
                rec['volume'],
                rec['spare']
            ))

            if len(batch) >= BATCH_SIZE:
                cur.executemany('''
                    INSERT INTO records
                    (file_path, datetime_code, timestamp, open, high, low, close, amount, volume, spare)
                    VALUES (?,?,?,?,?,?,?,?,?,?)
                ''', batch)
                conn.commit()
                total_inserted += len(batch)
                batch = []
                print(f"已导入 {total_inserted} 条记录...")

            if check_for_exit():
                break

        # 插入剩余批次
        if batch:
            cur.executemany('''
                INSERT INTO records
                (file_path, datetime_code, timestamp, open, high, low, close, amount, volume, spare)
                VALUES (?,?,?,?,?,?,?,?,?,?)
            ''', batch)
            conn.commit()
            total_inserted += len(batch)

    print(f"CSV 导入完成，共 {total_inserted} 条待恢复记录。")

def read_tdx_file(filepath):
    """读取通达信分钟数据文件，返回记录字典列表"""
    records = []
    try:
        with open(filepath, 'rb') as f:
            while True:
                chunk = f.read(32)
                if len(chunk) < 32:
                    break
                vals = struct.unpack('<2H5f2I', chunk)
                records.append({
                    'datetime': vals[0],
                    'timestamp': vals[1],
                    'open': vals[2],
                    'high': vals[3],
                    'low': vals[4],
                    'close': vals[5],
                    'amount': vals[6],
                    'volume': vals[7],
                    'spare': vals[8]
                })
    except FileNotFoundError:
        pass  # 文件不存在，后续会新建
    except Exception as e:
        print(f"  读取文件 {filepath} 出错: {e}")
    return records

def write_tdx_file(filepath, records):
    """将记录列表写回通达信文件"""
    try:
        with open(filepath, 'wb') as f:
            for rec in records:
                f.write(struct.pack('<2H5f2I',
                                     rec['datetime'],
                                     rec['timestamp'],
                                     rec['open'],
                                     rec['high'],
                                     rec['low'],
                                     rec['close'],
                                     rec['amount'],
                                     rec['volume'],
                                     rec['spare']))
        print(f"  成功写入 {len(records)} 条记录到 {filepath}")
    except Exception as e:
        print(f"  写入文件 {filepath} 出错: {e}")

def restore_file(file_path, conn):
    """对单个文件执行恢复（合并、去重、排序、写回）"""
    # 备份
    if BACKUP_BEFORE_RESTORE and os.path.exists(file_path):
        backup_path = file_path + '.bak'
        if not os.path.exists(backup_path):
            shutil.copy2(file_path, backup_path)
            print(f"  已备份至: {backup_path}")

    # 读取现有数据
    existing = read_tdx_file(file_path)
    existing_keys = {(rec['datetime'], rec['timestamp']) for rec in existing}

    # 从数据库查询该文件的所有待恢复记录
    cur = conn.cursor()
    cur.execute('''
        SELECT datetime_code, timestamp, open, high, low, close, amount, volume, spare
        FROM records
        WHERE file_path = ?
    ''', (file_path,))
    rows = cur.fetchall()

    added = 0
    skipped = 0
    for row in rows:
        rec = {
            'datetime': row[0],
            'timestamp': row[1],
            'open': row[2],
            'high': row[3],
            'low': row[4],
            'close': row[5],
            'amount': row[6],
            'volume': row[7],
            'spare': row[8]
        }
        key = (rec['datetime'], rec['timestamp'])
        if key in existing_keys:
            skipped += 1
        else:
            existing.append(rec)
            existing_keys.add(key)
            added += 1

    if added == 0:
        print(f"  无需添加新记录，跳过。")
        return

    # 按 (datetime, timestamp) 排序
    existing.sort(key=lambda x: (x['datetime'], x['timestamp']))

    # 写回
    write_tdx_file(file_path, existing)
    print(f"  完成：添加 {added} 条，跳过 {skipped} 条。")

def main():
    print("初始化数据库...")
    conn = init_db()

    print("开始导入 CSV 日志（此过程可能较慢，请耐心等待）...")
    import_csv_to_db(conn)

    # 获取所有需要处理的文件路径
    cur = conn.cursor()
    cur.execute('SELECT DISTINCT file_path FROM records')
    file_paths = [row[0] for row in cur.fetchall()]
    print(f"共发现 {len(file_paths)} 个需要恢复的文件。")

    # 逐个文件处理
    for idx, file_path in enumerate(file_paths, 1):
        print(f"\n[{idx}/{len(file_paths)}] 处理文件: {file_path}")
        restore_file(file_path, conn)

    # 清理临时数据库
    conn.close()
    os.remove(DB_PATH)
    print("\n所有恢复操作完成！临时数据库已删除。")

if __name__ == '__main__':
    main()
