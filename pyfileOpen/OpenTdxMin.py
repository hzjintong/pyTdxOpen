import struct
from datetime import datetime, timedelta
import holidays


# from sympy.physics.units import amount
# import os

def format_minute_datetime_str(date_code, minutes_past_midnight):
    # 解码计算日期和时间
    # 日期解码（参考多种方法）
    year = int (date_code / 2048) + 2004
    month = int (date_code % 2048) // 100
    day = int (date_code % 2048) % 100
    # 解码计算时间
    hour = minutes_past_midnight // 60
    minute = minutes_past_midnight % 60
    # 返回日期和时间的格式字符串
    return f"{year:04d}/{month:02d}/{day:02d} {hour:02d}:{minute:02d}"

def format_minute_datetime_obj(date_code, minutes_past_midnight):
    # 解码计算日期和时间
    # 日期解码（参考多种方法）
    datetime_str = format_minute_datetime_str(date_code, minutes_past_midnight)
    # 返回日期和时间的对象类型
    return datetime.strptime(datetime_str,"%Y/%m/%d %H:%M")

def parse_tdx_minute_record( record_buffer ):
    """
    解析解包通达信分钟线数据记录
    假设格式为: <2H5f2I (小端字节序)
    """
    try:
        # 解析二进制数据
        min_line_data = struct.unpack('<2H5f2I', record_buffer)

        # 返回解析后的数据
        return {
            'datetime': min_line_data[0] ,
            'timestamp': min_line_data[1],
            'open': min_line_data[2],
            'high': min_line_data[3],
            'low': min_line_data[4],
            'close': min_line_data[5],
            'amount': min_line_data[6],
            'volume': min_line_data[7],
            'spare': min_line_data[8]
        }
    except struct.error as error:
        print(f"解析记录时出错: {error}")
        return None

def read_tdx_min_file(file_path, start_datetime=None, end_datetime=None):
    """
    读取通达信分钟线数据文件
    格式: 日期(2), 时间(2), 开盘价(4), 最高价(4), 最低价(4), 收盘价(4), 成交额(4), 成交量(4)
    """
    data_list = []
    try:
        with open(file_path, 'rb') as f:
            buffer = f.read()
            size = len(buffer)
            record_size = 32  # 每条记录32字节

            record_number = size // record_size

            if record_number != 0 :
                print(f"文件{file_path}中约有（{record_number}）条记录。")

            if size % record_size != 0 :
                print(f"警告: 文件大小({size}字节)不是{record_size}字节的整数倍，可能存在数据不完整")

            for record_location in range(0, size, record_size):
                if record_location + record_size > size:
                    break

                # 调用新的二进数据解析方法，表达更清晰
                min_record_data = parse_tdx_minute_record( buffer[record_location:record_location + record_size] )

                # 转换解码日期数据格式
                t0 = format_minute_datetime_obj(min_record_data['datetime'], min_record_data['timestamp'])
                if start_datetime is not None:
                    t1 = datetime.strptime(start_datetime, f'%Y/%m/%d %H:%M')
                if end_datetime is not None:
                    t2 = datetime.strptime(end_datetime, f'%Y/%m/%d %H:%M')

                # 过滤指定时间段
                if (start_datetime is None or t0 >= t1) and \
                        (end_datetime is None or t0 <= t2):
                    data_list.append( min_record_data )

        return data_list

    except Exception as er:
        print(f"读取文件 {file_path} 时出错: {er}")
        return []

