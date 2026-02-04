import struct
import os
##import shutil
##from datetime import datetime, timedelta
##from operator import itemgetter
from pyfileOpen.OpenTdxMin import read_tdx_min_file, format_minute_datetime_obj,validate_datetime_sequence

def merge_minute_data(file1_data, file2_data):
    """
    合并两个分钟数据文件的数据
    """
    # 合并所有数据
    all_data = file1_data + file2_data

    # print(f"合并后共有 {len(all_data)} 条记录")
    return all_data

def sort_min_time_data( all_data ):
    # 按年月日和时分间戳进行排序
    sorted_data1 = sorted ( all_data, key=lambda x:( x['datetime'], x['timestamp'] ))

    # 检查时间连续性并处理不连续的情况
    merged_data = []
    prev_datetime = None
    prev_timestamp = None
    number_of_repetitions = 0   #  用于计算重复记录的数量

    for i, record in enumerate(sorted_data1):
        current_datetime = record['datetime']
        current_timestamp = record['timestamp']

        # 如果是第一条记录，直接添加
        if prev_timestamp is None and prev_datetime is None:
            merged_data.append(record)
            prev_datetime = current_datetime
            prev_timestamp = current_timestamp
            continue

        # 检查时间是否连续
        time_diff = current_timestamp - prev_timestamp
        date_diff = current_datetime - prev_datetime

        # 如果时间差大于1分钟但小于5分钟，可能是正常间隔
        # 如果时间差很大，说明有不连续的时段，781为13:01，690为11:30，这是午间休息停止交易的时间段，以下是适合1分钟数据的判断
        # if time_diff > 5 and current_timestamp != 781 and prev_timestamp != 690:  # 假设5分钟以上的间隔视为不连续
        #    print(f"发现不连续时间段: {prev_timestamp} -> {current_timestamp} (间隔: {time_diff} 分钟)")

        if time_diff == 0 and date_diff == 0:  # 如果时间差为0 为重复数据需要剔除
            number_of_repetitions = number_of_repetitions + 1   # 计算重复记录数
            # print(f"发现重复数据，时间点: {prev_timestamp} -> {current_timestamp} (间隔: {time_diff} 分钟)")
            prev_datetime = current_datetime
            prev_timestamp = current_timestamp
            continue

        # 添加数据
        merged_data.append(record)
        prev_datetime = current_datetime
        prev_timestamp = current_timestamp

    print(f"合并排序剔重后共有 {len(merged_data)} 条记录，剔除{number_of_repetitions}条重复记录。")
    return merged_data

def write_tdx_min_file(data_list, output_path):
    """
    将数据写入通达信分钟线数据文件
    """
    try:
        # 确保输出目录存在
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        with open(output_path, 'wb') as f:
            for record in data_list:
                # 将日期时间转换回通达信格式，因需要原样写回原格式文件，所以考虑性能不做转换
                record_date = record['datetime']

                # 提取时间部分
                minutes_since_midnight = record['timestamp']

                # 打包数据
                record_data = struct.pack('<2H5f2I',
                                          record_date,
                                          minutes_since_midnight,
                                          record['open'],
                                          record['high'],
                                          record['low'],
                                          record['close'],
                                          record['amount'],
                                          record['volume'],
                                          record['spare'])

                f.write(record_data)

        print(f"已写入 {len(data_list)} 条记录到 {output_path}")
        return True
    except Exception as e:
        print(f"写入文件 {output_path} 时出错: {e}")
        return False

def validate_time_sequence(data_list):
    """
    验证时间序列的连续性
    """
    if not data_list:
        print("数据列表为空")
        return False

    prev_timestamp = data_list[0]['timestamp']
    number_of_repetitions = 0
    gaps = []
    repe = []

    for i in range(1, len(data_list)):
        current_timestamp = data_list[i]['timestamp']
        time_diff = current_timestamp - prev_timestamp

        # 检查是否有记录重复
        if time_diff == 0:
            repe.append({
                'position': i,
                'prev_time': prev_timestamp,
                'current_time': current_timestamp,
                'gap_minutes': 0
            })
            #print(f"发现重复数据，时间点: {prev_timestamp} -> {current_timestamp} (间隔: {time_diff} 分钟)")
            number_of_repetitions = number_of_repetitions + 1  # 计算重复记录数
            prev_timestamp = current_timestamp

        # 检查时间间隔是否合理
        if time_diff > 5:  # 大于5分钟的间隔视为可能有问题
            gaps.append({
                'position': i,
                'prev_time': prev_timestamp,
                'current_time': current_timestamp,
                'gap_minutes': time_diff
            })

        prev_timestamp = current_timestamp

    if repe:
        print(f"发现 {len(repe)} 处重复数据：")
        for rep in repe:
            print(f" 位置 {rep['position']}: {rep['prev_time']} -> {rep['current_time']} (间隔: {rep['gap_minutes']} 分钟)")

    else:
        print(f"未发现重复数据。")

    if gaps:
        print(f"发现 {len(gaps)} 处时间间隔异常:")
        for gap in gaps:
            print(
                f"  位置 {gap['position']}: {gap['prev_time']} -> {gap['current_time']} (间隔: {gap['gap_minutes']} 分钟)")
        return False
    else:
        print("时间序列连续，没有发现异常间隔")
        return True

def main():
    # 配置输入和输出路径
    input_file1 = r"D:\new_hxzq_hc\vipdoc\ds\minline\27#HZ5017.lc1"  # 替换为第一个文件路径
    input_file2 = r"D:\new_tdx\vipdoc\ds\minline\27#HZ5017.lc1"  # 替换为第二个文件路径
    output_dir =  r"g:/D盘备份1/new_hxzq_hc/vipdoc/ds/minline"  # 替换为输出目录
    output_filename = "27#HZ5017.lc1"  # 输出文件名

    # 拼装目录名和文件名成为一个完整的文件路径名
    output_path = os.path.join(output_dir, output_filename)

    # 读取两个文件的数据
    print("正在读取第一个文件...")
    file1_data = read_tdx_min_file(input_file1)

    print("正在读取第二个文件...")
    file2_data = read_tdx_min_file(input_file2)

    if not file1_data and not file2_data:
        print("文件1、2都没有数据，程序退出")
        return

    # 合并数据
    print("正在合并文件1、2数据...")
    merged_data = merge_minute_data(file1_data, file2_data)
    if not merged_data:
        print("合并文件1、2数据不成功。")
    else:
        print("文件1、2数据合并成功！")

    print("正在做时间排序，并剔除重复数据...")
    sorted_data = sort_min_time_data(merged_data)
    if not sorted_data:
        print("数据排序不成功。")
    else:
        print("时间排序成功完成！")

    # 验证时间序列
    print("正在验证时间序列...")
    is_valid = validate_datetime_sequence(sorted_data,output_path)

    if not is_valid:
        response = input("时间序列存在异常间隔，是否继续写入文件？(y/n): ")
        if response.lower() != 'y':
            print("用户取消操作")
            return

    # 写入合并后的文件
    print("正在写入合并后的文件...")
    success = write_tdx_min_file( sorted_data, output_path)

    if success:
        print("文件数据合并完成。")
    else:
        print("文件合并失败！")

if __name__ == "__main__":
    main()
