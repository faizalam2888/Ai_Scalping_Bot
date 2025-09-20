from indicators import utbot_flags, linreg_flags, supertrend, get_rsi, ema_crossover, bollinger_bands, volume_level, atr
from config import MIN_CONF_POST, W_UT, W_LRC, UTBOT_ATR_PERIOD
from exchange_utils import fetch_orderbook, fetch_ticker
import math

def combined_strength(ut_conf, lrc_conf):
    try:
        return W_UT * (ut_conf or 0) + W_LRC * (lrc_conf or 0)
    except:
        return 0.0

def ai_heuristics(khist, ob, st_val, rsi_val, ema_side, indicators_enabled):
    try:
        closes = [float(k[4]) for k in khist[-60:]] if len(khist)>=10 else [float(k[4]) for k in khist]
        highs = [float(k[2]) for k in khist[-60:]] if len(khist)>=10 else [float(k[2]) for k in khist]
        lows  = [float(k[3]) for k in khist[-60:]] if len(khist)>=10 else [float(k[3]) for k in khist]
        last = closes[-1] if closes else None
        if last is None:
            return None, 0.0
        recent_high = max(highs[-20:]) if highs else last
        recent_low = min(lows[-20:]) if lows else last
        bids = sum([float(x[1]) for x in ob.get('bids',[])[:15]]) if ob.get('bids') else 0
        asks = sum([float(x[1]) for x in ob.get('asks',[])[:15]]) if ob.get('asks') else 0
        total = bids+asks if (bids+asks)!=0 else 1.0
        imbalance = (bids-asks)/total
        conf_base = 0.0
        side = None
        if last > recent_high * 0.995:
            side, conf_base = 'BUY', 0.6
        elif last < recent_low * 1.005:
            side, conf_base = 'SELL', 0.6
        else:
            if imbalance > 0.1: side, conf_base = 'BUY', 0.52
            elif imbalance < -0.1: side, conf_base = 'SELL', 0.52
        if not side: return None, 0.0
        indicator_conf_boost = 0.0
        if indicators_enabled:
            if side == 'BUY':
                if st_val == 'UP': indicator_conf_boost += 0.1
                if rsi_val and rsi_val < 50: indicator_conf_boost += 0.05
                if ema_side == 'BUY': indicator_conf_boost += 0.1
            elif side == 'SELL':
                if st_val == 'DOWN': indicator_conf_boost += 0.1
                if rsi_val and rsi_val > 50: indicator_conf_boost += 0.05
                if ema_side == 'SELL': indicator_conf_boost += 0.1
        conf = min(0.99, conf_base + abs(imbalance)*0.25 + indicator_conf_boost)
        return side, conf
    except:
        return None, 0.0

