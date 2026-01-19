import struct
from datetime import datetime
# import os

def format_date(date_int):
    """将整数日期转换为YYYYMMDD格式字符串"""
    year = date_int // 10000
    month = (date_int % 10000) // 100
    day = date_int % 100
    return f"{year:04d}-{month:02d}-{day:02d}"

def format_date2(date_int):
    """测试直接转换为时间结构数据"""
    date_str = str(date_int)
    return datetime.strptime(date_str,"%Y%m%d")


def read_tdx_day_file(file_path, start_date=None, end_date=None):
    """
    读取通达信日线数据文件
    格式: 日期(4), 开盘价(4), 最高价(4), 最低价(4), 收盘价(4), 成交额(4), 成交量(4), 保留(4)
    """
    data_list = []

    with open(file_path, 'rb') as f:
        buffer = f.read()
        size = len(buffer)
        record_size = 32  # 每条记录32字节

        record_number = size // record_size

        if record_number != 0 :
            print(f"文件中约有（{record_number}）条记录。")

        if size % record_size != 0 :
            print(f"警告: 文件大小({size}字节)不是{record_size}字节的整数倍，可能存在数据不完整")

        for i in range(0, size, record_size):
            if i + record_size > size:
                break

            # 解析二进制数据
            data_buffer = struct.unpack('IIIIIfII', buffer[i:i + record_size])

            # 转换数据格式
            date = format_date2(data_buffer[0])
            open_price = data_buffer[1] / 100.0
            high_price = data_buffer[2] / 100.0
            low_price = data_buffer[3] / 100.0
            close_price = data_buffer[4] / 100.0
            amount = data_buffer[5] / 10000.0  # 成交额(万元)
            vol = data_buffer[6]  # 成交量(手)
            spare = data_buffer[7]  # 备用

            if start_date is not None:
                start_date_date = datetime.strptime(start_date,f"%Y-%m-%d")

            if end_date is not None:
                end_date_date = datetime.strptime(end_date,f"%Y-%m-%d")

            # 过滤指定时间段
            if (start_date is None or date >= start_date_date) and \
                    (end_date is None or date <= end_date_date):
                data_list.append({
                    'date': date,
                    'open': open_price,
                    'high': high_price,
                    'low': low_price,
                    'close': close_price,
                    'amount': amount,
                    'volume': vol,
                    'spare': spare
                })

    return data_list


def read_tdx_min_file(file_path, start_datetime=None, end_datetime=None):
    """
    读取通达信分钟线数据文件
    格式: 日期(2), 时间(2), 开盘价(4), 最高价(4), 最低价(4), 收盘价(4), 成交额(4), 成交量(4)
    """
    data_list = []

    with open(file_path, 'rb') as f:
        buffer = f.read()
        size = len(buffer)
        record_size = 32  # 每条记录32字节

        record_number = size // record_size

        if record_number != 0 :
            print(f"文件中约有（{record_number}）条记录。")

        if size % record_size != 0 :
            print(f"警告: 文件大小({size}字节)不是{record_size}字节的整数倍，可能存在数据不完整")

        for i in range(0, size, record_size):
            if i + record_size > size:
                break

            # 解析二进制数据
            data_buffer = struct.unpack('2H5f2i', buffer[i:i + record_size])

            # 转换数据格式
            date_code = data_buffer[0]
            minutes_past_midnight = data_buffer[1]

            # 计算日期和时间
            # 日期解码（参考多种方法）
            # 方法1:cite[1]:
            year = int(date_code / 2048) + 2004
            month_day = date_code % 2048
            month = int(month_day / 100)
            day = month_day % 100


            # 方法2（见于其他来源）: year = math.floor(date_code / 2048) + 2004; 等...
            # 请根据实际数据测试并选择正确的解码方式

            # 时间解码
            hour = minutes_past_midnight // 60
            minute = minutes_past_midnight % 60

            date_str = f"{year:04d}-{month:02d}-{day:02d}"
            time_str = f"{hour:02d}:{minute:02d}"  # 秒数通常为00
            datetime_str = f"{date_str} {time_str}"


            #价格处理 - 假设前4个价格字段是浮点，无需除以100
            open_price = round(data_buffer[2],4)
            high_price = round(data_buffer[3],4)
            low_price = data_buffer[4]
            close_price = data_buffer[5]
            amount = data_buffer[6]  # 成交额(元)
            vol = data_buffer[7]  # 成交量(手)

            # 过滤指定时间段
            data_list.append({
                    'date': date_str,
                    'minutes_past_midnight': time_str,
                    'open': open_price,
                    'high': high_price,
                    'low': low_price,
                    'close': close_price,
                    'amount': amount,
                    'volume': vol
            })

    return data_list


# 使用示例
if __name__ == "__main__":
    # 读取日线数据
    day_data = read_tdx_day_file(r"D:/new_hxzq_hc/vipdoc/ds/lday/44#831039.day", "1990-04-15", "2025-10-22")
    print("日线数据:")
    for ii, data in enumerate(day_data[:60]):  # 只打印前20条
        print(f"{data['date'].date()}: Open:{data['open']} High:{data['high']} Low:{data['low']} Close:{data['close']} Volume:{data['volume']} Amount:{data['amount']} Spare:{data['spare']}")

    print("\n...\n")

    # 读取分钟线数据
    min_data = read_tdx_min_file(r"F:\D盘备份1\new_hxzq_hc\vipdoc\bj\fzline\bj920039.lc5", "1990-06-30 14:53", "2025-12-31 23:59")
    print("分钟线数据:")
    record_num = len(min_data)
    for ii, data in enumerate(min_data[:240]):  # 只打印前60条
        print(f"date:{data['date']} time:{data['minutes_past_midnight']} : Open:{data['open']} High:{data['high']} Low:{data['low']} Close:{data['close']} Volume:{data['volume']} Amount:{data['amount']}")
    print("\n...\n")
    for ii, data in enumerate(min_data[record_num-240:record_num]) :
        print(f"date:{data['date']} time:{data['minutes_past_midnight']} : Open:{data['open']} High:{data['high']} Low:{data['low']} Close:{data['close']} Volume:{data['volume']} Amount:{data['amount']}")