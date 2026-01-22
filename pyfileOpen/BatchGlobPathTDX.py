import struct
import os
import glob
import csv   # 新增：用于处理CSV输出
import keyboard
from datetime import datetime,timedelta
from pathlib import Path

from MergeTDXday import merge_day_data, read_tdx_day_file, sort_day_time_data, write_tdx_day_file

# 判断按'Esc'键中断处理过程，可保证不破坏文件
def check_for_exit():
    """检查是否按下了退出键"""
    # if keyboard.is_pressed('CTRL+q') or keyboard.is_pressed('esc'):
    if keyboard.is_pressed('CTRL+q') :
        return True
    return False

# 合并两处数据文件中的数据

def parse_tdx_minute_record( record_buffer ):
    """
    解析解包通达信分钟线数据记录
    假设格式为: <2H5f2I (小端字节序)
    """
    try:
        # 解析二进制数据
        data = struct.unpack('<2H5f2I', record_buffer)

        # 计算日期和时间
        date_code = data[0]
        minutes_past_midnight = data[1]
        # 做数据合并时，无需日期时间的解码，减少计算量，提高速度
        # year = int(date_code / 2048) + 2004
        # month_day = date_code % 2048
        # month = int(month_day / 100)
        # day = month_day % 100

        # 计算时间
        # hour = minutes_past_midnight // 60
        # minute = minutes_past_midnight % 60

        # date_str = f"{year:04d}-{month:02d}-{day:02d}"
        # time_str = f"{hour:02d}:{minute:02d}:00"  # 秒数通常为00
        # datetime_str = f"{date_str} {time_str}"

        # 返回解析后的数据
        return {
            'datetime': date_code ,
            'timestamp': minutes_past_midnight,
            'open': data[2],
            'high': data[3],
            'low': data[4],
            'close': data[5],
            'amount': data[6],
            'volume': data[7],
            'spare': data[8]
        }
    except struct.error as e:
        print(f"解析记录时出错: {e}")
        return None

def read_tdx_min_file(file_path):
    """
    读取通达信分钟线数据文件
    """
    data_list = []

    try:
        with open(file_path, 'rb') as f:
            buffer = f.read()
            size = len(buffer)
            record_size = 32

            for i in range(0, size, record_size):
                if i + record_size > size:
                    break

                record = parse_tdx_minute_record( buffer[ i:i + record_size ] )
                if record:
                    data_list.append(record)

        print(f"从 {file_path} 读取了 {len(data_list)} 条记录")
        return data_list
    except Exception as e:
        print(f"读取文件 {file_path} 时出错: {e}")
        return []

def merge_minute_data(file1_data, file2_data):
    """
    合并两个分钟数据文件的数据
    """
    # 合并所有数据
    all_data = file1_data + file2_data

    print(f"合并后共有 {len(all_data)} 条记录，可能含重复记录。")
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
                # record_date = record['datetime']

                # 提取时间部分
                # minutes_since_midnight = record['timestamp']

                # 打包数据
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

        print(f"已写入 {len(data_list)} 条记录到 {output_path}")
        return True
    except Exception as e:
        print(f"写入文件 {output_path} 时出错: {e}")
        return False

# 假设这是您之前写好的合并函数
def merge_min_data(input_filename, output_filename):
    """
    合并通达信分钟线.lc1或.lc5文件
    :param input_filename: 需要合并的文件路径列表
    :param output_filename: 合并后输出的文件路径
    """
    # 这里填入您之前已经写好的合并逻辑
    print("正在读取第一个文件...")
    file1_data = read_tdx_min_file(input_filename)

    print("正在读取第二个文件...")
    file2_data = read_tdx_min_file(output_filename)

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
        print("时间排序剔重成功完成！")

    # 例如：逐个读取input_files中的文件，解析并合并数据，最后写入output_filename
    # 写入合并后的文件
    print(f"正在写入合并后的数据到输出文件{output_filename} ...")
    success = write_tdx_min_file(sorted_data, output_filename)
    if success:
        print("合并数据文件写入指定 输出 目录完成。")
    else:
        print(f"合并数据文件写入到输出目录 {output_filename} 失败！")
