import struct
import os
import glob
# from asyncio import print_call_graph
from datetime import datetime, timedelta
from pathlib import Path
import keyboard

from OpenTdxMin import format_minute_datetime_obj, read_tdx_min_file
from pyfileOpen.DeleteTDXLC1 import delete_min_file, read_tdx_min_file2
# from pyfileOpen.OpenTdxMin import format_minute_datetime_obj

# 判断按'Esc'键中断处理过程，可保证不破坏文件
def check_for_exit():
    """检查是否按下了退出键"""
    # if keyboard.is_pressed('CTRL+q') or keyboard.is_pressed('esc'):
    if keyboard.is_pressed('CTRL+shift+q') :
        return True
    return False

def sort_delete_min_time_data( all_data, start_dt ):
    # 按年月日和时分间戳进行排序
    sorted_data1 = sorted ( all_data, key=lambda x:( x['datetime'], x['timestamp'] ))

    # 检查时间连续性并处理不连续的情况
    deleted_data = []
    prev_timestamp = None
    # current_date = None
    number_of_deleted = 0   #  用于计算删除指定时间点前的记录数量
    number_of_repetitions = 0   #  用于计算重复记录的数量

    for i, record in enumerate(sorted_data1):
        current_date_code = record['datetime']
        current_timestamp = record['timestamp']
        current_date = format_minute_datetime_obj( current_date_code, current_timestamp )

        if current_date < start_dt :  # 如果当前记录的时间小于需要的起始时间，为不需要的数据，跳过即删除
            number_of_deleted = number_of_deleted + 1
            #prev_timestamp = current_timestamp
            continue

        # 如果是第一条记录，直接添加
        if prev_timestamp is None:
            deleted_data.append(record)
            prev_timestamp = current_timestamp
            continue

        # 检查时间是否连续
        time_diff = current_timestamp - prev_timestamp

        if time_diff == 0 :  # 如果时间差为0 为重复数据需要剔除
            number_of_repetitions = number_of_repetitions + 1   # 计算重复记录数
            prev_timestamp = current_timestamp
            # print(f"发现重复数据，时间点: {prev_timestamp} -> {current_timestamp} (间隔: {time_diff} 分钟)")
            continue

        # 如果时间差大于1分钟但小于5分钟，可能是正常间隔
        # 如果时间差很大，说明有不连续的时段，781为13:01，690为11:30，这是午间休息停止交易的时间段，以下是适合1分钟数据的判断
        #if time_diff > 5 and prev_timestamp != 690 and current_timestamp != 781 :  # 假设5分钟以上的间隔视为不连续
        #    print(f"发现不连续时间段: {prev_timestamp} -> {current_timestamp} (间隔: {time_diff} 分钟)，在记录: {i} 处。")

        # 添加需要的数据
        deleted_data.append(record)
        prev_timestamp = current_timestamp

    print(f"排序删除剔重后共有 {len(deleted_data)} 条记录，剔除 {number_of_repetitions} 条重复记录，删除了 {number_of_deleted} 条记录。")
    return deleted_data

def write_tdx_min_file(data_list, output_path):
    """
    将数据写入通达信分钟线数据文件
    """
    if len( data_list ) == 0 :
        print("数据长度为 0 ，删除文件。")

        try:
            # 确保输出目录存在
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            # 删除指定的文件
            os.remove(output_path)
            print(f"文件 '{output_path}' 已成功删除。")
        except FileNotFoundError:
            print(f"错误：文件 '{output_path}' 不存在。")
        except PermissionError:
            print(f"错误：没有权限删除文件 '{output_path}'。")
        except Exception as e:
            print(f"删除文件时发生未知错误：{e}")

        return True

    try:
        # 确保输出目录存在
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # last_date = None
        with open(output_path, 'wb') as f:
            for record in data_list:
                # 将日期时间转换回通达信格式，因需要原样写回原格式文件，所以考虑性能前期就不做转换
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
def delete_min_data(input_filename, start_dt):
    """
    合并通达信分钟线.lc1或.lc5文件
    :param input_filename: 需要删除的文件路径列表
    :param start_dt: 需要保留的分钟数据开始时间
    """
    # 这里填入您之前已经写好的合并逻辑
    print("正在读取第一个文件...")
    file1_data = read_tdx_min_file(input_filename)

    if not file1_data :
        print(f"文件 {input_filename} 没有数据，程序退出")
        return
    else:
        print(f"从文件 {input_filename} 读取到 {len(file1_data)} 条数据。")

    # 删除指定时间点前的数据
    print("正在做时间排序，并剔除指点时间点前的数据和重复数据...")
    sorted_delete_data = sort_delete_min_time_data( file1_data, start_dt )
    if not sorted_delete_data:
        print("数据排序、删除剃重不成功。")
    else:
        print("时间排序、删除剔重成功完成！")

    # 例如：逐个读取input_files中的文件，解析并合并数据，最后写入output_filename
    # 写入合并后的文件
    print("正在写入删除后的文件...")
    success = write_tdx_min_file(sorted_delete_data, input_filename)

    if success:
        print("合并数据文件写入完成。")
    else:
        print("合并数据文件写入失败！")


