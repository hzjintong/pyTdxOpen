import struct
from datetime import datetime, timedelta
from http.client import responses

import holidays
import calendar


# import os

def format_day_date_str(date_int):
    """将整数日期转换为YYYYMMDD格式字符串"""
    year = date_int // 10000
    month = (date_int % 10000) // 100
    day = date_int % 100
    return f"{year:04d}-{month:02d}-{day:02d}"

def format_day_date_obj(date_int):
    """测试直接转换为时间结构数据"""
    date_str = str(date_int)
    return datetime.strptime(date_str,"%Y%m%d")

def parse_tdx_day_record( record_buffer ):
    """
    解析解包通达信分钟线数据记录
    假设格式为: <2H5f2I (小端字节序)
    """
    try:
        # 解析二进制数据，扩展市场的数据格式似乎要用这个格式来解析，如38#8_ATY.day美国十年期国债利率，无须除100
        min_line_data = struct.unpack('<I5f2I', record_buffer)

        # 返回解析后的数据
        return {
            'datetime': min_line_data[0] ,
            'open': min_line_data[1],
            'high': min_line_data[2],
            'low': min_line_data[3],
            'close': min_line_data[4],
            'amount': min_line_data[5],
            'volume': min_line_data[6],
            'spare': min_line_data[7]
        }
    except struct.error as error:
        print(f"解析记录时出错: {error}")
        return None

def read_tdx_day_file(file_path, start_date=None, end_date=None):
    """
    读取通达信日线数据文件
    格式: 日期(4), 开盘价(4), 最高价(4), 最低价(4), 收盘价(4), 成交额(4), 成交量(4), 保留(4)
    """
    data_list = []

    try :
        with open(file_path, 'rb') as f:
            buffer = f.read()
            size = len(buffer)
            record_size = 32  # 每条记录32字节

            record_number = size // record_size

            if record_number != 0 :
                print(f"文件中共有（{record_number}）条记录。")

            if size % record_size != 0 :
                print(f"警告: 文件大小({size}字节)不是{record_size}字节的整数倍，可能存在数据不完整")

            for record_location in range(0, size, record_size):
                if record_location + record_size > size:
                    break
                # 解析二进制数据
                day_line_data = parse_tdx_day_record( buffer[record_location : record_location + record_size] )

                # 转换为日期对象，为后续判断时间范围用
                day_record_date = format_day_date_obj(day_line_data['datetime'])

                if start_date is not None:
                    start_date_date = datetime.strptime(start_date,f"%Y-%m-%d")

                if end_date is not None:
                    end_date_date = datetime.strptime(end_date,f"%Y-%m-%d")

                # 过滤指定时间段
                if (start_date is None or day_record_date >= start_date_date) and \
                        (end_date is None or day_record_date <= end_date_date):
                    data_list.append({
                        'datetime': day_line_data['datetime'],
                        'open': day_line_data['open'],  # 原单位为分，需除100换算成元
                        'high': day_line_data['high'],
                        'low': day_line_data['low'],
                        'close': day_line_data['close'],
                        'amount': day_line_data['amount'],  # 成交额默认单位是元，除1万转换单位为(万元)也可以不除，看后续的计算需要
                        'volume': day_line_data['volume'],  # 成交量(手)
                        'spare': day_line_data['spare']  # 备用
                    })
        print(f"从 {file_path} 读取了 {len(data_list)} 条记录")
        return data_list

    except Exception as e:
        print(f"读取文件 {file_path} 时出错: {e}")
        return []

