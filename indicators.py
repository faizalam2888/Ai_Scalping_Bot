import math
from config import UTBOT_ATR_PERIOD, UTBOT_SENS, LRC_LENGTH, VOLUME_LOOKBACK, BB_PERIOD, BB_STD, ST_PERIOD, ST_MULTIPLIER, EMA_FAST, EMA_SLOW, RSI_PERIOD
def atr(khist, period=10):
    try:
        trs=[]
        for i in range(1, min(len(khist), period+1)):
            high = float(khist[-i][2]); low = float(khist[-i][3])
            prev_close = float(khist[-i-1][4] if len(khist) > i else khist[-i][4])
            trs.append(max(high-low, abs(high-prev_close), abs(low-prev_close)))
        return sum(trs)/max(1,len(trs))
    except:
        return 0.0

def utbot_flags(khist):
    try:
        if len(khist) < UTBOT_ATR_PERIOD+2: return None, 0.0
        xatr = atr(khist, UTBOT_ATR_PERIOD)
        a = UTBOT_SENS
        src = float(khist[-1][4]); prev = float(khist[-2][4])
        stop = src - a * xatr if src>=prev else src + a * xatr
        if src > stop and src > prev:
            return 'BUY', 0.6 + min(0.39, (src-prev)/max(1e-8, xatr)*0.1)
        if src < stop and src < prev:
            return 'SELL', 0.6 + min(0.39, (prev-src)/max(1e-8, xatr)*0.1)
        return 'NEUTRAL', 0.1
    except:
        return None, 0.0

def linreg_flags(khist):
    try:
        n = LRC_LENGTH
        if len(khist) < n: return None, 0.0
        closes = [float(k[4]) for k in khist[-n:]]
        slope = closes[-1] - closes[0]
        return ('BUY', abs(slope)) if slope>0 else ('SELL', abs(slope))
    except:
        return None, 0.0

def volume_level(khist):
    try:
        vols = [float(k[5]) for k in khist[-(VOLUME_LOOKBACK+1):]]
        if len(vols) < 2: return 'Unknown'
        last = vols[-1]; avg = sum(vols[:-1])/max(1,len(vols[:-1]))
        return 'High' if last >= 1.2*avg else 'Low'
    except:
        return 'Unknown'

def ema_from_list(values, period):
    if not values or period <= 0:
        return []
    emas = []
    k = 2 / (period + 1)
    ema_prev = sum(values[:period]) / period if len(values) >= period else values[0]
    for i, v in enumerate(values):
        if i == 0:
            ema_prev = v if len(values) < period else ema_prev
            emas.append(ema_prev)
        else:
            ema_prev = (v - ema_prev) * k + ema_prev
            emas.append(ema_prev)
    return emas

def ema_crossover(khist, fast=EMA_FAST, slow=EMA_SLOW):
    try:
        closes = [float(k[4]) for k in khist]
        if len(closes) < max(fast, slow) + 1:
            return None, 0.0
        emas_fast = ema_from_list(closes, fast)
        emas_slow = ema_from_list(closes, slow)
        if emas_fast[-2] <= emas_slow[-2] and emas_fast[-1] > emas_slow[-1]:
            return 'BUY', abs(emas_fast[-1]-emas_slow[-1])
        if emas_fast[-2] >= emas_slow[-2] and emas_fast[-1] < emas_slow[-1]:
            return 'SELL', abs(emas_fast[-1]-emas_slow[-1])
        return None, 0.0
    except:
        return None, 0.0

def get_rsi(khist, period=RSI_PERIOD):
    try:
        closes = [float(k[4]) for k in khist]
        if len(closes) < period + 1:
            return None
        gains = []
        losses = []
        for i in range(1, len(closes)):
            diff = closes[i] - closes[i-1]
            gains.append(max(diff, 0))
            losses.append(max(-diff, 0))
        gains_avg = sum(gains[-period:]) / period
        losses_avg = sum(losses[-period:]) / period
        if losses_avg == 0:
            return 100.0
        rs = gains_avg / losses_avg
        rsi = 100 - (100 / (1 + rs))
        return rsi
    except:
        return None

def supertrend(khist, period=ST_PERIOD, multiplier=ST_MULTIPLIER):
    try:
        if len(khist) < period + 2:
            return None
        highs = [float(k[2]) for k in khist]
        lows = [float(k[3]) for k in khist]
        closes = [float(k[4]) for k in khist]
        tr_list = []
        for i in range(1, len(khist)):
            tr = max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1]))
            tr_list.append(tr)
        atr_val = sum(tr_list[-period:]) / period if len(tr_list) >= period else (sum(tr_list)/len(tr_list) if tr_list else 0.0)
        if atr_val == 0:
            return None
        hl2 = [(h + l) / 2 for h, l in zip(highs, lows)]
        upperband = [hl2[i] + multiplier * atr_val for i in range(len(hl2))]
        lowerband = [hl2[i] - multiplier * atr_val for i in range(len(hl2))]
        final_upper = [0]*len(hl2)
        final_lower = [0]*len(hl2)
        trend = [True]*len(hl2)
        for i in range(len(hl2)):
            if i == 0:
                final_upper[i] = upperband[i]
                final_lower[i] = lowerband[i]
                trend[i] = True if closes[i] > final_upper[i] else False
            else:
                final_upper[i] = min(upperband[i], final_upper[i-1]) if closes[i-1] <= final_upper[i-1] else upperband[i]
                final_lower[i] = max(lowerband[i], final_lower[i-1]) if closes[i-1] >= final_lower[i-1] else lowerband[i]
                if closes[i] > final_upper[i]:
                    trend[i] = True
                elif closes[i] < final_lower[i]:
                    trend[i] = False
                else:
                    trend[i] = trend[i-1]
        return 'UP' if trend[-1] else 'DOWN'
    except:
        return None

def bollinger_bands(khist, period=BB_PERIOD, std_mult=BB_STD):
    try:
        closes = [float(k[4]) for k in khist]
        if len(closes) < period:
            return {'upper':None,'mid':None,'lower':None,'width':None,'position':None}
        window = closes[-period:]
        mid = sum(window)/period
        variance = sum((c-mid)**2 for c in window)/period
        sd = math.sqrt(variance)
        upper = mid + std_mult * sd
        lower = mid - std_mult * sd
        width = (upper - lower) / mid if mid != 0 else None
        last = closes[-1]
        if last > upper: pos = 'above_upper'
        elif last < lower: pos = 'below_lower'
        else: pos = 'inside'
        return {'upper':upper,'mid':mid,'lower':lower,'width':width,'position':pos}
    except:
        return {'upper':None,'mid':None,'lower':None,'width':None,'position':None}