# -------++++++++=============================================================================++++++++-------
    # 例如：逐个读取input_files中的文件，解析并合并数据，最后也写入input_filename
    # 写入合并后的文件,作为一种备份。
    #print(f"正在写入合并后的数据到输入文件{input_filename}...")
    #success1 = write_tdx_min_file(sorted_data, input_filename)
    #if success1:
    #    print("合并数据文件写入指定 输入 目录完成。")
    #else:
    #    print(f"合并数据文件写入到输入目录 {input_filename} 失败！")


def merge_lday_data(input_filename, output_filename):
    """
    合并通达信日线.day文件
    :param input_filename: 需要合并的文件路径列表
    :param output_filename: 合并后输出的文件路径
    """
    # 这里填入您之前已经写好的合并逻辑
    print("正在读取第一个文件...")
    file1_data = read_tdx_day_file(input_filename)

    print("正在读取第二个文件...")
    file2_data = read_tdx_day_file(output_filename)

    if not file1_data and not file2_data:
        print("文件1、2都没有数据，程序退出")
        return

    # 合并数据
    print("正在合并文件1、2数据...")
    merged_data = merge_day_data(file1_data, file2_data)
    if not merged_data:
        print("合并文件1、2数据不成功。")
    else:
        print("文件1、2数据合并成功！")

    print("正在做时间排序，并剔除重复数据...")
    sorted_data = sort_day_time_data(merged_data)
    if not sorted_data:
        print("数据排序不成功。")
    else:
        print("时间排序剔重成功完成！")

    # 例如：逐个读取input_files中的文件，解析并合并数据，最后写入output_filename
    # 写入合并后的文件
    print(F"正在写入合并后的数据到输出文件{output_filename}...")
    success = write_tdx_day_file(sorted_data, output_filename)

    if success:
        print("合并数据文件写入 输出 目录完成。")
    else:
        print(f"合并数据文件写入到 输出 目录 {output_filename} 失败！")

    # print(f"开始合并 {len(input_files)} 个文件到 {output_filename}")
    # ... your existing code here ...
    #print(f"合并完成！输出文件：{output_filename}")
# -------++++++++=============================================================================++++++++-------
    # 例如：逐个读取input_files中的文件，解析并合并数据，最后也写入input_filename
    # 写入合并后的文件,作为一种备份。
    #print(f"正在写入合并后的数据到输入文件{input_filename}...")
    #success1 = write_tdx_day_file(sorted_data, input_filename)
    #if success1:
    #    print("合并数据文件写入指定 输入 目录完成。")
    #else:
    #    print(f"合并数据文件写入到输入目录 {input_filename} 失败！")