def validate_date_sequence(data_list):
    """
    验证时间序列的连续性
    """
    if not data_list:
        print("数据列表为空")
        return False

    prev_timestamp = format_day_date_obj(data_list[0]['datetime'])
    gaps = []
    repe = []
    is_valid = True
    cn_holidays = holidays.country_holidays('CN') # 可指定国家，‘CN’为中国，‘US’为美国，也可指定判断金融市场的假期和休市情况

    for i in range(1, len(data_list)):
        current_timestamp = format_day_date_obj(data_list[i]['datetime'])
        time_diff = abs( current_timestamp - prev_timestamp )

        # 检查是否有重复数据
        if time_diff == timedelta( days = 0 ):
            repe.append({
                'position': i,
                'prev_time': prev_timestamp,
                'current_time': current_timestamp,
                'rep_day': time_diff
            })
            prev_timestamp = current_timestamp
            continue

        # 检查时间间隔是否合理
        if time_diff > timedelta( days = 1 ):  # 大于3天的间隔视为可能有问题

            # 如果时间差很大，说明有不连续的时段
            if prev_timestamp.weekday() == 4 and time_diff == timedelta( days= 3 ) :  # 前一个日期是周五，说明中间间隔的应该是周六和周日
                if current_timestamp.weekday() == 0 and time_diff == timedelta( days= 3 ) :  # 再确认下当前是否是周一，双重确认
                    print(f"{prev_timestamp.date()} -> {current_timestamp.date()} 之间是周六、周日的时间间隔。")
                    prev_timestamp = current_timestamp
                    continue

            #print(f"发现不连续时间段: {prev_timestamp.date()} -> {current_timestamp.date()} (间隔: {time_diff.days} 天)")

            gaps.append({
                'position': i,
                'prev_time': prev_timestamp,
                'current_time': current_timestamp,
                'gap_days': time_diff
            })

        prev_timestamp = current_timestamp

    if repe:
        print(f"发现 {len(repe)} 处记录重复：")
        response = input("是否列印重复记录数据信息？(y/n): ")
        if response.lower() == 'y':
            for rep in repe:
                print(f" 位置 {rep['position']}: {rep['prev_time'].date()} -> {rep['current_time'].date()} (间隔: {rep['rep_day'].days} 天)")
        is_valid = False

    if gaps:
        print(f"发现 {len(gaps)} 处时间间隔异常:")
        response = input("时间序列存在异常间隔，是否列印间隔异常数据信息？(y/n): ")
        if response.lower() == 'y':
            one_day = timedelta(days=1)
            for gap in gaps:
                print(
                    f"  位置 {gap['position']}: {gap['prev_time'].date()} -> {gap['current_time'].date()} (间隔: {gap['gap_days'].days-1} 天)")
                current_days = gap['prev_time'] + one_day
                while current_days < gap['current_time']:
                    #if current_days in cn_holidays:
                    print(f"    日期：{current_days.date()} 是假日： {cn_holidays.get(current_days)}")
                    current_days += one_day
        is_valid = False

    else:
        print("时间序列连续，没有发现异常间隔。\n")
        return is_valid

    return is_valid

# 使用示例
def main():
    # 指定需要读取的文件名及其完整路径，38#8_ATY为美国十年期国债利率，属于扩展行情数据，通达信中代码ATY属于宏观指标数据。历史数据中间有中断
    filepath = "D:/new_hxzq_hc/vipdoc/ds/lday/38#9_930994.day"
    start_date_time = "1990-04-15"
    end_date_time = "2026-12-31"
    #尝试调用
    try:
        # 读取日线数据
        day_data = read_tdx_day_file(filepath,start_date_time,end_date_time)
        # day_data = read_tdx_day_file(filepath)

        is_valid = validate_date_sequence(day_data)

        if not is_valid:
            response = input("时间序列存在异常间隔。\n是否继续列印文件样例数据？(y/n): ")
            if response.lower() != 'y':
                print("用户取消操作")
                return

        if len(day_data) != 0 :
            print(f"获取到指定时间范围内共 {len(day_data)} 条数据记录。")
            print("日线数据:")
            i = 0
            for i, data in enumerate(day_data[0:10]):  # 只打印前5条
                print(f"{format_day_date_obj(data['datetime']).date()}: Open:{data['open']} High:{data['high']} Low:{data['low']} Close:{data['close']}"
                      f" Volume:{data['volume']} Amount:{data['amount']} Spare:{data['spare']}")
            print(f"共打印 {i + 1} 条记录。")
            i = 0
            for i, data in enumerate(day_data[len(day_data)-10:len(day_data)]):  # 只打印后5条
                print(
                    f"{format_day_date_obj(data['datetime']).date()}: Open:{data['open']} High:{data['high']} Low:{data['low']} Close:{data['close']}"
                    f" Volume:{data['volume']} Amount:{data['amount']} Spare:{data['spare']}")
            print(f"共打印 {i + 1} 条记录。")

        else :
            print("没有读取到指定时间范围内的数据。")
        print("\n...\n")

    except Exception as er:
        print(f"读取文件时发生错误：{er}。" )

if __name__ == "__main__":
    main()