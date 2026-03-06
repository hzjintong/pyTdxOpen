import csv
import ast
import struct
import os
import shutil
import keyboard
from collections import defaultdict

# ===== 配置 =====
# 日志文件路径（请根据实际情况修改）
ERROR_LOG_CSV = r"tdx_minute_parsing_errors.csv"
# 是否在恢复前备份原文件（True/False）
BACKUP_BEFORE_RESTORE = True
# ================
def check_for_exit():
    """检查是否按下了退出键"""
    # if keyboard.is_pressed('CTRL+q') or keyboard.is_pressed('esc'):
    if keyboard.is_pressed('CTRL+q') :
        return True
    return False

def read_tdx_file(filepath):
    """
    读取通达信分钟数据文件（.lc1/.lc5），返回记录字典列表
    格式：<2H5f2I (32字节/条)
    """
    records = []
    try:
        with open(filepath, 'rb') as f:
            while True:
                chunk = f.read(32)
                if len(chunk) < 32:
                    break
                # 解包：2个unsigned short, 5个float, 2个unsigned int
                vals = struct.unpack('<2H5f2I', chunk)
                record = {
                    'datetime': vals[0],
                    'timestamp': vals[1],
                    'open': vals[2],
                    'high': vals[3],
                    'low': vals[4],
                    'close': vals[5],
                    'amount': vals[6],
                    'volume': vals[7],
                    'spare': vals[8]
                }
                records.append(record)
    except FileNotFoundError:
        print(f"  文件不存在: {filepath}，将新建文件。")
    except Exception as e:
        print(f"  读取文件 {filepath} 时出错: {e}")
    return records

def write_tdx_file(filepath, records):
    """将记录列表写回通达信分钟数据文件"""
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
        print(f"  写入文件 {filepath} 时出错: {e}")

def restore_records_for_file(file_path, recover_records):
    """对单个文件执行恢复操作（合并、去重、排序、写回）"""
    if not os.path.exists(file_path) and not recover_records:
        return

    # 备份原文件
    if BACKUP_BEFORE_RESTORE and os.path.exists(file_path):
        backup_path = file_path + '.bak'
        if not os.path.exists(backup_path):
            shutil.copy2(file_path, backup_path)
            print(f"  已备份至: {backup_path}")

    # 读取现有数据
    existing = read_tdx_file(file_path)
    existing_dict = {(rec['datetime'], rec['timestamp']): rec for rec in existing}

    added = 0
    skipped = 0
    for rec in recover_records:
        key = (rec['datetime'], rec['timestamp'])
        if key in existing_dict:
            print(f"    跳过重复记录: datetime={rec['datetime']}, timestamp={rec['timestamp']}")
            skipped += 1
        else:
            existing.append(rec)
            existing_dict[key] = rec
            added += 1

    if added == 0:
        print(f"  无需添加新记录，文件未变动。")
        return

    # 按(datetime, timestamp)排序
    existing.sort(key=lambda x: (x['datetime'], x['timestamp']))

    # 写回文件
    write_tdx_file(file_path, existing)
    print(f"  完成：添加 {added} 条，跳过 {skipped} 条。")

def main():
    print("开始读取清理日志...")
    # 按文件路径分组存储待恢复的记录
    records_by_file = defaultdict(list)

    try:
        with open(ERROR_LOG_CSV, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                error_msg = row.get('错误信息', '')
                # 筛选日期解析格式错误（可根据需要调整关键字）
                if 'does not match format' in error_msg:
                    record_str = row.get('原始记录全量', '')
                    if not record_str:
                        continue
                    try:
                        # 将字符串表示的字典转换为真实字典
                        record = ast.literal_eval(record_str)
                        # 确保字典包含所有必要字段
                        if all(k in record for k in ('datetime', 'timestamp', 'open', 'high', 'low', 'close', 'amount', 'volume', 'spare')):
                            file_path = row.get('文件完整路径', '')
                            if file_path:
                                records_by_file[file_path].append(record)
                            else:
                                print("警告：某行缺少文件路径，已跳过")
                        else:
                            print("警告：记录缺少必要字段，已跳过")

                        if check_for_exit():
                            break

                    except Exception as e:
                        print(f"解析记录失败: {e}\n记录内容: {record_str}")
    except FileNotFoundError:
        print(f"错误：日志文件 {ERROR_LOG_CSV} 不存在，请检查路径。")
        return
    except Exception as e:
        print(f"读取日志时出错: {e}")
        return

    total_files = len(records_by_file)
    total_records = sum(len(v) for v in records_by_file.values())
    print(f"共找到 {total_files} 个文件，包含 {total_records} 条待恢复记录。")

    # 按文件逐一恢复
    for idx, (file_path, rec_list) in enumerate(records_by_file.items(), 1):
        print(f"\n[{idx}/{total_files}] 处理文件: {file_path}")
        restore_records_for_file(file_path, rec_list)

    print("\n所有恢复操作完成！")

if __name__ == '__main__':
    main()