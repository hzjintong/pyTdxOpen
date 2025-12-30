import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle


class SimpleKLineChart:
    def __init__(self, data, title="简单K线图"):
        self.data = data
        self.title = title

        # 创建图形和轴
        self.fig, (self.ax_price, self.ax_volume) = plt.subplots(
            2, 1, figsize=(12, 8),
            gridspec_kw={'height_ratios': [3, 1]}
        )

        # 设置窗口标题
        self.fig.canvas.manager.set_window_title('简单K线图')

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
        self.ax_price.set_title(self.title)
        self.ax_price.set_ylabel('价格')
        self.ax_price.grid(True, alpha=0.3)

        # 设置成交量图
        self.ax_volume.set_ylabel('成交量')
        self.ax_volume.set_xlabel('K线序号')
        self.ax_volume.grid(True, alpha=0.3)

        # 调整布局
        plt.tight_layout()

    def show(self):
        """显示图表"""
        print("开始绘制K线图...")
        self.draw_chart()
        print("图表绘制完成，显示窗口...")
        plt.show()


def create_sample_data():
    """创建示例数据"""
    print("创建示例数据...")

    # 生成100个数据点
    n = 100
    dates = pd.date_range(start='2024-01-01', periods=n, freq='D')

    np.random.seed(42)

    # 生成价格数据
    prices = [100.0]
    for i in range(1, n):
        change = np.random.normal(0, 2)
        new_price = prices[-1] + change
        prices.append(new_price)

    # 生成OHLC数据
    data = []
    for i in range(n):
        base_price = prices[i]
        open_price = base_price
        close_price = base_price + np.random.normal(0, 1)
        high_price = max(open_price, close_price) + abs(np.random.normal(0, 0.5))
        low_price = min(open_price, close_price) - abs(np.random.normal(0, 0.5))
        volume = np.random.randint(1000, 100000)

        data.append({
            'datetime': dates[i],
            'open': round(open_price, 2),
            'high': round(high_price, 2),
            'low': round(low_price, 2),
            'close': round(close_price, 2),
            'volume': volume
        })

    df = pd.DataFrame(data)
    df.set_index('datetime', inplace=True)
    print(f"示例数据创建完成，共 {len(df)} 行")
    return df


# 主程序
if __name__ == "__main__":
    print("简单K线图程序启动")

    try:
        # 创建示例数据
        data = create_sample_data()

        # 创建K线图
        chart = SimpleKLineChart(data, title="简单K线图示例")

        # 显示图表
        chart.show()

    except Exception as e:
        print(f"程序运行出错: {e}")
        import traceback

        traceback.print_exc()

    print("程序结束")