def merge_decision(sym, timeframe_minutes, khist):
    if not khist or len(khist) < timeframe_minutes+5: return None
    window = khist[-1:]
    ob = fetch_orderbook(sym)
    indicators_enabled = (timeframe_minutes == 15)
    ut_side = lrc_side = None
    ut_conf = lrc_conf = 0.0
    st_val = None; rsi_val = None; ema_side = None; ema_strength = 0.0; bb = {'upper':None}
    if indicators_enabled:
        ut_side, ut_conf = utbot_flags(khist)
        lrc_side, lrc_conf = linreg_flags(khist)
        st_val = supertrend(khist)
        rsi_val = get_rsi(khist)
        ema_side, ema_strength = ema_crossover(khist)
        bb = bollinger_bands(khist)
    ai_side, ai_conf = ai_heuristics(khist, ob, st_val, rsi_val, ema_side, indicators_enabled)
    strength_score = combined_strength(ut_conf or 0, lrc_conf or 0) if indicators_enabled else 0.0
    votes = []
    if indicators_enabled:
        if ut_side and ut_side!='NEUTRAL': votes.append(ut_side)
        if lrc_side: votes.append(lrc_side)
    ind_side = None
    if votes:
        if votes.count('BUY') > votes.count('SELL'): ind_side='BUY'
        elif votes.count('SELL') > votes.count('BUY'): ind_side='SELL'
    if not ai_side: return None
    if indicators_enabled and ind_side is not None and ind_side == ai_side:
        final_side = ai_side; label='AI+INDICATORS'; conf=min(0.99, ai_conf+0.2 + 0.1*strength_score)
    elif indicators_enabled and ind_side is not None and ind_side != ai_side:
        return None
    else:
        final_side = ai_side; label='AI ONLY'; conf=ai_conf
    if conf < MIN_CONF_POST: return None
    if indicators_enabled:
        if st_val is not None:
            if final_side == 'BUY' and st_val != 'UP': return None
            if final_side == 'SELL' and st_val != 'DOWN': return None
        if ema_side is not None and ema_side != final_side:
            return None
        if rsi_val is not None:
            if final_side == 'BUY' and rsi_val > 70: return None
            if final_side == 'SELL' and rsi_val < 30: return None
        bb_pos = (bb or {}).get('position')
        trend = None
        if st_val in ('UP','DOWN'):
            trend = st_val
        elif ema_side in ('BUY','SELL'):
            trend = 'UP' if ema_side=='BUY' else 'DOWN'
        if bb_pos == 'above_upper' and final_side == 'BUY':
            if trend is None or trend != 'UP': return None
        if bb_pos == 'below_lower' and final_side == 'SELL':
            if trend is None or trend != 'DOWN': return None
    highs=[float(k[2]) for k in khist[-60:]] if len(khist)>=60 else [float(k[2]) for k in khist]
    lows=[float(k[3]) for k in khist[-60:]] if len(khist)>=60 else [float(k[3]) for k in khist]
    atrv = sum([(h-l) for h,l in zip(highs,lows)]) / max(1,len(highs))
    entry = float(window[-1][4])
    avg_range = atrv if atrv>0 else max(1e-6, max(highs)-min(lows))
    vf = 1.0
    if avg_range < 0.5: vf=0.8
    elif avg_range > 2.0: vf=1.6
    atr_val = atr(khist, UTBOT_ATR_PERIOD)
    high_volatility = False
    if atr_val and entry > 0:
        vol_ratio = atr_val / entry
        high_volatility = vol_ratio >= 0.002
    if high_volatility:
        dyn_tp_mult = 2.5
        dyn_sl_mult = 1.8
    else:
        dyn_tp_mult = 4.0
        dyn_sl_mult = 3.0
    if timeframe_minutes == 15:
        base_sl_mult = 2.2 * (dyn_sl_mult / 1.8)
    else:
        base_sl_mult = 1.2 * (dyn_sl_mult / 1.8)
    sl_distance = base_sl_mult * avg_range * vf
    if sl_distance <= 0 or math.isnan(sl_distance):
        sl_distance = max(0.0001 * entry, 0.5 * avg_range)
    tp_distance = 2.0 * sl_distance
    if final_side=='BUY':
        tp = round(entry + tp_distance, 8)
        sl = round(entry - sl_distance, 8)
    else:
        tp = round(entry - tp_distance, 8)
        sl = round(entry + sl_distance, 8)
    tkr = fetch_ticker(sym)
    qvol = 0.0
    if isinstance(tkr, dict):
        info = tkr.get('info', {})
        for k in ('quoteVolume','turnover24h','volumeUsd24h'):
            v = info.get(k)
            if v is not None:
                try:
                    qvol = float(v); break
                except:
                    pass
    vol_level = volume_level(khist)
    return {'timeframe':f"{timeframe_minutes}m",'label':label,'side':final_side,'confidence':conf,'entry':round(entry,8),
            'tp':tp,'sl':sl,'volume':vol_level,'ind_ut':ut_side,'ind_lrc':lrc_side,
            'rsi': rsi_val, 'supertrend': st_val, 'ema': ema_side, 'high_volatility': high_volatility,
            'bollinger': bb, 'strength_score': strength_score, 'qvol': qvol}
