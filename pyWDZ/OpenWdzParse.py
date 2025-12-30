#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
万得(Wind) WDZ文件解析器
适用于证券历史K线数据文件
文件名格式：wstock_市场_代码_周期.wdz
示例：wstock_SHSZ_2000_5Min.wdz
尝试找到匹配格式
"""

import os
import struct
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
import mmap
from typing import Dict, List, Tuple, Optional


class WindWDZParser:
    """
    解析万得金融终端WDZ格式数据文件
    支持日线、分钟线等K线数据
    """

    # WDZ文件头结构（基于公开的逆向工程）
    # 注意：万得未公开官方格式，这是社区分析的结果
    WDZ_HEADER_FORMAT = {
        'magic': '4s',  # 文件标识，通常是'WDT'或'WDF'
        'version': 'I',  # 版本号
        'record_size': 'I',  # 每条记录的大小
        'record_count': 'I',  # 记录总数
        'start_date': 'I',  # 起始日期（YYYYMMDD格式）
        'end_date': 'I',  # 结束日期
        'code': '8s',  # 证券代码（如'000001.SZ'）
        'period': 'H',  # 周期类型：1=日线，5=5分钟，15=15分钟等
        'reserved': '10s',  # 保留字段
    }

    # K线记录结构（根据周期不同可能略有差异）
    KLINE_RECORD_FORMAT = {
        'date': 'I',  # 日期：YYYYMMDD
        'time': 'I',  # 时间：HHMMSS（对于分钟线）
        'open': 'f',  # 开盘价
        'high': 'f',  # 最高价
        'low': 'f',  # 最低价
        'close': 'f',  # 收盘价
        'volume': 'f',  # 成交量（手）
        'amount': 'f',  # 成交额（元）
        'trade_count': 'I',  # 成交笔数（可选）
        'pre_close': 'f',  # 前收盘价（可选）
        'settle': 'f',  # 结算价（期货用）
        'open_interest': 'I',  # 持仓量（期货用）
        'reserved': '12s',  # 保留字段
    }

    def __init__(self, file_path: str):
        """初始化解析器"""
        self.file_path = Path(file_path)
        if not self.file_path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        self.file_size = self.file_path.stat().st_size
        self.header = {}
        self.records = []
        self.df = None

    def parse_file(self, max_records: int = 100) -> pd.DataFrame:
        """解析WDZ文件，返回DataFrame"""

        print(f"正在解析文件: {self.file_path.name}")
        print(f"文件大小: {self.file_size:,} 字节")

        with open(self.file_path, 'rb') as f:
            # 1. 解析文件头
            header_data = self._parse_header(f)
            print("\n=== 文件头信息 ===")
            for key, value in header_data.items():
                print(f"{key:15}: {value}")

            # 2. 解析数据记录
            records = self._parse_records(f, max_records)

            # 3. 转换为DataFrame
            self.df = self._to_dataframe(records)

            return self.df

    def _parse_header(self, file_obj) -> Dict:
        """解析WDZ文件头"""

        # 构建格式字符串
        fmt = ''.join(self.WDZ_HEADER_FORMAT.values())
        header_size = struct.calcsize(fmt)

        # 读取头数据
        raw_header = file_obj.read(header_size)
        if len(raw_header) < header_size:
            raise ValueError("文件头不完整")

        # 解包数据
        values = struct.unpack(fmt, raw_header)

        # 映射到字典
        header = {}
        for i, (key, fmt_char) in enumerate(self.WDZ_HEADER_FORMAT.items()):
            value = values[i]

            # 特殊处理
            if key == 'magic':
                value = value.decode('gbk', errors='ignore').strip('\x00')
            elif key == 'code':
                value = value.decode('gbk', errors='ignore').strip('\x00')
            elif key == 'reserved':
                continue  # 跳过保留字段
            elif key == 'period':
                # 转换周期类型
                period_map = {
                    1: '日线',
                    5: '5分钟',
                    15: '15分钟',
                    30: '30分钟',
                    60: '60分钟',
                    240: '日线',  # 有些系统用240表示日线
                }
                value = period_map.get(value, f'未知({value})')

            header[key] = value

        # 根据文件名补充信息
        filename = self.file_path.stem
        parts = filename.split('_')
        if len(parts) >= 4:
            header['market'] = parts[1]  # SHSZ
            header['stock_code'] = parts[2]  # 2000
            header['period_from_name'] = parts[3] if len(parts) > 3 else ''

        self.header = header
        return header

    def _parse_records(self, file_obj, max_records: int = 100) -> List[Dict]:
        """解析K线数据记录"""

        records = []

        # 构建记录格式字符串
        fmt = ''.join(self.KLINE_RECORD_FORMAT.values())
        record_size = struct.calcsize(fmt)

        print(f"\n记录大小: {record_size} 字节")
        print(f"最大解析记录数: {max_records}")

        # 计算预期记录数
        expected_records = self.header.get('record_count', 0)
        if expected_records > 0:
            print(f"文件头声明的记录数: {expected_records}")

        # 逐条解析记录
        for i in range(max_records):
            try:
                # 读取一条记录
                raw_record = file_obj.read(record_size)
                if not raw_record:
                    break  # 文件结束

                if len(raw_record) < record_size:
                    print(f"警告: 记录 {i} 不完整")
                    break

                # 解包记录
                values = struct.unpack(fmt, raw_record)

                # 转换为字典
                record = {}
                for j, (key, fmt_char) in enumerate(self.KLINE_RECORD_FORMAT.items()):
                    value = values[j]

                    # 特殊处理
                    if key == 'date':
                        # 转换为日期字符串
                        date_str = str(value)
                        if len(date_str) == 8:
                            record['date_str'] = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"

                    elif key == 'time' and value > 0:
                        # 转换为时间字符串
                        time_str = str(value).zfill(6)
                        record['time_str'] = f"{time_str[:2]}:{time_str[2:4]}:{time_str[4:6]}"

                        # 创建完整的datetime
                        if 'date_str' in record:
                            record['datetime'] = datetime.strptime(
                                f"{record['date_str']} {record['time_str']}",
                                "%Y-%m-%d %H:%M:%S"
                            )

                    # 保留原始值
                    record[key] = value

                records.append(record)

                # 每解析100条记录打印进度
                if (i + 1) % 100 == 0 and i > 0:
                    print(f"已解析 {i + 1} 条记录...")

            except struct.error as e:
                print(f"解析记录 {i} 时出错: {e}")
                break

        print(f"实际解析记录数: {len(records)}")
        return records

    def _to_dataframe(self, records: List[Dict]) -> pd.DataFrame:
        """将记录列表转换为pandas DataFrame"""

        if not records:
            return pd.DataFrame()

        # 创建DataFrame
        df = pd.DataFrame(records)

        # 设置索引
        if 'datetime' in df.columns:
            df.set_index('datetime', inplace=True)
        elif 'date_str' in df.columns:
            df.set_index('date_str', inplace=True)

        # 重命名列（中文化）
        column_map = {
            'open': '开盘价',
            'high': '最高价',
            'low': '最低价',
            'close': '收盘价',
            'volume': '成交量',
            'amount': '成交额',
            'pre_close': '前收盘',
            'trade_count': '成交笔数',
        }

        df.rename(columns=column_map, inplace=True)

        # 重新排序列
        preferred_order = ['开盘价', '最高价', '最低价', '收盘价', '成交量', '成交额', '前收盘']
        existing_cols = [col for col in preferred_order if col in df.columns]
        other_cols = [col for col in df.columns if col not in existing_cols]

        df = df[existing_cols + other_cols]

        return df

    def print_sample_data(self, num_rows: int = 10):
        """打印样本数据"""

        if self.df is None:
            print("请先调用 parse_file() 方法解析文件")
            return

        print(f"\n=== 前 {num_rows} 条K线数据 ===")
        print(self.df.head(num_rows))

        if len(self.df) > 0:
            print(f"\n=== 数据统计摘要 ===")
            print(f"时间范围: {self.df.index[0]} 到 {self.df.index[-1]}")
            print(f"总记录数: {len(self.df)}")

            if '收盘价' in self.df.columns:
                print(f"收盘价统计:")
                print(f"  最小值: {self.df['收盘价'].min():.2f}")
                print(f"  最大值: {self.df['收盘价'].max():.2f}")
                print(f"  平均值: {self.df['收盘价'].mean():.2f}")

            if '成交量' in self.df.columns:
                print(f"总成交量: {self.df['成交量'].sum():,.0f} 手")

    def save_to_csv(self, output_path: str = None):
        """保存为CSV文件"""

        if self.df is None or self.df.empty:
            print("没有数据可保存")
            return

        if output_path is None:
            # 自动生成输出文件名
            code = self.header.get('stock_code', 'unknown')
            period = self.header.get('period', 'unknown').replace('/', '_')
            output_path = f"{code}_{period}_kline.csv"

        self.df.to_csv(output_path, encoding='utf-8-sig')
        print(f"数据已保存到: {output_path}")
        print(f"记录数: {len(self.df)}")


# 使用示例
def main():
    """主函数"""

    # 替换为你的WDZ文件路径
    wdz_file = r"G:\D盘备份1\证券股票\分钟数据\wstock_SHSZ_201701_5Min.wdz"

    if not os.path.exists(wdz_file):
        print(f"文件不存在: {wdz_file}")

        # 尝试查找WDZ文件
        wdz_files = list(Path('../pyfileOpen').glob('*.wdz'))
        if wdz_files:
            print(f"当前目录找到以下WDZ文件:")
            for i, f in enumerate(wdz_files):
                print(f"  {i + 1}. {f.name}")

            choice = input("请选择文件编号 (直接回车选择第一个): ").strip()
            if choice.isdigit() and 1 <= int(choice) <= len(wdz_files):
                wdz_file = str(wdz_files[int(choice) - 1])
            else:
                wdz_file = str(wdz_files[0])
            print(f"使用文件: {wdz_file}")
        else:
            print("当前目录没有找到.wdz文件")
            return

    try:
        # 创建解析器
        parser = WindWDZParser(wdz_file)

        # 解析文件（最多1000条记录）
        df = parser.parse_file(max_records=1000)

        # 打印样本数据
        parser.print_sample_data(num_rows=20)

        # 保存为CSV（可选）
        save_option = input("\n是否保存为CSV文件? (y/N): ").strip().lower()
        if save_option == 'y':
            parser.save_to_csv()

        print("\n解析完成!")

    except Exception as e:
        print(f"解析过程中出错: {e}")
        import traceback
        traceback.print_exc()


# 增强版：尝试多种格式解析
class AdvancedWDZParser(WindWDZParser):
    """
    增强版WDZ解析器，尝试多种格式
    """

    def _try_multiple_formats(self, file_obj, max_records=100):
        """尝试多种格式解析"""

        formats_to_try = [
            # 格式1: 标准Wind格式
            {
                'header': '<4sIIIII8sH10s',
                'record': '<IIffffffIfI12s',
            },
            # 格式2: 简化版（无时间戳）
            {
                'header': '<4sIIII8sH10s',
                'record': '<IffffffI12s',
            },
            # 格式3: 包含更多字段
            {
                'header': '<4sIIII8sH16s',
                'record': '<IIffffffffI12s',
            }
        ]

        for i, fmt in enumerate(formats_to_try, 1):
            print(f"\n尝试格式 {i}...")
            file_obj.seek(0)  # 重置文件指针

            try:
                # 尝试解析头
                header_size = struct.calcsize(fmt['header'])
                raw_header = file_obj.read(header_size)
                header = struct.unpack(fmt['header'], raw_header)

                print(f"  头信息: {header[:6]}...")

                # 尝试解析几条记录
                record_size = struct.calcsize(fmt['record'])
                records = []

                for j in range(min(5, max_records)):
                    raw_record = file_obj.read(record_size)
                    if not raw_record:
                        break

                    record = struct.unpack(fmt['record'], raw_record)
                    records.append(record[:6])  # 只取前几个字段

                print(f"  成功读取 {len(records)} 条记录")
                if records:
                    print(f"  第一条记录: {records[0]}")
                    return fmt, records

            except struct.error:
                continue

        return None, []


if __name__ == "__main__":
    # 运行主函数
    main()

    # 可选：如果标准解析失败，尝试增强版
    retry = input("\n标准解析是否失败？是否尝试增强解析？ (y/N): ").strip().lower()
    if retry == 'y':
        wdz_file = input("请输入WDZ文件路径: ").strip()
        if wdz_file and os.path.exists(wdz_file):
            print("\n=== 尝试增强解析 ===")
            parser = AdvancedWDZParser(wdz_file)

            with open(wdz_file, 'rb') as f:
                fmt, records = parser._try_multiple_formats(f)

                if fmt:
                    print(f"\n找到匹配格式！")
                    print(f"头格式: {fmt['header']}")
                    print(f"记录格式: {fmt['record']}")
                else:
                    print("\n无法识别文件格式")

                    # 显示文件头原始字节
                    with open(wdz_file, 'rb') as f:
                        header_bytes = f.read(100)
                        print(f"文件头前100字节(十六进制):")
                        print(' '.join(f'{b:02x}' for b in header_bytes))

                        print(f"\n文件头前100字节(ASCII):")
                        print(''.join(chr(b) if 32 <= b < 127 else '.' for b in header_bytes))