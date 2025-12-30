#!/usr/bin/env python3
import struct
import pandas as pd
import os


def extract_wdz_data(file_path, max_records=1000):
    """
    快速提取WDZ数据
    """

    # 已知格式
    header_format = '<4sIIIII8sH10s'
    record_format = '<IIffffffIfI12s'

    header_size = struct.calcsize(header_format)
    record_size = struct.calcsize(record_format)

    with open(file_path, 'rb') as f:
        # 1. 解析头
        header_data = struct.unpack(header_format, f.read(header_size))

        print("=== 文件头信息 ===")
        headers = [
            f"文件标识: {header_data[0].decode('gbk', errors='ignore').strip(chr(0))}",
            f"版本号: {header_data[1]}",
            f"记录大小: {header_data[2]}",
            f"总记录数: {header_data[3]}",
            f"开始日期: {header_data[4]} ({str(header_data[4])[:4]}-{str(header_data[4])[4:6]}-{str(header_data[4])[6:8]})",
            f"结束日期: {header_data[5]}",
            f"证券代码: {header_data[6].decode('gbk', errors='ignore').strip(chr(0))}",
            f"周期类型: {header_data[7]}",
        ]

        for h in headers:
            print(h)

        # 2. 解析数据
        records = []
        for i in range(min(max_records, header_data[3])):
            try:
                record_bytes = f.read(record_size)
                if not record_bytes:
                    break

                record = struct.unpack(record_format, record_bytes)

                # 解析日期时间
                date_str = str(record[0]).zfill(8)
                time_str = str(record[1]).zfill(6)

                datetime_str = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
                if record[1] > 0:
                    datetime_str += f" {time_str[:2]}:{time_str[2:4]}:{time_str[4:6]}"

                # 创建记录字典
                record_dict = {
                    'datetime': datetime_str,
                    'date': date_str,
                    'time': time_str,
                    'open': record[2],
                    'high': record[3],
                    'low': record[4],
                    'close': record[5],
                    'volume': record[6],
                    'amount': record[7],
                    'trade_count': record[8],
                    'pre_close': record[9],
                    'open_interest': record[10],
                }

                records.append(record_dict)

                # 显示前5条记录
                if i < 5:
                    print(f"\n记录 {i + 1}:")
                    for key, value in record_dict.items():
                        if isinstance(value, float):
                            print(f"  {key:15}: {value:.4f}")
                        elif key in ['volume', 'amount']:
                            print(f"  {key:15}: {value:,.2f}")
                        else:
                            print(f"  {key:15}: {value}")

            except Exception as e:
                print(f"解析记录 {i + 1} 时出错: {e}")
                break

        print(f"\n成功解析 {len(records)} 条记录")

        # 3. 创建DataFrame
        if records:
            df = pd.DataFrame(records)

            # 设置datetime为索引
            if 'datetime' in df.columns:
                # 尝试转换为datetime类型
                try:
                    df['datetime'] = pd.to_datetime(df['datetime'])
                    df.set_index('datetime', inplace=True)
                except:
                    pass

            return df

    return None


# 使用示例
if __name__ == "__main__":
    file_path = r"G:\D盘备份1\证券股票\分钟数据\wstock_SHSZ_201701_5Min.wdz"

    if os.path.exists(file_path):
        print(f"正在提取数据: {file_path}")
        df = extract_wdz_data(file_path, max_records=50)

        if df is not None:
            print(f"\n=== DataFrame信息 ===")
            print(f"形状: {df.shape}")
            print(f"\n前10行数据:")
            print(df.head(10))

            print(f"\n数据统计:")
            print(df.describe())

            # 保存为CSV
            save_option = input("\n是否保存为CSV文件? (y/N): ").strip().lower()
            if save_option == 'y':
                output_file = file_path.replace('.wdz', '.csv')
                df.to_csv(output_file, encoding='utf-8-sig')
                print(f"数据已保存到: {output_file}")
    else:
        print(f"文件不存在: {file_path}")