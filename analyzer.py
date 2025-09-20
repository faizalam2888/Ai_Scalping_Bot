import time
from exchange_utils import fetch_ticker, fetch_klines, fetch_top_n_symbols
from ai_logic import merge_decision
from db_utils import db_get, db_set
from telegram_utils import send_telegram, safe_print_exc
from trade_manager import active_trades, active_lock, record_trade
from model_training import load_model
from config import MIN_24H_VOL_USDT, MIN_CONF_POST, HIGH_CONF, PARTIAL_TP_RATIO, MARGIN_USD
from exchange_utils import fetch_and_set_max_leverage
from trade_manager import compute_estimated_pnl_usd
def _is_on_cooldown(sym, timeframe_label):
    try:
        cooldowns = db_get('cooldowns', {})
        key = f"{sym}|{timeframe_label}"
        until_ms = cooldowns.get(key)
        if not until_ms:
            return False
        return int(time.time()*1000) < int(until_ms)
    except:
        return False

def analyze_and_post(sym, minute, model):
    try:
        valid_timeframes = []
        if minute % 5 == 0:
            valid_timeframes.append('5m')
        if minute % 15 == 0:
            valid_timeframes.append('15m')
        if not valid_timeframes:
            print('HOLD - Waiting for a valid candle close time.')
            return
        for tf in valid_timeframes:
            if sym in active_trades:
                print('SKIP - active trade already exists for', sym)
                continue
            if _is_on_cooldown(sym, tf):
                print('SKIP -', sym, tf, 'is on cooldown')
                continue
            pub = fetch_ticker(sym)
            qvol = 0.0
            if pub and isinstance(pub, dict):
                info = pub.get('info', {})
                for k in ('quoteVolume','turnover24h','volumeUsd24h'):
                    v = info.get(k)
                    if v is not None:
                        try:
                            qvol = float(v); break
                        except:
                            pass
            if qvol and qvol < MIN_24H_VOL_USDT:
                print('SKIP - Low 24h vol for', sym, 'at', tf, qvol)
                continue
            khist = fetch_klines(sym, interval=tf, limit=300)
            sig = merge_decision(sym, int(tf.replace('m','')), khist)
            if not sig:
                print('HOLD - No trade signal for', sym, 'on', tf)
                continue
            other_tf = '15m' if tf == '5m' else '5m'
            try:
                khist_other = fetch_klines(sym, interval=other_tf, limit=300)
                other_sig = merge_decision(sym, int(other_tf.replace('m','')), khist_other)
                if other_sig and other_sig.get('side') and sig.get('side') and other_sig.get('side') != sig.get('side'):
                    print('REJECT - Opposite signals 5m vs 15m for', sym)
                    continue
            except Exception:
                pass
            if model:
                try:
                    feat = [1 if sig.get('ind_ut')=='BUY' else (-1 if sig.get('ind_ut')=='SELL' else 0),
                            1 if sig.get('ind_lrc')=='BUY' else (-1 if sig.get('ind_lrc')=='SELL' else 0),
                            sig.get('confidence',0),
                            1 if sig.get('volume')=='High' else 0,
                            abs(sig.get('tp') - sig.get('entry')) + abs(sig.get('entry') - sig.get('sl')),
                            (sig.get('bollinger') or {}).get('width') or 0,
                            sig.get('strength_score') or 0]
                    prob = model.predict_proba([feat])[0][1]
                    if prob < MIN_CONF_POST:
                        print(sym, 'model low prob on', tf, prob)
                        continue
                except Exception:
                    pass
            lev = fetch_and_set_max_leverage(sym) or 10
            with active_lock:
                if sym in active_trades: continue
                conf_label = 'High' if sig['confidence']>=HIGH_CONF else 'Medium'
                pnl_tp = compute_estimated_pnl_usd(sig['entry'], sig['tp'], MARGIN_USD, lev, sig['side'])
                pnl_sl = compute_estimated_pnl_usd(sig['entry'], sig['sl'], MARGIN_USD, lev, sig['side'])
                msg = (f"Signal ({sig['timeframe']}) - {sig['label']}\nPair: {sym}\nAction: {sig['side']}\nCurrent price: {sig['entry']}\n"
                        f"FullTP: {sig['tp']} (≈ ${pnl_tp:.2f})\nSL: {sig['sl']} (≈ ${pnl_sl:.2f})\n"
                        f"Confidence: ({conf_label})\nVolume: ({sig['volume']})")
                send_telegram(msg)
                active_trades[sym] = {'symbol':sym,'timeframe':sig['timeframe'],'label':sig['label'],'side':sig['side'],
                                      'entry':sig['entry'],'tp':sig['tp'],'sl':sig['sl'],'confidence':sig['confidence'],
                                      'volume':sig['volume'],'ind_ut':sig.get('ind_ut'),'ind_lrc':sig.get('ind_lrc'),
                                      'open_time':None, 'partial_done': False}
            record_trade({**active_trades[sym],'symbol':sym}, status='opened')
            stats = db_get('accuracy_stats')
            if sig['label'] in stats:
                stats[sig['label']]['trades'] += 1
                db_set('accuracy_stats', stats)
    except Exception:
        safe_print_exc('analyze_and_post')
