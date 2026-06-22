import os
import struct
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from tqdm import tqdm
import talib
import warnings
import talib

# 屏蔽警告
warnings.filterwarnings('ignore')

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

        # ========== 1. 趋势过滤 ==========
        ma5 = talib.SMA(self.close, timeperiod=5)
        ma10 = talib.SMA(self.close, timeperiod=10)
        ma20 = talib.SMA(self.close, timeperiod=20)
        ma60 = talib.SMA(self.close, timeperiod=60)
        signals['bull_alignment'] = (ma5[-1] > ma10[-1] > ma20[-1])
        signals['bull_alignment_long'] = (ma20[-1] > ma60[-1])  # 中长期趋势

        # ========== 2. 动量指标 ==========
        rsi = talib.RSI(self.close, timeperiod=14)
        signals['rsi_value'] = rsi[-1]
        signals['rsi_oversold'] = rsi[-1] < 30   # 超卖（潜在买入机会）
        signals['rsi_overbought'] = rsi[-1] > 70  # 超买（潜在卖出风险）

        # MACD
        macd, macd_signal, macd_hist = talib.MACD(self.close, fastperiod=12, slowperiod=26, signalperiod=9)
        signals['macd_bullish'] = macd[-1] > macd_signal[-1]  # MACD金叉
        signals['macd_hist_positive'] = macd_hist[-1] > 0     # 红柱

        # ========== 3. 成交量分析 ==========
        vma5 = talib.SMA(self.volume, timeperiod=5)
        vma20 = talib.SMA(self.volume, timeperiod=20)
        signals['volume_breakout'] = self.volume[-1] > (vma5[-1] * 1.5)
        signals['volume_ma5_above_ma20'] = vma5[-1] > vma20[-1]  # 量能趋势向好

        # ========== 4. K线形态（多维度） ==========

        # --- 4a. 单根反转形态 ---
        # 锤头线（底部反转）
        hammer = talib.CDLHAMMER(self.open, self.high, self.low, self.close)
        signals['hammer'] = hammer[-1] == 100

        # 倒锤头（底部反转）
        inv_hammer = talib.CDLINVERTEDHAMMER(self.open, self.high, self.low, self.close)
        signals['inverted_hammer'] = inv_hammer[-1] == 100

        # 射击之星（顶部反转）
        shooting_star = talib.CDLSHOOTINGSTAR(self.open, self.high, self.low, self.close)
        signals['shooting_star'] = shooting_star[-1] == -100

        # 吊颈线（顶部反转）
        hanging_man = talib.CDLHANGINGMAN(self.open, self.high, self.low, self.close)
        signals['hanging_man'] = hanging_man[-1] == -100

        # 光头光脚大阳线（趋势强劲）
        marubozu = talib.CDLMARUBOZU(self.open, self.high, self.low, self.close)
        signals['bullish_marubozu'] = marubozu[-1] == 100

        # 十字星（趋势犹豫/变盘）
        doji = talib.CDLDOJI(self.open, self.high, self.low, self.close)
        signals['doji'] = doji[-1] != 0  # 出现十字星

        # 蜻蜓十字星（底部反转）
        dragonfly = talib.CDLDRAGONFLYDOJI(self.open, self.high, self.low, self.close)
        signals['dragonfly_doji'] = dragonfly[-1] == 100

        # 墓碑十字星（顶部反转）
        gravestone = talib.CDLGRAVESTONEDOJI(self.open, self.high, self.low, self.close)
        signals['gravestone_doji'] = gravestone[-1] == -100

        # --- 4b. 双K线组合 ---
        # 吞没形态
        engulfing = talib.CDLENGULFING(self.open, self.high, self.low, self.close)
        signals['bullish_engulfing'] = engulfing[-1] == 100
        signals['bearish_engulfing'] = engulfing[-1] == -100

        # 刺透形态（看涨反转）
        piercing = talib.CDLPIERCING(self.open, self.high, self.low, self.close)
        signals['piercing'] = piercing[-1] == 100

        # 乌云盖顶（看跌反转）
        dark_cloud = talib.CDLDARKCLOUDCOVER(self.open, self.high, self.low, self.close)
        signals['dark_cloud_cover'] = dark_cloud[-1] == -100

        # 捉腰带线（趋势启动）
        belt_hold = talib.CDLBELTHOLD(self.open, self.high, self.low, self.close)
        signals['bullish_belt_hold'] = belt_hold[-1] == 100

        # --- 4c. 三K线组合（高可靠性） ---
        # 晨星（底部反转）
        morning_star = talib.CDLMORNINGSTAR(self.open, self.high, self.low, self.close, penetration=0.3)
        signals['morning_star'] = morning_star[-1] == 100

        # 暮星（顶部反转）
        evening_star = talib.CDLEVENINGSTAR(self.open, self.high, self.low, self.close, penetration=0.3)
        signals['evening_star'] = evening_star[-1] == -100

        # 三白兵（强势上涨）
        three_soldiers = talib.CDL3WHITESOLDIERS(self.open, self.high, self.low, self.close)
        signals['three_white_soldiers'] = three_soldiers[-1] == 100

        # 三黑鸦（强势下跌）
        three_crows = talib.CDL3BLACKCROWS(self.open, self.high, self.low, self.close)
        signals['three_black_crows'] = three_crows[-1] == -100

        # 上升三法（上涨中继）
        rise_methods = talib.CDLRISEFALL3METHODS(self.open, self.high, self.low, self.close)
        signals['rising_three_methods'] = rise_methods[-1] == 100

        # 下降三法（下跌中继）
        fall_methods = talib.CDLRISEFALL3METHODS(self.open, self.high, self.low, self.close)
        signals['falling_three_methods'] = fall_methods[-1] == -100

        # --- 4d. 缺口形态 ---
        upside_gap = talib.CDLUPSIDEGAP2CROWS(self.open, self.high, self.low, self.close)
        signals['upside_gap_2crows'] = upside_gap[-1] == -100

        return signals

    def get_technical_score(self):
        """计算技术面综合评分 (0-100)"""
        sig = self.scan_signals()
        score = 0

        # ===== 趋势得分 (最高30分) =====
        if sig['bull_alignment']:
            score += 20  # 短期多头排列
        if sig['bull_alignment_long']:
            score += 10  # 中长期趋势向上

        # ===== 动量得分 (最高20分) =====
        if sig['macd_bullish']:
            score += 10  # MACD金叉
        if sig['macd_hist_positive']:
            score += 5   # MACD红柱
        if 30 <= sig['rsi_value'] <= 70:
            score += 5   # RSI在合理区间（非超买超卖）

        # ===== 成交量得分 (最高15分) =====
        if sig['volume_breakout']:
            score += 10  # 放量突破
        if sig['volume_ma5_above_ma20']:
            score += 5   # 量能趋势向好

        # ===== K线形态得分 (最高35分) =====
        # 高可靠性三K线组合 (每个10分)
        if sig['morning_star']:
            score += 10
        if sig['three_white_soldiers']:
            score += 10
        if sig['rising_three_methods']:
            score += 8

        # 双K线反转组合 (每个8分)
        if sig['bullish_engulfing']:
            score += 8
        if sig['piercing']:
            score += 6
        if sig['bullish_belt_hold']:
            score += 6

        # 单根K线反转 (每个5分)
        if sig['hammer']:
            score += 5
        if sig['inverted_hammer']:
            score += 5
        if sig['bullish_marubozu']:
            score += 5
        if sig['dragonfly_doji']:
            score += 4

        # ===== 风险信号扣分 =====
        if sig['shooting_star']:
            score -= 10
        if sig['hanging_man']:
            score -= 8
        if sig['evening_star']:
            score -= 10
        if sig['three_black_crows']:
            score -= 10
        if sig['bearish_engulfing']:
            score -= 8
        if sig['dark_cloud_cover']:
            score -= 6
        if sig['gravestone_doji']:
            score -= 5
        if sig['rsi_overbought']:
            score -= 5  # RSI超买，回调风险

        # 限制得分范围 0-100
        return max(0, min(100, score))

    def get_signal_summary(self):
        """返回信号摘要，便于调试和展示"""
        sig = self.scan_signals()
        bullish_signals = []
        bearish_signals = []

        # 收集看涨信号
        if sig['bull_alignment']: bullish_signals.append('均线多头排列')
        if sig['macd_bullish']: bullish_signals.append('MACD金叉')
        if sig['volume_breakout']: bullish_signals.append('放量突破')
        if sig['morning_star']: bullish_signals.append('晨星形态')
        if sig['three_white_soldiers']: bullish_signals.append('三白兵')
        if sig['bullish_engulfing']: bullish_signals.append('看涨吞没')
        if sig['hammer']: bullish_signals.append('锤头线')
        if sig['piercing']: bullish_signals.append('刺透形态')
        if sig['bullish_marubozu']: bullish_signals.append('光头光脚阳线')
        if sig['dragonfly_doji']: bullish_signals.append('蜻蜓十字星')
        if sig['rising_three_methods']: bullish_signals.append('上升三法')
        if sig['bullish_belt_hold']: bullish_signals.append('看涨捉腰带线')
        if sig['inverted_hammer']: bullish_signals.append('倒锤头')

        # 收集看跌信号
        if sig['shooting_star']: bearish_signals.append('射击之星')
        if sig['hanging_man']: bearish_signals.append('吊颈线')
        if sig['evening_star']: bearish_signals.append('暮星形态')
        if sig['three_black_crows']: bearish_signals.append('三黑鸦')
        if sig['bearish_engulfing']: bearish_signals.append('看跌吞没')
        if sig['dark_cloud_cover']: bearish_signals.append('乌云盖顶')
        if sig['gravestone_doji']: bearish_signals.append('墓碑十字星')
        if sig['falling_three_methods']: bearish_signals.append('下降三法')
        if sig['upside_gap_2crows']: bearish_signals.append('向上跳空两只乌鸦')
        if sig['rsi_overbought']: bearish_signals.append('RSI超买')

        return {
            'score': self.get_technical_score(),
            'rsi': sig['rsi_value'],
            'bullish_signals': bullish_signals,
            'bearish_signals': bearish_signals,
            'signal_count': len(bullish_signals) - len(bearish_signals)
        }
