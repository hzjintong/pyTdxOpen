import struct
from datetime import datetime,timedelta
import os

from pyfileOpen.OpenTdxDay import format_day_date_obj, read_tdx_day_file, validate_date_sequence

# from future.backports.datetime import timedelta
# import shutil
# from operator import itemgetter


def merge_day_data(file1_data, file2_data):
    """
    合并两个分钟数据文件的数据
    """
    # 合并所有数据
    all_data = file1_data + file2_data

    print(f"合并后共有 {len(all_data)} 条记录")
    return all_data


def sort_day_time_data( all_data ):
    # 按年月日和时分间戳进行排序
    sorted_data1 = sorted ( all_data, key=lambda x:( x['datetime'] ))

    # 检查时间连续性并处理不连续的情况
    merged_data = []
    prev_timestamp = None
    number_of_repetitions = 0

    for i, record in enumerate(sorted_data1):
        current_timestamp = record['datetime']  # 作为排序和剃重没有必要做时间对象转换
        # current_timestamp = format_date2(record['datetime'])

        # 如果是第一条记录，直接添加
        if prev_timestamp is None:
            merged_data.append(record)
            prev_timestamp = current_timestamp
            continue

        # 检查时间是否有重复，剔除重复数据
        time_diff = current_timestamp - prev_timestamp

        if time_diff  == 0 : # timedelta( days=0 ) :   如果时间差为0 为重复数据需要剔除
            number_of_repetitions = number_of_repetitions + 1  # 计算重复记录数
            # print(f"发现重复数据，时间点: {prev_timestamp} -> {current_timestamp} (间隔: {time_diff} 天)")
            prev_timestamp = current_timestamp
            continue

        # 添加数据
        merged_data.append(record)
        prev_timestamp = current_timestamp

    print(f"合并排序后共有 {len(merged_data)} 条有效记录，已剔除 {number_of_repetitions} 条重复记录。")
    return merged_data

def write_tdx_day_file(data_list, output_path):
    """
    将数据写入通达信分钟线数据文件
    """

    try:
        # 确保输出目录存在
        os.makedirs(os.path.dirname(output_path), exist_ok=True )

        with open(output_path, 'wb') as f:
            for record in data_list:
                # 将日期时间转换回通达信格式，因需要原样写回原格式文件，所以考虑性能不做转换
                record_date = record['datetime']

                # 提取时间部分
                # minutes_since_midnight = record['timestamp']

                # 打包数据
                record_data = struct.pack('<5If2I',
                                          record_date,
                                          # minutes_since_midnight,
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


def main():
    # 配置输入和输出路径
    input_file1 = "D:/new_hxzq_hc/vipdoc/sh/lday/sh000001.day"  # 替换为第一个文件路径
    input_file2 = "E:/D盘备份1/new_tdx/vipdoc/sh/lday/sh000001.day"  # 替换为第二个文件路径
    # input_file3 = "D:/home1/ds/minline/62#399986.lc1"  # 替换为第三个文件路径
    # input_file4 = "D:/home2/ds/minline/62#399986.lc1"  # 替换为第四个文件路径
    output_dir = "E:/D盘备份1/new_tdx/vipdoc/sh/lday/"  # 替换为输出目录
    output_filename = "sh000001.day"  # 输出文件名

    output_path = os.path.join(output_dir, output_filename)

    # 读取两个文件的数据
    print("正在读取第一个文件...")
    file1_data = read_tdx_day_file(input_file1)

    print("正在读取第二个文件...")
    file2_data = read_tdx_day_file(input_file2)

    # print("正在读取第三个文件...")
    # file3_data = read_tdx_day_file(input_file3)

    # print("正在读取第四个文件...")
    # file4_data = read_tdx_day_file(input_file4)

    if not file1_data and not file2_data:
        print("文件1、2都没有数据，程序退出")
        return
    # if not file3_data and not file4_data:
        # print("文件3、4都没有数据，程序退出")
        # return

    # 合并数据
    print("正在合并文件1、2数据...")
    merged_data = merge_day_data(file1_data, file2_data)
    if not merged_data:
        print("合并文件1、2数据不成功。")
    else:
        print("文件1、2数据合并成功！")

    print("正在做时间排序，并剔除重复数据...")
    sorted_data = sort_day_time_data( merged_data )
    if not sorted_data:
        print("数据排序不成功。")
    else:
        print("时间排序成功完成！")

    # 验证时间序列
    print("正在验证时间序列...")
    is_valid = validate_date_sequence(sorted_data)

    if not is_valid:
        response = input("时间序列存在异常间隔，是否继续写入文件？(y/n): ")
        if response.lower() != 'y':
            print("用户取消操作")
            return

    # 写入合并后的文件
    print("正在写入合并后的文件...")
    success = write_tdx_day_file( sorted_data, output_path)

    if success:
        print("文件数据合并完成。")
    else:
        print("文件合并失败！")


if __name__ == "__main__":
    main()