def validate_datetime_sequence(data_list):
    """
    验证时间序列的连续性
    """
    if not data_list:
        print("数据列表为空")
        return False

    prev_timestamp = format_minute_datetime_obj(data_list[0]['datetime'], data_list[0]['timestamp'])
    gaps = []
    repe = []
    its_minute = None  # 定义判断是那种分钟数据，并进行标识
    is_valid = True
    cn_holidays = holidays.country_holidays('CN')  # 可指定国家，‘CN’为中国，‘US’为美国，也可指定判断金融市场的假期和休市情况

    for i in range(1, len(data_list)):
        current_timestamp = format_minute_datetime_obj(data_list[i]['datetime'], data_list[i]['timestamp'])
        time_diff = ( current_timestamp - prev_timestamp )  # 测试是否要加ABS，是否允许负值

        # 检查是否有重复数据
        if time_diff == timedelta( minutes = 0 ):
            repe.append({
                'position': i,
                'prev_time': prev_timestamp,
                'current_time': current_timestamp,
                'rep_day': time_diff
            })
            prev_timestamp = current_timestamp
            continue

        if its_minute is None:
            if time_diff == timedelta( minutes = 1 ):
                print("这是 1 分钟的K线数据。")
                its_minute = 1
            else :
                if time_diff == timedelta( minutes = 5 ):
                    print("这是 5 分钟的K线数据。")
                    its_minute = 5

        # 检查时间间隔是否合理
        if its_minute ==1 and time_diff == timedelta( minutes = 1 ):
            prev_timestamp = current_timestamp
            continue

        if its_minute == 5 and time_diff == timedelta( minutes = 5 ):
            prev_timestamp = current_timestamp
            continue

        # 检查时间间隔是否合理，午休时间间隔
        if its_minute == 1 and time_diff == timedelta( hours = 1, minutes = 31 ):
            prev_timestamp = current_timestamp
            continue

        if its_minute == 5 and time_diff == timedelta( hours = 1, minutes = 35 ):
            prev_timestamp = current_timestamp
            continue

        # 检查时间间隔是否合理，次日时间间隔
        if its_minute == 1 and time_diff == timedelta( hours = 18, minutes = 31 ):
            prev_timestamp = current_timestamp
            continue

        if its_minute == 5 and time_diff == timedelta( hours = 18, minutes = 35 ):
            prev_timestamp = current_timestamp
            continue

        # 日常交易一分钟的数据次日应判断大于18小时31分的间隔视为异常间隔
        # 日常交易五分钟的数据次日应判断大于18小时35分的间隔视为可能有问题
        if (its_minute == 1 and
            (time_diff >= timedelta( hours = 17 ,minutes = 31 ) or time_diff >= timedelta( hours = 18 ,minutes = 31 ))):

            # 如果是1分钟数据文件，时间差大于下列值，且前一天不是周五，当前不是周一，说明有不连续的时段
            if (prev_timestamp.weekday() == 4 and
                ( time_diff == timedelta( days = 2 ,hours = 17, minutes = 31 ) or
                    time_diff == timedelta( days = 2, hours = 18, minutes = 31 )) ) :  # 前一个日期是周五，说明中间间隔的应该是周六和周日
                if current_timestamp.weekday() == 0 :  # 再确认下当前是否是周一，双重确认
                    print(f"{prev_timestamp.date()} -> {current_timestamp.date()} 之间是周六、周日的时间间隔。")
                    prev_timestamp = current_timestamp
                    continue

        if (its_minute == 5 and
            (time_diff >= timedelta( hours=17, minutes=35) or time_diff >= timedelta( hours=18, minutes=35 ))):

            # 如果是5分钟数据文件，时间差大于下列值，且前一天不是周五，当前不是周一，说明有不连续的时段
            if (prev_timestamp.weekday() == 4 and
                (time_diff == timedelta( days = 2, hours = 17, minutes = 35) or
                    time_diff == timedelta( days = 2, hours = 18, minutes =35 )) ):  # 前一个日期是周五，说明中间间隔的应该是周六和周日
                if current_timestamp.weekday() == 0 :  # 再确认下当前是否是周一，双重确认
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
            for rep in repe[:10]:
                # print(f" 位置 {rep['position']}: {rep['prev_time'].date()} -> {rep['current_time'].date()} (间隔: {rep['rep_day'].days} 天)")
                print(
                    f" 位置 {rep['position']}: {rep['prev_time']} -> {rep['current_time']} (间隔: {rep['rep_day']} 小时。)")
        is_valid = False

    if gaps:
        print(f"发现 {len(gaps)} 处时间间隔异常:")
        response = input("时间序列存在异常间隔，是否列印间隔异常数据信息？(y/n): ")
        if response.lower() == 'y':
            one_day = timedelta(days=1)
            for gap in gaps[:]:
                print(
                    f"  位置 {gap['position']}: {gap['prev_time']} -> {gap['current_time']} (间隔: {gap['gap_days']} ) ")
                current_timestamp = gap['prev_time'] + one_day
                while current_timestamp < gap['current_time']:
                    print(f"    日期：{current_timestamp} 是假日： {cn_holidays.get(current_timestamp)}")
                    current_timestamp += one_day
        is_valid = False

    else:
        if is_valid:
            print("时间序列连续，没有发现异常间隔。")

    return is_valid

# 使用示例
def main():
    filepath = r"G:\D盘备份1\new_hxzq_hc\vipdoc\sh\minline\sh171753.lc1"  # 指定需要读取的文件名及其完整路径
    start_date_time = "1990/01/01 09:20"
    end_date_time = "2025/12/31 19:40"
    # 尝试调用
    try:
        # 读取1分钟线数据1
        # min_data = read_tdx_min_file(filepath, start_datetime=start_date_time, end_datetime=end_date_time)
        min_data = read_tdx_min_file(filepath)
        is_valid = validate_datetime_sequence(min_data)

        if not is_valid:
            response = input("时间序列存在异常间隔，是否继续列印文件首尾样例数据？(y/n): ")
            if response.lower() != 'y':
                print("用户取消操作")
                return

        if len(min_data) != 0 :
            print(f"获取到指定时间范围内的分钟数据共 {len(min_data)} 条。")
            print("列印分钟线数据:")
            i = 0
            for i, data in enumerate(min_data[0:245]):  # 只打印前241条
                min_line_datetime = format_minute_datetime_str(data['datetime'], data['timestamp'])
                print(f"{min_line_datetime}: Open: {data['open']} High: {data['high']} Low: {data['low']} Close: {data['close']}"
                      f" Volume: {data['volume']} Amount: {data['amount']} Spare: {data['spare']}")
            print(f"已列印 { i + 1 } 条记录。")
            i = 0
            for i, data in enumerate(min_data[len(min_data)-245:len(min_data)]):  # 只打印后241条
                min_line_datetime = format_minute_datetime_str(data['datetime'], data['timestamp'])
                print(f"{min_line_datetime}: Open: {data['open']} High: {data['high']} Low: {data['low']} Close: {data['close']}"
                      f" Volume: {data['volume']} Amount: {data['amount']} Spare: {data['spare']}")
            print(f"已列印 { i + 1 } 条记录。")
        else:
            print("没有读取到指定时间范围内的数据。")
        print("\n...\n")

    except Exception as e:
        print(f"读取文件时发生错误: {e}")

if __name__ == "__main__":
    main()