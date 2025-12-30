import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import matplotlib.font_manager as fm
import struct
from datetime import datetime, timedelta
import platform


# 设置中文字体
def set_chinese_font():
    system = platform.system()

    if system == 'Windows':
        font_names = ['Microsoft YaHei', 'KaiTi', 'SimSun']
    elif system == 'Darwin':  # macOS
        font_names = ['Heiti TC', 'STHeiti', 'Heiti SC', 'PingFang SC', 'Hiragino Sans GB']
    else:  # Linux
        font_names = ['WenQuanYi Micro Hei', 'WenQuanYi Zen Hei', 'Noto Sans CJK SC']

    available_fonts = []
    for font_name in font_names:
        try:
            font_path = fm.findfont(fm.FontProperties(family=font_name))
            available_fonts.append(font_name)
            print(f"找到字体: {font_name}")
        except Exception as e:
            print(f"查找字体文件时发生错误: {e}")
            pass

    if available_fonts:
        plt.rcParams['font.sans-serif'] = available_fonts + ['DejaVu Sans']
        plt.rcParams['axes.unicode_minus'] = False
        print(f"已设置中文字体: {available_fonts[0]}")
        return available_fonts[0]
    else:
        print("警告: 未找到中文字体，中文可能显示为方框")
        return None


# 设置中文字体
chinese_font = set_chinese_font()


# 通达信日线数据读取函数
def format_day_date_obj(date_int):
    """将整数日期转换为datetime对象"""
    date_str = str(date_int)
    return datetime.strptime(date_str, "%Y%m%d")


