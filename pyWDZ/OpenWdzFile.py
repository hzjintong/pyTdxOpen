#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
万得WDZ文件解析器 - 根据匹配的格式提取数据
头格式: <4sIIIII8sH10s
记录格式: <IIffffffIfI12s
"""

import struct
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import os
from pathlib import Path
import matplotlib.pyplot as plt
from typing import List, Dict, Tuple, Optional


class WDZDataExtractor:
    """
    根据已识别的格式提取WDZ数据
    """

    def __init__(self, file_path: str):
        self.file_path = Path(file_path)
        self.header_format = '<4sIIIII8sH10s'  # 头格式
        self.record_format = '<IIffffffIfI12s'  # 记录格式

        # 计算结构体大小
        self.header_size = struct.calcsize(self.header_format)
        self.record_size = struct.calcsize(self.record_format)

        # 存储数据
        self.header_data = {}
        self.records = []
        self.dataframe = None

    def parse_file(self) -> pd.DataFrame:
        """解析整个WDZ文件"""

        print(f"解析文件: {self.file_path.name}")
        print(f"文件大小: {os.path.getsize(self.file_path):,} 字节")
        print(f"头格式: {self.header_format}")
        print(f"记录格式: {self.record_format}")
        print(f"记录大小: {self.record_size} 字节")

        with open(self.file_path, 'rb') as f:
            # 1. 解析文件头
            self._parse_header(f)

            # 2. 解析所有记录
            self._parse_all_records(f)

            # 3. 转换为DataFrame
            self.dataframe = self._create_dataframe()

            return self.dataframe

    def _parse_header(self, file_obj):
        """解析文件头"""

        try:
            # 读取并解析头
            header_bytes = file_obj.read(self.header_size)
            header_fields = struct.unpack(self.header_format, header_bytes)

            # 字段名称映射
            field_names = [
                'magic',  # 4s - 文件标识
                'version',  # I  - 版本号
                'record_size',  # I  - 记录大小
                'record_count',  # I  - 记录总数
                'start_date',  # I  - 起始日期
                'end_date',  # I  - 结束日期
                'code',  # 8s - 证券代码
                'period',  # H  - 周期类型
                'reserved',  # 10s - 保留字段
            ]

            # 转换为字典
            for i, (name, value) in enumerate(zip(field_names, header_fields)):
                # 特殊处理字符串字段
                if name in ['magic', 'code', 'reserved']:
                    try:
                        value = value.decode('gbk').strip('\x00')
                    except:
                        value = str(value)

                self.header_data[name] = value

            # 解码周期类型
            period_map = {
                1: '日线',
                5: '5分钟',
                15: '15分钟',
                30: '30分钟',
                60: '60分钟',
                240: '日线',
            }

            period_code = self.header_data.get('period', 0)
            self.header_data['period_str'] = period_map.get(period_code, f'未知({period_code})')

            # 解码日期
            for date_field in ['start_date', 'end_date']:
                date_val = self.header_data.get(date_field)
                if date_val:
                    date_str = str(date_val)
                    if len(date_str) == 8:
                        self.header_data[f'{date_field}_str'] = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"

            print("\n=== 文件头信息 ===")
            for key, value in self.header_data.items():
                print(f"{key:20}: {value}")

        except Exception as e:
            print(f"解析文件头时出错: {e}")
            raise

    def _parse_all_records(self, file_obj):
        """解析所有数据记录"""

        record_count = self.header_data.get('record_count', 0)
        print(f"\n=== 开始解析数据记录 ===")
        print(f"文件头显示记录数: {record_count}")

        # 计算预期的数据大小
        expected_data_size = record_count * self.record_size
        current_pos = file_obj.tell()
        file_obj.seek(0, 2)  # 移动到文件末尾
        file_size = file_obj.tell()
        file_obj.seek(current_pos)  # 回到原位置

        print(f"当前位置: {current_pos}")
        print(f"文件总大小: {file_size}")
        print(f"预期数据大小: {expected_data_size}")
        print(f"可用数据大小: {file_size - current_pos}")

        # 计算实际可读取的记录数
        available_bytes = file_size - current_pos
        max_records = min(record_count, available_bytes // self.record_size)

        print(f"最多可读取记录数: {max_records}")

        # 批量读取以提高性能
        batch_size = 10000
        records_parsed = 0

        self.records = []

        # 字段名称（根据格式推断）
        record_field_names = [
            'date',  # I - 日期 (YYYYMMDD)
            'time',  # I - 时间 (HHMMSS)
            'open',  # f - 开盘价
            'high',  # f - 最高价
            'low',  # f - 最低价
            'close',  # f - 收盘价
            'volume',  # f - 成交量
            'amount',  # f - 成交额
            'trade_count',  # I - 成交笔数
            'pre_close',  # f - 前收盘价
            'open_interest',  # I - 持仓量（期货用）
            'reserved',  # 12s - 保留字段
        ]

        try:
            while records_parsed < max_records:
                # 计算本次读取的记录数
                current_batch = min(batch_size, max_records - records_parsed)

                # 批量读取
                bytes_to_read = current_batch * self.record_size
                raw_data = file_obj.read(bytes_to_read)

                if not raw_data:
                    break

                # 批量解析
                format_string = f'{current_batch}{self.record_format[1:]}'  # 去掉开头的'<'
                batch_records = struct.unpack(format_string, raw_data)

                # 重组为记录列表
                num_fields = len(record_field_names)
                for i in range(current_batch):
                    start_idx = i * num_fields
                    end_idx = start_idx + num_fields
                    record_values = batch_records[start_idx:end_idx]

                    # 创建记录字典
                    record = {}
                    for field_name, value in zip(record_field_names, record_values):
                        record[field_name] = value

                    # 添加解析后的记录
                    self.records.append(record)

                records_parsed += current_batch

                if records_parsed % 100000 == 0:
                    print(f"已解析 {records_parsed:,} 条记录...")

        except Exception as e:
            print(f"解析记录时出错: {e}")

        print(f"\n实际解析记录数: {len(self.records):,}")

    def _create_dataframe(self) -> pd.DataFrame:
        """将记录转换为DataFrame"""

        if not self.records:
            print("没有记录可转换")
            return pd.DataFrame()

        print("\n=== 创建DataFrame ===")

        # 创建基础DataFrame
        df = pd.DataFrame(self.records)

        # 处理日期时间字段
        def create_datetime(row):
            """创建datetime对象"""
            date_str = str(row['date']).zfill(8)
            time_str = str(row['time']).zfill(6)

            try:
                # 如果时间为0，可能是日线数据
                if row['time'] == 0:
                    return datetime.strptime(date_str, "%Y%m%d")
                else:
                    return datetime.strptime(f"{date_str} {time_str[:2]}:{time_str[2:4]}:{time_str[4:6]}",
                                             "%Y%m%d %H:%M:%S")
            except:
                return None

        print("处理日期时间...")
        df['datetime'] = df.apply(create_datetime, axis=1)

        # 设置索引
        if 'datetime' in df.columns:
            df.set_index('datetime', inplace=True)

        # 重命名列（中文化）
        column_mapping = {
            'open': '开盘价',
            'high': '最高价',
            'low': '最低价',
            'close': '收盘价',
            'volume': '成交量',
            'amount': '成交额',
            'trade_count': '成交笔数',
            'pre_close': '前收盘价',
            'open_interest': '持仓量',
        }

        df.rename(columns=column_mapping, inplace=True)

        # 重新排序列
        basic_columns = ['开盘价', '最高价', '最低价', '收盘价', '成交量', '成交额']
        existing_basic = [col for col in basic_columns if col in df.columns]
        other_columns = [col for col in df.columns if col not in existing_basic + ['datetime']]

        df = df[existing_basic + other_columns]

        print(f"DataFrame形状: {df.shape}")
        print(f"时间范围: {df.index.min()} 到 {df.index.max()}")

        return df

    def show_data_summary(self, num_samples: int = 10):
        """显示数据摘要"""

        if self.dataframe is None or self.dataframe.empty:
            print("没有数据可显示")
            return

        print("\n" + "=" * 80)
        print("数据摘要")
        print("=" * 80)

        # 基本信息
        print(f"数据总行数: {len(self.dataframe):,}")
        print(f"数据列数: {len(self.dataframe.columns)}")
        print(f"时间范围: {self.dataframe.index.min()} 到 {self.dataframe.index.max()}")

        # 显示前几行数据
        print(f"\n前{num_samples}条数据:")
        print(self.dataframe.head(num_samples))

        # 显示后几行数据
        print(f"\n后{num_samples}条数据:")
        print(self.dataframe.tail(num_samples))

        # 统计信息
        print("\n基本统计信息:")
        print(self.dataframe.describe())

        # 数据类型
        print("\n数据类型:")
        print(self.dataframe.dtypes)

        # 检查缺失值
        print("\n缺失值检查:")
        print(self.dataframe.isnull().sum())

    def visualize_data(self, column: str = '收盘价',
                       start_date: str = None,
                       end_date: str = None):
        """可视化数据"""

        if self.dataframe is None or self.dataframe.empty:
            print("没有数据可可视化")
            return

        if column not in self.dataframe.columns:
            print(f"列 '{column}' 不存在。可用列: {list(self.dataframe.columns)}")
            return

        # 过滤数据
        df_to_plot = self.dataframe.copy()

        if start_date:
            df_to_plot = df_to_plot[df_to_plot.index >= pd.to_datetime(start_date)]
        if end_date:
            df_to_plot = df_to_plot[df_to_plot.index <= pd.to_datetime(end_date)]

        if df_to_plot.empty:
            print("没有数据在指定时间范围内")
            return

        # 创建图表
        fig, axes = plt.subplots(2, 2, figsize=(16, 10))

        # 1. 价格走势图
        ax1 = axes[0, 0]
        ax1.plot(df_to_plot.index, df_to_plot[column], linewidth=1)
        ax1.set_title(f'{column}走势图')
        ax1.set_xlabel('时间')
        ax1.set_ylabel('价格')
        ax1.grid(True, alpha=0.3)

        # 2. 成交量图
        if '成交量' in df_to_plot.columns:
            ax2 = axes[0, 1]
            ax2.bar(df_to_plot.index, df_to_plot['成交量'], width=0.8, alpha=0.7)
            ax2.set_title('成交量')
            ax2.set_xlabel('时间')
            ax2.set_ylabel('成交量')
            ax2.grid(True, alpha=0.3)

        # 3. 价格分布直方图
        ax3 = axes[1, 0]
        ax3.hist(df_to_plot[column].dropna(), bins=50, alpha=0.7, edgecolor='black')
        ax3.set_title(f'{column}分布直方图')
        ax3.set_xlabel('价格')
        ax3.set_ylabel('频率')
        ax3.grid(True, alpha=0.3)

        # 4. K线图（简化版）
        if all(col in df_to_plot.columns for col in ['开盘价', '最高价', '最低价', '收盘价']):
            ax4 = axes[1, 1]

            # 取前100个点显示K线图，否则太密集
            sample_df = df_to_plot.iloc[-100:] if len(df_to_plot) > 100 else df_to_plot

            # 计算上涨下跌
            colors = ['red' if sample_df['收盘价'].iloc[i] >= sample_df['开盘价'].iloc[i]
                      else 'green' for i in range(len(sample_df))]

            # 绘制K线
            for i in range(len(sample_df)):
                ax4.plot([sample_df.index[i], sample_df.index[i]],
                         [sample_df['最低价'].iloc[i], sample_df['最高价'].iloc[i]],
                         color=colors[i], linewidth=1)

                # 绘制实体
                ax4.plot([sample_df.index[i], sample_df.index[i]],
                         [sample_df['开盘价'].iloc[i], sample_df['收盘价'].iloc[i]],
                         color=colors[i], linewidth=3)

            ax4.set_title('K线图（最近100条）')
            ax4.set_xlabel('时间')
            ax4.set_ylabel('价格')
            ax4.grid(True, alpha=0.3)

        plt.tight_layout()
        plt.show()

    def export_to_csv(self, output_path: str = None):
        """导出数据到CSV文件"""

        if self.dataframe is None or self.dataframe.empty:
            print("没有数据可导出")
            return

        if output_path is None:
            # 自动生成文件名
            code = self.header_data.get('code', 'unknown')
            period = self.header_data.get('period_str', 'unknown').replace('/', '_')
            output_path = f"{code}_{period}_export.csv"

        self.dataframe.to_csv(output_path, encoding='utf-8-sig')
        print(f"数据已导出到: {output_path}")
        print(f"导出记录数: {len(self.dataframe):,}")

    def find_extreme_values(self):
        """找出极端值（最高价、最低价等）"""

        if self.dataframe is None or self.dataframe.empty:
            return

        print("\n" + "=" * 80)
        print("极端值分析")
        print("=" * 80)

        if '最高价' in self.dataframe.columns:
            max_price_idx = self.dataframe['最高价'].idxmax()
            max_price = self.dataframe['最高价'].max()
            print(f"最高价: {max_price:.2f} (时间: {max_price_idx})")

        if '最低价' in self.dataframe.columns:
            min_price_idx = self.dataframe['最低价'].idxmin()
            min_price = self.dataframe['最低价'].min()
            print(f"最低价: {min_price:.2f} (时间: {min_price_idx})")

        if '成交量' in self.dataframe.columns:
            max_volume_idx = self.dataframe['成交量'].idxmax()
            max_volume = self.dataframe['成交量'].max()
            print(f"最大成交量: {max_volume:,.0f} (时间: {max_volume_idx})")

    def calculate_technical_indicators(self):
        """计算技术指标"""

        if self.dataframe is None or self.dataframe.empty:
            return

        print("\n" + "=" * 80)
        print("技术指标计算")
        print("=" * 80)

        df = self.dataframe.copy()

        # 移动平均线
        if '收盘价' in df.columns:
            df['MA5'] = df['收盘价'].rolling(window=5).mean()
            df['MA10'] = df['收盘价'].rolling(window=10).mean()
            df['MA20'] = df['收盘价'].rolling(window=20).mean()

            print("移动平均线计算完成")
            print(f"最新MA5: {df['MA5'].iloc[-1]:.2f}")
            print(f"最新MA10: {df['MA10'].iloc[-1]:.2f}")
            print(f"最新MA20: {df['MA20'].iloc[-1]:.2f}")

        # 价格变化百分比
        if '收盘价' in df.columns:
            df['日涨跌幅'] = df['收盘价'].pct_change() * 100

            print(f"\n价格变化统计:")
            print(f"平均日涨跌幅: {df['日涨跌幅'].mean():.4f}%")
            print(f"最大日涨幅: {df['日涨跌幅'].max():.4f}%")
            print(f"最大日跌幅: {df['日涨跌幅'].min():.4f}%")

        # 成交量变化
        if '成交量' in df.columns:
            df['成交量变化率'] = df['成交量'].pct_change() * 100

            print(f"\n成交量变化统计:")
            print(f"平均成交量变化率: {df['成交量变化率'].mean():.4f}%")

        return df


def main():
    """主函数"""

    # 设置文件路径
    file_path = r"G:\D盘备份1\证券股票\分钟数据\wstock_SHSZ_201701_5Min.wdz"

    if not os.path.exists(file_path):
        print(f"文件不存在: {file_path}")

        # 查找当前目录的wdz文件
        wdz_files = list(Path('../pyfileOpen').glob('*.wdz'))
        if wdz_files:
            print("找到以下WDZ文件:")
            for i, f in enumerate(wdz_files, 1):
                print(f"{i}. {f.name}")

            choice = input("请选择文件编号: ").strip()
            if choice.isdigit() and 1 <= int(choice) <= len(wdz_files):
                file_path = str(wdz_files[int(choice) - 1])
            else:
                file_path = str(wdz_files[0])
        else:
            print("当前目录没有.wdz文件")
            return

    try:
        # 创建解析器
        extractor = WDZDataExtractor(file_path)

        # 解析文件
        print("开始解析文件...")
        df = extractor.parse_file()

        if df is not None and not df.empty:
            # 显示数据摘要
            extractor.show_data_summary(num_samples=20)

            # 分析极端值
            extractor.find_extreme_values()

            # 计算技术指标
            df_with_indicators = extractor.calculate_technical_indicators()

            # 询问是否导出
            export = input("\n是否导出数据为CSV文件? (y/N): ").strip().lower()
            if export == 'y':
                extractor.export_to_csv()

            # 询问是否可视化
            visualize = input("\n是否可视化数据? (y/N): ").strip().lower()
            if visualize == 'y':
                # 获取可视化参数
                column = input("要可视化的列 (默认: 收盘价): ").strip() or '收盘价'
                start_date = input("开始日期 (YYYY-MM-DD, 可选): ").strip() or None
                end_date = input("结束日期 (YYYY-MM-DD, 可选): ").strip() or None

                extractor.visualize_data(column=column,
                                         start_date=start_date,
                                         end_date=end_date)

            print("\n解析完成!")

        else:
            print("解析完成，但没有获取到有效数据")

    except Exception as e:
        print(f"解析过程中出错: {e}")
        import traceback
        traceback.print_exc()


def quick_test():
    """快速测试函数"""

    test_file = "wstock_SHSZ_2000_5Min.wdz"

    if not os.path.exists(test_file):
        print(f"测试文件不存在: {test_file}")
        return

    print("进行快速测试...")

    # 只解析前100条记录用于测试
    with open(test_file, 'rb') as f:
        # 读取文件头
        header_format = '<4sIIIII8sH10s'
        header_size = struct.calcsize(header_format)
        header_data = f.read(header_size)

        print(f"文件头大小: {header_size}")
        print(f"文件头原始字节 (前64字节): {header_data[:64].hex()}")

        # 解析文件头
        header_fields = struct.unpack(header_format, header_data)
        print("\n解析后的文件头:")
        field_names = ['magic', 'version', 'record_size', 'record_count',
                       'start_date', 'end_date', 'code', 'period', 'reserved']

        for name, value in zip(field_names, header_fields):
            if name in ['magic', 'code', 'reserved']:
                try:
                    value_str = value.decode('gbk', errors='ignore').strip('\x00')
                except:
                    value_str = str(value)
                print(f"  {name:15}: {value_str} (原始: {value})")
            else:
                print(f"  {name:15}: {value}")

        # 读取并解析前5条记录
        record_format = '<IIffffffIfI12s'
        record_size = struct.calcsize(record_format)

        print(f"\n记录大小: {record_size}")
        print(f"前5条记录:")

        for i in range(5):
            try:
                record_data = f.read(record_size)
                if not record_data:
                    break

                record_fields = struct.unpack(record_format, record_data)

                # 字段名称
                record_field_names = [
                    'date', 'time', 'open', 'high', 'low', 'close',
                    'volume', 'amount', 'trade_count', 'pre_close',
                    'open_interest', 'reserved'
                ]

                print(f"\n记录 {i + 1}:")
                for name, value in zip(record_field_names, record_fields):
                    if name == 'reserved':
                        continue  # 跳过保留字段
                    elif name in ['date', 'time']:
                        value_str = str(value)
                        if name == 'date' and len(value_str) == 8:
                            value_str = f"{value_str[:4]}-{value_str[4:6]}-{value_str[6:8]}"
                        elif name == 'time' and len(value_str) < 6:
                            value_str = value_str.zfill(6)
                        print(f"  {name:15}: {value_str}")
                    elif name in ['open', 'high', 'low', 'close', 'pre_close']:
                        print(f"  {name:15}: {value:.4f}")
                    elif name in ['volume', 'amount']:
                        print(f"  {name:15}: {value:,.2f}")
                    else:
                        print(f"  {name:15}: {value}")

            except Exception as e:
                print(f"解析记录 {i + 1} 时出错: {e}")
                break


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == 'test':
        quick_test()
    else:
        main()