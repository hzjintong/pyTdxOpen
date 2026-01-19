
from pyfileOpen.OpenTdxMin import read_tdx_min_file, format_minute_datetime_str, validate_datetime_sequence

# 使用示例
def main():
    file_path = r"F:\new_tdx\vipdoc\sz\fzline\SZ300069.lc5"
    start_datetime = None
    end_datetime = None
    # 尝试调用
    try:
        # 读取5分钟线数据1
        min_data = read_tdx_min_file(file_path, start_datetime, end_datetime)
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
            for i, data in enumerate(min_data[0:241]):  # 只打印前60条
                min_line_datetime = format_minute_datetime_str(data['datetime'], data['timestamp'])
                print(f"{min_line_datetime}: Open: {data['open']} High: {data['high']} Low: {data['low']} Close: {data['close']}"
                      f" Volume: {data['volume']} Amount: {data['amount']} Spare: {data['spare']}")
            print(f"已列印 { i + 1 } 条记录。")
            i = 0
            for i, data in enumerate(min_data[len(min_data) - 241:len(min_data)]):  # 只打印后241条
                min_line_datetime = format_minute_datetime_str(data['datetime'], data['timestamp'])
                print(
                    f"{min_line_datetime}: Open: {data['open']} High: {data['high']} Low: {data['low']} Close: {data['close']}"
                    f" Volume: {data['volume']} Amount: {data['amount']} Spare: {data['spare']}")
            print(f"已列印 {i + 1} 条记录。")
        else:
            print("没有读取到指定时间范围内的数据。")
        print("\n...\n")

    except Exception as e:
        print(f"读取文件时发生错误: {e}")

if __name__ == "__main__":
    main()