def batch_delete_vipdoc(vipdoc_root_path, import_start_date_time):
    """
    批量处理VIPDOC目录下的所有分钟线数据
    :param vipdoc_root_path: VIPDOC的根目录路径，例如 'D:/new_tdx/vipdoc'
    :param import_start_date_time:  需要保留的K线数据开始时间
    """
    vipdoc_path = Path(vipdoc_root_path)
    start_dt = datetime.strptime(import_start_date_time, f"%Y%m%d")

    # 1. 定义一个字典来规划我们要处理哪些市场和数据类型
    # 键：市场目录名 (e.g., 'sh', 'sz')
    # 值：一个列表，包含要处理的数据类型子目录名 (e.g., 'minline', 'fzline', 'lday')
    target_structures = {
        'bj': ['minline', 'fzline', 'lday'],
        'ds': ['minline', 'fzline', 'lday'],
        'sh': ['minline', 'fzline', 'lday'],
        'sz': ['minline', 'fzline', 'lday']
        # 如果您还有其他市场，例如北京交易所('bj')，可以在这里添加
    }

    # 2. 遍历我们定义的市场和数据类型
    for market, data_types in target_structures.items():
        market_path = vipdoc_path / market

        if not market_path.exists():
            print(f"警告：市场目录 {market_path} 不存在，跳过。")
            continue

        for data_type in data_types:
            data_type_path = market_path / data_type

            print(data_type_path)

            if not data_type_path.exists():
                print(f"警告：数据类型目录 {data_type_path} 不存在，跳过。")
                continue

            # 3. 在目标目录下查找所有的 .lc1 和 .lc5 文件
            # 使用 glob 模式匹配，例如：匹配 /sh/minline/*.lc1 和 /sh/minline/*.lc5
            pattern_lc1 = os.path.join(data_type_path, '*.lc1')
            pattern_lc5 = os.path.join(data_type_path, '*.lc5')
            pattern_lday = os.path.join(data_type_path, '*.day')

            file_list_lc1 = glob.glob(pattern_lc1)
            file_list_lc5 = glob.glob(pattern_lc5)
            file_list_day = glob.glob(pattern_lday)

            print(f"从{data_type_path}读取了 {len(file_list_lc1)}个lc1文件。")
            print(f"从{data_type_path}读取了 {len(file_list_lc5)}个lc5文件。")
            print(f"从{data_type_path}读取了 {len(file_list_day)}个day文件。")

            for long_file1 in file_list_lc1[:5]:
                print(long_file1)

            for long_file3 in file_list_lc5[:5]:
                print(long_file3)

            for long_file4 in file_list_day[:5]:
                print(long_file4)

            file_list_lc1_lc5 = file_list_lc1 + file_list_lc5

            # 4. 按股票代码对文件进行分组
            # 例如：将 'sh600000.lc1' 和 'sh600000.lc5' 分为一组，代码为 '600000'
            file_groups = {}
            for file_path in file_list_lc1_lc5:
                filename = os.path.basename(file_path)  # e.g., 'sh600000.lc1'
                # print(filename)

                # 提取股票代码：去掉市场前缀和文件扩展名
                # 假设文件名格式为 [市场][代码].[扩展名]
                # stock_code = filename.replace(market, '').split('.')[0]  # e.g., '600000'
                stock_code = filename

                if stock_code not in file_groups:
                    file_groups[stock_code] = []
                file_groups[stock_code].append(file_path)

            # 5. 对同一只股票的相同数据类型文件（.lc1 或 .lc5）进行合并
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
                # print(input_filename,output_filename)

                # 调用您写好的合并函数
                try:
                    delete_min_data(input_filename, start_dt )
                except Exception as e:
                    print(f"处理股票 {market}{filename} 时发生错误: {e}")

                if check_for_exit():
                    response = input("是否取消删除此类分钟文件中早于指定时间的数据？(y/n): ")
                    if response.lower() == 'y':
                        print("用户取消操作")
                        break
                    else:
                        continue

    print("所有市场和数据类型的批量处理完成！")

def batch_delete_min_file( vipdoc_root_path ) :
    vipdoc_path = Path(vipdoc_root_path)
    deleted_files_num = 0
    operating_files_num = 0
    # 1. 定义一个字典来规划我们要处理哪些市场和数据类型
    # 键：市场目录名 (e.g., 'sh', 'sz')
    # 值：一个列表，包含要处理的数据类型子目录名 (e.g., 'minline', 'fzline', 'lday')
    target_structures = {
        'bj': ['minline', 'fzline', 'lday'],
        'ds': ['minline', 'fzline', 'lday'],
        'sh': ['minline', 'fzline', 'lday'],
        'sz': ['minline', 'fzline', 'lday']
        # 如果您还有其他市场，例如北京交易所('bj')，可以在这里添加
    }

