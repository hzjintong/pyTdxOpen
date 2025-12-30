import os
# import glob
from datetime import datetime, timedelta
from pyfileOpen.OpenTdxMin import format_minute_datetime_obj, parse_tdx_minute_record
# from pathlib import Path

def read_tdx_min_file2( file_path ) :
    try :
        # 打开lc1文件
        with (open(file_path, 'rb') as openfile):
            buffer = openfile.read()
            size = len( buffer)
            # 初始化一个列表来存储解析后的数据
            kline_data = []
            # 每条记录的长度为32个字节
            record_size = 32

            if size % record_size != 0:
                print(f"警告: 文件大小({size}字节)不是{record_size}字节的整数倍，可能存在数据不完整")

            # 计算记录数量
            record_count = size // record_size

            print(f"共有 {record_count} 条记录。")

            record = parse_tdx_minute_record(buffer[ (record_count-1) * record_size : size ])
            if record:
                kline_data.append(record)

        print(f"从 {file_path} 读取了 {len(kline_data)} 条记录")
        return kline_data

    except Exception as err:
        print(f"读取文件 {file_path} 时出错: {err}")
    return []

def delete_min_file(file_path) :
    try:
        # 确保输出目录存在
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        # 删除当前指定的文件
        os.remove(file_path)
        print(f"文件 '{file_path}' 已成功删除。")
    except FileNotFoundError:
        print(f"错误：文件 '{file_path}' 不存在。")
    except PermissionError:
        print(f"错误：没有权限删除文件 '{file_path}'。")
        return False
    except Exception as er:
        print(f"删除文件时发生未知错误：{er}")
        return False
    return True

def delete_min_file2(file_path) :
    try:
        file_path.unlink() # `unlink()` 是 Path 对象删除文件的方法
        print(f"文件 '{file_path}' 已成功删除。")
    except FileNotFoundError:
        print(f"错误：文件 '{file_path}' 不存在。")
        return False
    except PermissionError:
        print(f"错误：没有权限删除文件 '{file_path}'。")
        return False
    except Exception as e:
        print(f"删除文件时发生未知错误：{e}")
        return False
    return True

def main():
    try :
        input_path="D:\\new_tdx\\vipdoc\\ds\\minline\\27#HZ5328.lc1"
        min_data = read_tdx_min_file2( input_path )
        print("分钟线数据:")
        #datetime_str = format_minute_datetime_str( min_data[0]['begin_date'], min_data[0]['begin_time'])
        #end_date_time = datetime.strptime(datetime_str, '%Y/%m/%d %H:%M:%S')
        end_date_time = format_minute_datetime_obj(min_data[0]['begin_date'], min_data[0]['begin_time'])
        if datetime.now()-end_date_time >= timedelta(days=1095):
            # 删除最后交易日数据为1095天前（即距今已经三年）的分钟数据文件，
            delete_min_file(input_path)

        for data in min_data :  #打印前20条记录
            print(f"Datetime: {end_date_time},Open: {data['open']}, High: {data['high']}, Low: {data['low']},"
                  f" Close: {data['close']}, Volume: {data['volume']}, Amount: {data['amount']}, Spare: {data['spare']}")

        if len( min_data ) == 0 :
            print("数据长度为 0 ")

        print(f"文件共有 {len( min_data )} 条记录。")
    except Exception as e:
        print(f"读取文件时发生错误：{e}")

if __name__ == "__main__":
    main()
