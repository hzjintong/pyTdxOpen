import talib
import numpy as np


class TechnicalAnalyzer:
    """技术面模式识别引擎"""

    def __init__(self, df_day):
        """
        Args:
            df_day: 包含 'open', 'high', 'low', 'close', 'volume' 的 DataFrame
        """
        self.df = df_day
        # 预转换数据格式以适配 TA-Lib
        self.close = df_day['close'].values.astype(float)
        self.open = df_day['open'].values.astype(float)
        self.high = df_day['high'].values.astype(float)
        self.low = df_day['low'].values.astype(float)
        self.volume = df_day['volume'].values.astype(float)

    def scan_signals(self):
        """扫描多种技术面模式"""
        signals = {}

        # 1. 趋势过滤：均线多头排列 (MA5 > MA10 > MA20)
        ma5 = talib.SMA(self.close, timeperiod=5)
        ma10 = talib.SMA(self.close, timeperiod=10)
        ma20 = talib.SMA(self.close, timeperiod=20)
        signals['bull_alignment'] = (ma5[-1] > ma10[-1] > ma20[-1])

        # 2. 动量识别：RSI超买超卖 (判断强度)
        rsi = talib.RSI(self.close, timeperiod=14)
        signals['rsi_value'] = rsi[-1]

        # 3. 模式识别：放量突破 (当日成交量 > 5日均量 1.5倍)
        vma5 = talib.SMA(self.volume, timeperiod=5)
        signals['volume_breakout'] = self.volume[-1] > (vma5[-1] * 1.5)

        # 4. K线形态：TA-Lib 自动识别“锤头线”或“吞没形态”
        # CDLENGULFING: 吞没形态 (返回 100 表示看涨吞没, -100 看跌)
        engulfing = talib.CDLENGULFING(self.open, self.high, self.low, self.close)
        signals['bullish_engulfing'] = engulfing[-1] == 100

        return signals

    def get_technical_score(self):
        """计算技术面综合评分 (0-100)"""
        sig = self.scan_signals()
        score = 0
        if sig['bull_alignment']: score += 40  # 趋势得分
        if sig['volume_breakout']: score += 30  # 成长得分
        if sig['bullish_engulfing']: score += 30  # 形态确认得分
        return score