# 2. 遍历我们定义的市场和数据类型
    for market, data_types in target_structures.items():
        market_path = vipdoc_path / market

        if not market_path.exists():
            print(f"警告：市场目录 {market_path} 不存在，跳过。")
            continue

        for data_type in data_types:
            data_type_path = market_path / data_type

            print(data_type_path)

            if not data_type_path.exists():
                print(f"警告：数据类型目录 {data_type_path} 不存在，跳过。")
                continue

            # 3. 在目标目录下查找所有的 .lc1 和 .lc5 文件
            # 使用 glob 模式匹配，例如：匹配 /sh/minline/*.lc1 和 /sh/minline/*.lc5
            pattern_lc1 = os.path.join(data_type_path, '*.lc1')
            pattern_lc5 = os.path.join(data_type_path, '*.lc5')
            pattern_lday = os.path.join(data_type_path, '*.day')

            file_list_lc1 = glob.glob(pattern_lc1)
            file_list_lc5 = glob.glob(pattern_lc5)
            file_list_day = glob.glob(pattern_lday)

            print(f"从{data_type_path}读取了 {len(file_list_lc1)}个lc1文件。")
            print(f"从{data_type_path}读取了 {len(file_list_lc5)}个lc5文件。")
            print(f"从{data_type_path}读取了 {len(file_list_day)}个day文件。")

            for long_file1 in file_list_lc1[:5]:
                print(long_file1)

            for long_file3 in file_list_lc5[:5]:
                print(long_file3)

            for long_file4 in file_list_day[:5]:
                print(long_file4)

            file_list_lc1_lc5 = file_list_lc1 + file_list_lc5

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

            # 5. 对同一只股票的相同数据类型文件（.lc1 或 .lc5）进行合并
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
                print(input_filename)
                min_data = read_tdx_min_file2(input_filename)
                if not min_data:
                    print("未读取到分钟数据的最后日期")
                else:
                    #datetime_str = format_min_date_obj( min_data[0]['begin_date'], min_data[0]['begin_time'])
                    #end_date_time = datetime.strptime(datetime_str, '%Y%m%d %H:%M:%S')
                    end_date_time = format_minute_datetime_obj( min_data[0]['datetime'], min_data[0]['timestamp'] )
                    if datetime.now() - end_date_time >= timedelta( days = 10950 ):
                        print(f"数据文件中最后更新的交易日期早于1095天（三年前）730(两年前)，故删除文件。")
                        delete_min_file(input_filename)
                        deleted_files_num += 1

                for data in min_data:  # 打印前20条记录
                    print(
                        f"Datetime: {data['datetime']} {data['timestamp']},Open: {data['open']}, High: {data['high']}, Low: {data['low']},"
                        f" Close: {data['close']}, Volume: {data['volume']}, Amount: {data['amount']}, Spare: {data['spare']}")

                operating_files_num += 1

                if check_for_exit():
                    response = input("是否停止删除此类分钟文件？(y/n): ")
                    if response.lower() == 'y':
                        print("用户取消操作")
                        break
                    else:
                        continue

    print(f"所有市场和数据类型的批量处理完成！共处理 {operating_files_num} 个文件，共删除 {deleted_files_num} 个文件。")
    return deleted_files_num


# 使用示例
def main():
    tdx_vipdoc_dir = r'D:\new_hxzq_hc\vipdoc'  # 请修改为您的通达信VIPDOC实际路径
    start_date_time = '19900101' # 请修改为您需要删除的时间点，这个时间点前的分钟K线数据将删除
    # 为计算整体作业所花费的时间，先记录开始作业的时间
    begin_time = datetime.now()
    is_right = 0
    batch_delete_min_file( tdx_vipdoc_dir )
    end_time = datetime.now()
    delta_time = abs(end_time - begin_time)
    print(f"删除已停止交易的数据文件，任务开始时间 {begin_time.strftime('%Y/%m/%d %H:%M:%S')}，结束时间 {end_time.strftime('%Y/%m/%d %H:%M:%S')}, 共用时 {delta_time}")
    if is_right != 0:
        response = input(f"已删除 {is_right} 个文件，\n  是否继续删除文件中早于指定时间的数据？(y/n): ")
        if response.lower() != 'y':
            print("用户取消操作")
            return
    else:
        response = input(f"已删除 {is_right} 个文件，是否继续删除文件中早于设定时间的数据？(y/n): ")
        if response.lower() != 'y':
            print("用户取消操作")
            return

    begin_time = datetime.now()
    batch_delete_vipdoc( tdx_vipdoc_dir, start_date_time )
    end_time = datetime.now()
    delta_time = abs(end_time - begin_time)
    print(f"删除早于指定日期的分钟数据，处理开始时间 {begin_time.strftime('%Y/%m/%d %H:%M:%S')}，结束时间 {end_time.strftime('%Y/%m/%d %H:%M:%S')}, 共用时 {delta_time}")

if __name__ == '__main__':
    main()