def parse_tdx_day_record(record_buffer):
    """
    解析解包通达信日线数据记录
    格式为: <I4IfII (小端字节序)
    """
    try:
        # 解析二进制数据 - 日期(4), 开盘(4), 最高(4), 最低(4), 收盘(4), 成交额(4), 成交量(4), 保留(4)
        day_line_data = struct.unpack('<I4IfII', record_buffer)

        # 返回解析后的数据
        return {
            'datetime': day_line_data[0],
            'open': day_line_data[1],
            'high': day_line_data[2],
            'low': day_line_data[3],
            'close': day_line_data[4],
            'amount': day_line_data[5],
            'volume': day_line_data[6],
            # 'spare': day_line_data[7]  # 备用字段，暂时不用
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

    try:
        with open(file_path, 'rb') as f:
            buffer = f.read()
            size = len(buffer)
            record_size = 32  # 每条记录32字节

            record_number = size // record_size

            if record_number != 0:
                print(f"文件中共有 {record_number} 条记录")

            if size % record_size != 0:
                print(f"警告: 文件大小({size}字节)不是{record_size}字节的整数倍，可能存在数据不完整")

            for record_location in range(0, size, record_size):
                if record_location + record_size > size:
                    break

                # 解析二进制数据
                day_line_data = parse_tdx_day_record(buffer[record_location: record_location + record_size])

                if day_line_data is None:
                    continue

                # 转换为日期对象
                day_record_date = format_day_date_obj(day_line_data['datetime'])

                # 过滤指定时间段
                if start_date is not None:
                    start_date_date = datetime.strptime(start_date, "%Y-%m-%d")

                if end_date is not None:
                    end_date_date = datetime.strptime(end_date, "%Y-%m-%d")

                # 过滤指定时间段
                if (start_date is None or day_record_date >= start_date_date) and \
                        (end_date is None or day_record_date <= end_date_date):
                    # 价格单位转换：从分转换为元
                    data_list.append({
                        'datetime': day_record_date,  # 使用datetime对象
                        'open': day_line_data['open'] / 100.0,  # 转换为元
                        'high': day_line_data['high'] / 100.0,
                        'low': day_line_data['low'] / 100.0,
                        'close': day_line_data['close'] / 100.0,
                        'amount': day_line_data['amount'],  # 成交额(元)
                        'volume': day_line_data['volume'],  # 成交量(手)
                    })

        print(f"从 {file_path} 读取了 {len(data_list)} 条记录")
        return data_list

    except Exception as e:
        print(f"读取文件 {file_path} 时出错: {e}")
        return []


# K线图显示类
class SimpleKLineChart:
    def __init__(self, data, title="K线图"):
        self.data = data
        self.title = title

        # 创建图形和轴
        self.fig, (self.ax_price, self.ax_volume) = plt.subplots(
            2, 1, figsize=(12, 8),
            gridspec_kw={'height_ratios': [3, 1]}
        )

        # 设置窗口标题
        if chinese_font:
            self.fig.canvas.manager.set_window_title('通达信K线图')
        else:
            self.fig.canvas.manager.set_window_title('TDX K Line Chart')

    def draw_chart(self):
        """绘制K线图和成交量图"""
        # 清空轴
        self.ax_price.clear()
        self.ax_volume.clear()

        # 设置颜色
        rise_color = 'red'  # 上涨为红色
        fall_color = 'green'  # 下跌为绿色

        # 显示所有数据
        data = self.data

        # 绘制K线
        for i, (idx, row) in enumerate(data.iterrows()):
            open_price = row['open']
            close_price = row['close']
            high_price = row['high']
            low_price = row['low']
            volume = row['volume']

            # 判断涨跌
            if close_price >= open_price:
                color = rise_color
                body_color = rise_color
            else:
                color = fall_color
                body_color = 'white'

            # 绘制影线（最高到最低的线）
            self.ax_price.plot([i, i], [low_price, high_price], color=color, linewidth=1)

            # 绘制实体（开盘到收盘的矩形）
            body_height = abs(close_price - open_price)
            if body_height > 0:
                rect = Rectangle(
                    (i - 0.3, min(open_price, close_price)),
                    0.6, body_height,
                    facecolor=body_color, edgecolor=color, linewidth=1
                )
                self.ax_price.add_patch(rect)

            # 绘制成交量
            volume_color = rise_color if close_price >= open_price else fall_color
            self.ax_volume.bar(i, volume, color=volume_color, alpha=0.7, width=0.6)

        # 设置价格图
        if chinese_font:
            self.ax_price.set_title(self.title)
            self.ax_price.set_ylabel('价格')
            self.ax_volume.set_ylabel('成交量')
            self.ax_volume.set_xlabel('日期')
        else:
            self.ax_price.set_title("K Line Chart")
            self.ax_price.set_ylabel('Price')
            self.ax_volume.set_ylabel('Volume')
            self.ax_volume.set_xlabel('Date')

        self.ax_price.grid(True, alpha=0.3)
        self.ax_volume.grid(True, alpha=0.3)

        # 设置X轴刻度 - 显示日期
        if len(data) > 0:
            step = max(1, len(data) // 10)  # 显示约10个标签
            indices = range(0, len(data), step)

            # 获取对应的日期
            dates = data.index[indices]
            labels = [date.strftime('%Y-%m-%d') for date in dates]

            self.ax_price.set_xticks(indices)
            self.ax_price.set_xticklabels(labels, rotation=45)
            self.ax_volume.set_xticks(indices)
            self.ax_volume.set_xticklabels(labels, rotation=45)

        # 调整布局
        plt.tight_layout()

    def show(self):
        """显示图表"""
        print("开始绘制K线图...")
        self.draw_chart()
        print("图表绘制完成，显示窗口...")
        plt.show()


# 主程序
def main():
    print("通达信K线图程序启动")

    try:
        # 读取通达信日线数据
        filepath = "D:/new_hxzq_hc/vipdoc/sh/lday/sh999999.day"  # 修改为你的实际文件路径
        start_date = "2024-05-01"  # 开始日期
        end_date = "2025-10-16"  # 结束日期

        print(f"正在读取文件: {filepath}")
        day_data = read_tdx_day_file(filepath, start_date, end_date)

        if len(day_data) == 0:
            print("没有读取到数据，程序结束")
            return

        # 转换为DataFrame
        df = pd.DataFrame(day_data)
        df.set_index('datetime', inplace=True)

        # 按日期排序
        df.sort_index(inplace=True)

        print(f"成功加载 {len(df)} 条日线数据")
        print(f"数据时间范围: {df.index[0]} 到 {df.index[-1]}")
        print(f"数据列: {df.columns.tolist()}")
        print(f"前5条数据:\n{df.head()}")

        # 创建K线图
        if chinese_font:
            title = f"通达信日线数据 - 共{len(df)}个交易日"
        else:
            title = f"TDX Daily Data - {len(df)} trading days"

        chart = SimpleKLineChart(df, title=title)

        # 显示图表
        chart.show()

    except Exception as e:
        print(f"程序运行出错: {e}")
        import traceback
        traceback.print_exc()

    print("程序结束")


if __name__ == "__main__":
    main()