# from pyfileOpen.MergeTDXLC1 import validate_time_sequence
from pyfileOpen.OpenTdxMin import read_tdx_min_file, format_minute_datetime_str,validate_datetime_sequence

# import math
def main():
    input_path = r"D:\new_hxzq_hc\vipdoc\ds\minline\27#HZ5401.lc1"
    start_datetime = "20190101 08:30"
    end_datetime = "20251231 23:59"
    try:
        #min_data = read_tdx_min_file( input_path, start_datetime, end_datetime )
        min_data = read_tdx_min_file( input_path )
        is_valid = validate_datetime_sequence(min_data)

        if not is_valid:
            response = input("时间序列存在异常间隔，是否继续列印文件首尾样例数据？(y/n): ")
            if response.lower() != 'y':
                print("用户取消操作")
                return

        if len(min_data) != 0 :
            print(f"获取到指定时间范围内的分钟数据共 {len(min_data)} 条。")
            print("分钟线数据:")
            i = 0
            for i, data in enumerate(min_data[0:331]):  # 只打印前60条
                min_line_datetime = format_minute_datetime_str(data['datetime'], data['timestamp'])
                print(f"{min_line_datetime}: Open: {data['open']} High: {data['high']} Low: {data['low']} Close: {data['close']}"
                      f" Volume: {data['volume']} Amount: {data['amount']} Spare: {data['spare']}")
            print(f"已列印 { i + 1 } 条记录。")
            print("\n...\n")
            i = 0
            for i, data in enumerate(min_data[len(min_data) - 331:len(min_data)]):  # 只打印后241条
                min_line_datetime = format_minute_datetime_str(data['datetime'], data['timestamp'])
                print(f"{min_line_datetime}: Open: {data['open']} High: {data['high']} Low: {data['low']} Close: {data['close']}"
                      f" Volume: {data['volume']} Amount: {data['amount']} Spare: {data['spare']}")
            print(f"已列印 {i + 1} 条记录。")
        else:
            print("没有读取到指定时间范围内的数据。")
        print("\n...\n")
    except Exception as e:
        print(f"读取文件时发生错误: {e}")

if __name__ == "__main__":
    main()