def batch_merge_vipdoc(vipdoc_root_path, vipdoc_home_path, target_structures ):
    """
    批量处理VIPDOC目录下的所有分钟线数据
    :param vipdoc_root_path: VIPDOC的根目录路径，例如 'D:/new_hxzq_hc/vipdoc'
    :param vipdoc_home_path: VIPDOC的源目录路径 'D:/new_tdx/vipdoc'
    :param target_structures: VIPDOC目录下的结构,市场目录bj（北京）,ds（扩展市场）,sh（上海证券交易所）,sz（深圳证券交易所）,分类数据目录minline（1分钟）,fzline（5分钟）,lday（日线）
    """
    vipdoc_path = Path( vipdoc_root_path )
    vipdoc_path2 = Path( vipdoc_home_path )

    file_num = 0  # 设置一个处理文件数量的计数器

    # 1. 定义一个字典来规划我们要处理哪些市场和数据类型，修改为从外部传参

    # 2. 遍历我们定义的市场和数据类型
    for market, data_types in target_structures.items():
        market_path = vipdoc_path / market
        market_path2 = vipdoc_path2 / market

        if not market_path.exists():
            print(f"警告：市场目录 {market_path} 不存在，跳过。")
            #continue

        if not market_path2.exists():
            print(f"警告：市场目录 {market_path2} 不存在，跳过。")
            #continue

        for data_type in data_types:

            data_type_path = market_path / data_type
            data_type_path2 = market_path2 / data_type

            print(data_type_path)
            print(data_type_path2)

            if not data_type_path.exists():
                print(f"警告：数据类型目录 {data_type_path} 不存在，跳过。")
                #continue

            if not data_type_path2.exists():
                print(f"警告：数据类型目录 {data_type_path2} 不存在，跳过。")
                #continue

            # 3. 在目标目录下查找所有的 .lc1 和 .lc5 文件
            # 使用 glob 模式匹配，例如：匹配 /sh/minline/*.lc1、/sh/minline/*.lc5和/sh/lday/*.day
            pattern_lc1 = os.path.join(data_type_path, '*.lc1')
            pattern_lc12 = os.path.join(data_type_path2, '*.lc1')
            pattern_lc5 = os.path.join(data_type_path, '*.lc5')
            pattern_lc52 = os.path.join(data_type_path2, '*.lc5')
            pattern_lday = os.path.join(data_type_path, '*.day')
            pattern_lday2 = os.path.join(data_type_path2, '*.day')

            file_list_lc1 = glob.glob(pattern_lc1)
            file_list_lc12 = glob.glob(pattern_lc12)
            file_list_lc5 = glob.glob(pattern_lc5)
            file_list_lc52 = glob.glob(pattern_lc52)
            file_list_day = glob.glob(pattern_lday)
            file_list_day2 = glob.glob(pattern_lday2)

            print(f"从{data_type_path}读取了 {len(file_list_lc1)}个lc1文件。")
            print(f"从{data_type_path2}读取了 {len(file_list_lc12)}个lc1文件。")
            print(f"从{data_type_path}读取了 {len(file_list_lc5)}个lc5文件。")
            print(f"从{data_type_path2}读取了 {len(file_list_lc52)}个lc5文件。")
            print(f"从{data_type_path}读取了 {len(file_list_day)}个day文件。")
            print(f"从{data_type_path2}读取了 {len(file_list_day2)}个day文件。")

            for long_file1 in file_list_lc1[:3]:
                print(long_file1)

            for long_file2 in file_list_lc12[:3]:
                print(long_file2)

            for long_file3 in file_list_lc5[:3]:
                print(long_file3)

            for long_file4 in file_list_lc52[:3]:
                print(long_file4)

            for long_file4 in file_list_day[:3]:
                print(long_file4)

            for long_file4 in file_list_day2[:3]:
                print(long_file4)

            file_list_lc1_lc5 = file_list_lc1 + file_list_lc5 # + file_list_lc12 + file_list_lc52
            file_list_lday = file_list_day # + file_list_day2
            print(f"读取 分钟文件 总数 {len(file_list_lc1_lc5)}")
            print(f"读取 日线文件 总数 {len(file_list_lday)}")


            # 4. 按股票代码对文件进行分组
            # 例如：将 'sh600000.lc1' 和 'sh600000.lc5' 分为一组，代码为 '600000'
            file_groups = {}
            for file_path in file_list_lc1_lc5:
                filename = os.path.basename(file_path)  # e.g., 'sh600000.lc1'

                # 提取股票代码：去掉市场前缀和文件扩展名
                # 假设文件名格式为 [市场][代码].[扩展名]
                # stock_code = filename.replace(market, '').split('.')[0]  # e.g., '600000'
                stock_code = filename

                if stock_code not in file_groups:
                    file_groups[stock_code] = []
                file_groups[stock_code].append(file_path)

            print(f"file_groups共有 {len(file_groups)} 个分钟文件待融合清洗处理。")

            # 5. 对同一只股票的相同数据类型文件（.lc1 或 .lc5）进行数据合并
            # for stock_code, files in file_groups.items():
            for filename, files in file_groups.items() :
                # 确保文件列表不为空
                if not files:
                    continue

                # 确定输出文件名
                # 例如：将输出文件命名为 sh600000_ALL.lc1
                # 注意：通达信通常识别 .lc1 (1分钟) 或 .lc5 (5分钟)，
                # 但合并后的自定义文件最好使用其他扩展名或放在其他目录，以免被软件误读。
                # 这里我们输出为 .dat 文件作为示例，您也可以选择其他方式。
                # output_filename = data_type_path / f"{market}{stock_code}_ALL.dat"
                input_filename = data_type_path / f"{filename}"
                output_filename = data_type_path2 / f"{filename}"
                #print(input_filename,output_filename)
                # 调用您写好的合并函数
                try:
                    merge_min_data(input_filename, output_filename)
                except Exception as e:
                    print(f"处理股票 {market}{filename} 时发生错误: {e}")

                file_num = file_num + 1

                if check_for_exit():
                    response = input("是否取消合并此类分钟文件数据？(y/n): ")
                    if response.lower() == 'y':
                        print("用户取消操作")
                        break
                    else:
                        continue

            # 6. 对同一只股票的相同数据类型文件（.day）进行数据合并
            file_groups = {}
            for file_path in file_list_lday :
                filename = os.path.basename(file_path)

                stock_code = filename
                if stock_code not in file_groups :
                    file_groups[stock_code] = []
                file_groups[stock_code].append(file_path)

            print(f"file_groups共有 {len(file_groups)} 个日线文件待融合清洗处理。")

            for filename,files in file_groups.items() :
                # 确保文件列表不为空
                if not files :
                    continue
                input_filename = data_type_path / f"{filename}"
                output_filename = data_type_path2 / f"{filename}"
                #print(f"Input filename:{input_filename} ， Output filename: {output_filename} 。")

                try:
                    merge_lday_data(input_filename,output_filename)
                except Exception as e:
                    print(f"处理股票 {market}{filename} 时发生错误：{e}")
                file_num = file_num + 1

                if check_for_exit():
                    response = input("是否取消合并此类日线文件数据？(y/n): ")
                    if response.lower() == 'y':
                        print("用户取消操作")
                        break
                    else:
                        continue

    return file_num  #修改缩进了两次，届时回退

