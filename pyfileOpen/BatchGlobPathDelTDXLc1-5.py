import struct
import os
import glob
import csv  # 新增：用于处理CSV输出
from datetime import datetime, timedelta
from pathlib import Path
import keyboard

from OpenTdxMin import format_minute_datetime_obj, read_tdx_min_file
from DeleteTDXLC1 import delete_min_file, read_tdx_min_file2

# 定义错误日志文件名
ERROR_LOG_CSV = r"F:\D盘备份1\new_hxzq_hc\vipdoc\All_csv\tdx_parsing_errors.csv"


def log_parsing_error(file_path, record_idx, record, error_msg):
    """
    将解析错误记录到CSV文件中
    """
    file_exists = os.path.isfile(ERROR_LOG_CSV)
    with open(ERROR_LOG_CSV, 'a', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        # 如果文件不存在，写入表头
        if not file_exists:
            writer.writerow(['文件完整路径', '记录顺序号', '原始日期码(datetime)', '原始时间戳(timestamp)', '错误信息',
                             '原始记录全量'])

        writer.writerow([
            file_path,
            record_idx,
            record.get('datetime'),
            record.get('timestamp'),
            error_msg,
            str(record)
        ])


def check_for_exit():
    """检查是否按下了退出键"""
    if keyboard.is_pressed('CTRL+shift+q'):
        return True
    return False


def sort_delete_min_time_data(all_data, start_dt, file_path):
    # 按年月日和时分间戳进行排序
    sorted_data1 = sorted(all_data, key=lambda x: (x['datetime'], x['timestamp']))

    # 检查时间连续性并处理不连续的情况
    deleted_data = []
    prev_timestamp = None
    number_of_deleted = 0  #  用于计算删除指定时间点前的记录数量
    number_of_repetitions = 0   #  用于计算重复记录的数量
    number_of_errors = 0

    for i, record in enumerate(sorted_data1):
        current_date_code = record['datetime']
        current_timestamp = record['timestamp']

        try:
            # 尝试解析日期，如果历史数据损坏，这里最容易报错
            current_date = format_minute_datetime_obj(current_date_code, current_timestamp)
        except Exception as e:
            # 捕获异常，记录到CSV，增加错误计数，并跳过此条记录继续处理
            number_of_errors += 1
            log_parsing_error(file_path, i, record, f"日期解析异常: {str(e)}")
            continue

        if current_date < start_dt:  # 如果当前记录的时间小于需要的起始时间，为不需要的数据，跳过即删除
            number_of_deleted += 1
            continue

        # 大于当前日期肯定是个错误，也要进行删除
        if current_date > datetime.now():
            number_of_errors += 1
            log_parsing_error(file_path, i, record, f"日期解析异常（大于当前日期）: {current_date}")
            continue

        # 对于价格异常进行处理，小于0.001
        if record['open'] < 0 or record['high'] < 0 or record['low'] < 0 or record['close'] < 0 :
            number_of_errors += 1
            log_parsing_error(file_path, i, record, f"有价格异常（小于0）")
            continue

        # 如果是第一条记录，直接添加
        if prev_timestamp is None:
            deleted_data.append(record)
            prev_timestamp = current_timestamp
            continue

        # 检查时间是否连续
        time_diff = current_timestamp - prev_timestamp

        if time_diff == 0:  # 如果时间差为0 为重复数据需要剔除
            number_of_repetitions += 1
            prev_timestamp = current_timestamp
            # print(f"发现重复数据，时间点: {prev_timestamp} -> {current_timestamp} (间隔: {time_diff} 分钟)")
            continue

        # 如果时间差大于1分钟但小于5分钟，可能是正常间隔
        # 如果时间差很大，说明有不连续的时段，781为13:01，690为11:30，这是午间休息停止交易的时间段，以下是适合1分钟数据的判断
        # if time_diff > 5 and prev_timestamp != 690 and current_timestamp != 781 :  # 假设5分钟以上的间隔视为不连续
        #    print(f"发现不连续时间段: {prev_timestamp} -> {current_timestamp} (间隔: {time_diff} 分钟)，在记录: {i} 处。")

        # 添加需要的数据
        deleted_data.append(record)
        prev_timestamp = current_timestamp

    if number_of_errors > 0:
        print(f"!!! 在文件 {file_path} 中发现 {number_of_errors} 条异常记录，已记录至 CSV。")

    print(
        f"处理完成：保留 {len(deleted_data)} 条，剔除 {number_of_repetitions} 条重复，删除 {number_of_deleted} 条早于设定时间记录。")
    return deleted_data


def write_tdx_min_file(data_list, output_path):
    if len(data_list) == 0:
        print("数据长度为 0 ，删除文件。")
        try:
            os.remove(output_path)
            print(f"文件 '{output_path}' 已成功删除。")
        except Exception as e:
            print(f"删除空文件时出错：{e}")
        return True

    try:
        # 确保输出目录存在
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        with open(output_path, 'wb') as f:
            for record in data_list:
                record_data = struct.pack('<2H5f2I',
                                          record['datetime'],
                                          record['timestamp'],
                                          record['open'],
                                          record['high'],
                                          record['low'],
                                          record['close'],
                                          record['amount'],
                                          record['volume'],
                                          record['spare'])
                f.write(record_data)
        print(f"已回写 {len(data_list)} 条合法记录到 {output_path}")
        return True
    except Exception as e:
        print(f"写入文件 {output_path} 时出错: {e}")
        return False

# 假设这是您之前写好的合并函数
def delete_min_data(input_filename, start_dt):
    print(f"正在读取: {input_filename}")
    # 这里我们假设 read_tdx_min_file 内部已有基础 try-except，不会直接崩溃
    file1_data = read_tdx_min_file(input_filename)

    if not file1_data:
        print(f"文件 {input_filename} 为空或读取失败，跳过。")
        return

    # 传递 input_filename 用于错误日志记录
    sorted_delete_data = sort_delete_min_time_data(file1_data, start_dt, str(input_filename))

    if sorted_delete_data is not None:
        write_tdx_min_file(sorted_delete_data, input_filename)


def batch_delete_vipdoc(vipdoc_root_path, import_start_date_time):
    vipdoc_path = Path(vipdoc_root_path)
    try:
        start_dt = datetime.strptime(import_start_date_time, "%Y%m%d")
    except ValueError:
        print("输入的日期格式有误，请使用 YYYYMMDD 格式")
        return

    target_structures = {
        'bj': ['minline', 'fzline', 'lday'],
        'ds': ['minline', 'fzline', 'lday'],
        'sh': ['minline', 'fzline', 'lday'],
        'sz': ['minline', 'fzline', 'lday']
    }

    for market, data_types in target_structures.items():
        market_path = vipdoc_path / market
        if not market_path.exists():
            continue

        for data_type in data_types:
            data_type_path = market_path / data_type
            if not data_type_path.exists():
                continue

            # 获取所有lc1, lc5文件
            files_to_process = glob.glob(os.path.join(data_type_path, '*.lc1')) + \
                               glob.glob(os.path.join(data_type_path, '*.lc5'))

            print(f"正在处理目录: {data_type_path}，待处理文件数: {len(files_to_process)}")

            for file_path in files_to_process:
                input_file = Path(file_path)
                try:
                    delete_min_data(input_file, start_dt)
                except Exception as e:
                    # 顶层捕获，防止单个文件处理逻辑崩溃导致整个批处理停止
                    print(f"处理文件 {file_path} 时发生严重错误: {e}")
                    log_parsing_error(file_path, -1, {}, f"文件处理崩溃: {str(e)}")

                if check_for_exit():
                    response = input("\n已检测到中断信号，是否取消后续操作？(y/n): ")
                    if response.lower() == 'y':
                        break

    print("所有市场和数据类型的批量处理完成！")


def batch_delete_min_file(vipdoc_root_path, import_start_date_time):
    """
    该函数保留原逻辑，但在关键解析位置增加防崩处理
    """
    vipdoc_path = Path(vipdoc_root_path)
    try:
        start_dt = datetime.strptime(import_start_date_time, "%Y%m%d")
    except ValueError:
        print("输入的日期格式有误，请使用 YYYYMMDD 格式")
        return False

    deleted_files_num = 0
    operating_files_num = 0

    target_structures = {
        'bj': ['minline', 'fzline', 'lday'],
        'ds': ['minline', 'fzline', 'lday'],
        'sh': ['minline', 'fzline', 'lday'],
        'sz': ['minline', 'fzline', 'lday']
    }

    for market, data_types in target_structures.items():
        market_path = vipdoc_path / market
        if not market_path.exists(): continue

        for data_type in data_types:
            data_type_path = market_path / data_type
            if not data_type_path.exists(): continue

            file_list = glob.glob(os.path.join(data_type_path, '*.lc[15]'))

            for input_filename in file_list:
                try:
                    min_data = read_tdx_min_file2(input_filename)
                    if min_data:
                        # 增加解析保护
                        try:
                            end_date_time = format_minute_datetime_obj(min_data[0]['datetime'],
                                                                       min_data[0]['timestamp'])
                            if datetime.now() - end_date_time >= timedelta(days=10950):
                                print(f"清理旧文件: {input_filename}")
                                delete_min_file(input_filename)
                                deleted_files_num += 1
                                continue
                        except Exception as e:
                            log_parsing_error(input_filename, 0, min_data[0], f"预检日期解析失败: {e}")
                except Exception as e:
                    print(f"预检文件 {input_filename} 失败: {e}")

                try:
                    delete_min_data(input_filename, start_dt)
                except Exception as e:
                    # 顶层捕获，防止单个文件处理逻辑崩溃导致整个批处理停止
                    print(f"处理文件 {input_filename} 时发生严重错误: {e}")
                    log_parsing_error(input_filename, -1, {}, f"文件处理崩溃: {str(e)}")

                operating_files_num += 1
                if check_for_exit():
                    response = input("\n已检测到中断信号，是否取消后续操作？(y/n): ")
                    if response.lower() == 'y':
                        break

    print(f"预检清理完成！处理 {operating_files_num} 个，删除 {deleted_files_num} 个。")
    return deleted_files_num


def main():
    tdx_vipdoc_dir = r'F:\D盘备份1\new_hxzq_hc\vipdoc'
    start_date_time = '19800101'

    begin_time = datetime.now()
    # 第一步：清理极旧文件
    batch_delete_min_file(tdx_vipdoc_dir, start_date_time)

    # 第二步：正式清洗数据
    print(f"\n开始执行数据清洗，异常记录将输出至: {ERROR_LOG_CSV}")
    # batch_delete_vipdoc(tdx_vipdoc_dir, start_date_time)

    end_time = datetime.now()
    print(f"\n全部任务结束。")
    print(f"耗时: {abs(end_time - begin_time)}")


if __name__ == '__main__':
    main()