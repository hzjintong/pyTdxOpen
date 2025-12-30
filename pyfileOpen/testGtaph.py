import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import matplotlib.dates as mdates
from datetime import datetime, timedelta
import os


class KLineChart:
    def __init__(self, data, title="K线图"):
        self.data = data
        self.title = title
        self.current_start = 0
        self.display_count = 50  # 默认显示50根K线
        self.cursor_pos = 0  # 光标位置
        self.zoom_factor = 1.2  # 缩放因子

        # 创建图形和轴
        self.fig, (self.ax_price, self.ax_volume) = plt.subplots(
            2, 1, figsize=(12, 8),
            gridspec_kw={'height_ratios': [3, 1]}
        )

        self.fig.canvas.mpl_connect('key_press_event', self.on_key_press)
        #self.fig.canvas.set_window_title('K线图分析工具')
        self.fig.canvas.manager.window.title('K线图分析工具')

    def calculate_technical_indicators(self, data):
        """计算技术指标"""
        # 计算MA
        data['MA5'] = data['close'].rolling(window=5).mean()
        data['MA10'] = data['close'].rolling(window=10).mean()
        data['MA20'] = data['close'].rolling(window=20).mean()
        return data

    def draw_k_line(self, data_slice):
        """绘制K线"""
        self.ax_price.clear()
        self.ax_volume.clear()

        # 设置颜色
        rise_color = 'red'  # 上涨颜色
        fall_color = 'green'  # 下跌颜色

        # 绘制K线
        for i, (idx, row) in enumerate(data_slice.iterrows()):
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

            # 绘制影线
            self.ax_price.plot([i, i], [low_price, high_price], color=color, linewidth=1)

            # 绘制实体
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

        # 绘制均线
        if 'MA5' in data_slice.columns:
            self.ax_price.plot(range(len(data_slice)), data_slice['MA5'],
                               label='MA5', color='blue', linewidth=1)
        if 'MA10' in data_slice.columns:
            self.ax_price.plot(range(len(data_slice)), data_slice['MA10'],
                               label='MA10', color='orange', linewidth=1)
        if 'MA20' in data_slice.columns:
            self.ax_price.plot(range(len(data_slice)), data_slice['MA20'],
                               label='MA20', color='purple', linewidth=1)

        # 绘制光标
        if 0 <= self.cursor_pos < len(data_slice):
            cursor_idx = self.cursor_pos
            self.ax_price.axvline(x=cursor_idx, color='yellow', linestyle='--', alpha=0.7)
            self.ax_volume.axvline(x=cursor_idx, color='yellow', linestyle='--', alpha=0.7)

            # 显示光标位置的信息
            cursor_data = data_slice.iloc[cursor_idx]
            info_text = (f"日期: {cursor_data.name.strftime('%Y-%m-%d %H:%M')}\n"
                         f"开: {cursor_data['open']:.2f} 高: {cursor_data['high']:.2f}\n"
                         f"低: {cursor_data['low']:.2f} 收: {cursor_data['close']:.2f}\n"
                         f"成交量: {cursor_data['volume']:.0f}")

            self.ax_price.text(0.02, 0.98, info_text, transform=self.ax_price.transAxes,
                               verticalalignment='top', bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8),
                               fontsize=8)

        # 设置价格图
        self.ax_price.set_title(f'{self.title} - 显示 {len(data_slice)} 根K线')
        self.ax_price.set_ylabel('价格')
        self.ax_price.legend()
        self.ax_price.grid(True, alpha=0.3)

        # 设置成交量图
        self.ax_volume.set_ylabel('成交量')
        self.ax_volume.set_xlabel('时间')
        self.ax_volume.grid(True, alpha=0.3)

        # 设置X轴刻度
        if len(data_slice) > 0:
            step = max(1, len(data_slice) // 10)  # 显示约10个标签
            indices = range(0, len(data_slice), step)
            labels = [data_slice.index[i].strftime('%m-%d %H:%M') for i in indices]

            self.ax_price.set_xticks(indices)
            self.ax_price.set_xticklabels(labels, rotation=45)
            self.ax_volume.set_xticks(indices)
            self.ax_volume.set_xticklabels(labels, rotation=45)

        plt.tight_layout()

    def on_key_press(self, event):
        """键盘事件处理"""
        if event.key in ['left', 'right', 'up', 'down']:
            self.handle_navigation(event.key)
            self.update_chart()

    def handle_navigation(self, key):
        """处理导航键"""
        total_bars = len(self.data)

        if key == 'left':  # 左移光标
            self.cursor_pos = max(0, self.cursor_pos - 1)
            # 如果光标移到显示范围外，向左移动显示范围
            if self.cursor_pos < self.current_start:
                self.current_start = max(0, self.current_start - 1)

        elif key == 'right':  # 右移光标
            self.cursor_pos = min(total_bars - 1, self.cursor_pos + 1)
            # 如果光标移到显示范围外，向右移动显示范围
            if self.cursor_pos >= self.current_start + self.display_count:
                self.current_start = min(total_bars - self.display_count,
                                         self.current_start + 1)

        elif key == 'up':  # 放大（显示更少K线）
            self.display_count = max(10, int(self.display_count / self.zoom_factor))
            # 保持光标在可见范围内
            self.cursor_pos = min(self.cursor_pos, self.current_start + self.display_count - 1)

        elif key == 'down':  # 缩小（显示更多K线）
            self.display_count = min(total_bars, int(self.display_count * self.zoom_factor))
            # 调整起始位置确保显示完整范围
            if self.current_start + self.display_count > total_bars:
                self.current_start = max(0, total_bars - self.display_count)

    def update_chart(self):
        """更新图表显示"""
        end_idx = min(self.current_start + self.display_count, len(self.data))
        data_slice = self.data.iloc[self.current_start:end_idx]

        self.draw_k_line(data_slice)
        self.fig.canvas.draw()

    def show(self):
        """显示图表"""
        # 计算技术指标
        self.data = self.calculate_technical_indicators(self.data)

        # 初始显示
        self.update_chart()
        plt.show()


def load_tdx_data(file_path, freq='1min'):
    """
    加载通达信数据
    假设数据格式为CSV，包含以下列：
    datetime, open, high, low, close, volume
    """
    try:
        # 读取数据
        df = pd.read_csv(file_path)

        # 确保日期时间格式
        df['datetime'] = pd.to_datetime(df['datetime'])
        df.set_index('datetime', inplace=True)

        # 确保数值列是浮点数
        numeric_cols = ['open', 'high', 'low', 'close', 'volume']
        for col in numeric_cols:
            df[col] = pd.to_numeric(df[col], errors='coerce')

        # 按时间排序
        df.sort_index(inplace=True)

        print(f"成功加载 {len(df)} 条{freq}数据")
        return df

    except Exception as e:
        print(f"加载数据失败: {e}")
        # 生成示例数据
        return generate_sample_data()


def generate_sample_data(days=30, freq='1min'):
    """生成示例数据用于测试"""
    dates = pd.date_range(start='2024-01-01', periods=days * 24 * 60, freq='1min')  # 分钟数据

    # 生成随机价格数据
    np.random.seed(42)
    price = 100 + np.cumsum(np.random.randn(len(dates)) * 0.1)

    # 生成OHLC数据
    data = []
    for i, date in enumerate(dates):
        base_price = price[i]
        open_price = base_price
        close_price = base_price + np.random.randn() * 0.5
        high_price = max(open_price, close_price) + abs(np.random.randn() * 0.3)
        low_price = min(open_price, close_price) - abs(np.random.randn() * 0.3)
        volume = np.random.randint(1000, 100000)

        data.append({
            'datetime': date,
            'open': open_price,
            'high': high_price,
            'low': low_price,
            'close': close_price,
            'volume': volume
        })

    df = pd.DataFrame(data)
    df.set_index('datetime', inplace=True)
    print(f"生成 {len(df)} 条示例{freq}数据")
    return df


# 使用示例
if __name__ == "__main__":
    # 方法1: 加载真实数据（请修改文件路径）
    # data = load_tdx_data('your_tdx_data.csv', freq='1min')

    # 方法2: 使用示例数据
    data = generate_sample_data(days=10, freq='1min')

    # 创建并显示K线图
    chart = KLineChart(data, title="股票K线图 - 1分钟数据")
    chart.show()