# 使用示例
def main():
    tdx_vipdoc_dir = "D:/new_hxzq_hc/vipdoc"  # 请修改为您的通达信VIPDOC实际路径
    taget_vipdoc_path = 'G:/D盘备份1/new_hxzq_hc/vipdoc' # 请修改为您的其他数据的实际路径
    # 键：市场目录名 (e.g., 'sh', 'sz')
    # 值：一个列表，包含要处理的数据类型子目录名 (e.g., 'minline', 'fzline', 'lday')
    path_structures = {
        'bj': ['minline', 'fzline', 'lday'],
        'ds': ['minline', 'fzline', 'lday'],
        'sh': ['minline', 'fzline', 'lday'],
        'sz': ['minline', 'fzline', 'lday']
        # 如果您还有其他市场，例如北京交易所('bj')，可以在这里添加
    }

    print(f"读取数据目录： {tdx_vipdoc_dir} ， 并入数据的目标目录：{taget_vipdoc_path} 。")
    response = input("是否确认执行上述两个目录数据的合并、融合与清洗(y/n): ")
    if response.lower() != 'y':
        print("用户取消了操作，程序退出。")
        return False

    try:
        # 为计算整体作业所花费的时间，先记录开始作业的时间
        begin_time = datetime.now()
        file_op_num = batch_merge_vipdoc(tdx_vipdoc_dir, taget_vipdoc_path, path_structures)
        end_time = datetime.now()
        print(f"共处理了 {file_op_num} 个文件，所有市场和数据类型的批量处理完成！")
        delta_time = abs( end_time - begin_time )
        print(f"处理开始时间 {begin_time.strftime('%Y/%m/%d %H:%M')}，结束时间 {end_time.strftime('%Y/%m/%d %H:%M:%S')}, 共用时 { delta_time }")
    except Exception as er:
        print(f"文件处理异常，错误为：{er}")

if __name__ == '__main__':
    main()
