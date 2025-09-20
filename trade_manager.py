import threading, time, math
from datetime import datetime, timezone
from db_utils import db_get, db_set, db_push
from telegram_utils import send_telegram, safe_print_exc, format_price
from config import MARGIN_USD, COOLDOWN_MINUTES_AFTER_CLOSE, DEFAULT_LEVERAGE
from exchange_utils import fetch_and_set_max_leverage, fetch_last_price, fetch_ticker
active_trades = {}
active_lock = threading.Lock()

def record_trade(history_entry, status='opened'):
    rec = {'ts':datetime.now(timezone.utc).isoformat(),'symbol':history_entry.get('symbol'),'timeframe':history_entry.get('timeframe'),
           'label':history_entry.get('label'),'side':history_entry.get('side'),'entry':history_entry.get('entry'),
           'tp':history_entry.get('tp'),'sl':history_entry.get('sl'),'confidence':history_entry.get('confidence'),
           'volume':history_entry.get('volume'),'ind_ut':history_entry.get('ind_ut'),'ind_lrc':history_entry.get('ind_lrc'),
           'status':status}
    db_push('trades_history', rec)

def update_accuracy(label, win):
    stats = db_get('accuracy_stats', {'AI+INDICATORS':{'wins':0,'losses':0,'trades':0},'AI ONLY':{'wins':0,'losses':0,'trades':0}})
    key = label if label in stats else ('AI ONLY' if label=='AI ONLY' else 'AI+INDICATORS')
    if win: stats[key]['wins'] += 1
    else: stats[key]['losses'] += 1
    stats[key]['trades'] += 1
    db_set('accuracy_stats', stats)

def compute_estimated_pnl_usd(entry, target_price, margin_usd, leverage, side):
    try:
        pos_notional = margin_usd * leverage
        contracts = math.floor(pos_notional / entry) if entry > 0 else 0
        if contracts <= 0:
            return 0.0
        if side == 'BUY':
            pnl = (target_price - entry) * contracts
        else:
            pnl = (entry - target_price) * contracts
        return float(pnl)
    except:
        return 0.0

def _bump_retrain_counter_and_maybe_retrain():
    try:
        cnt = int(db_get('retrain_counter', 0)) + 1
        db_set('retrain_counter', cnt)
    except:
        safe_print_exc('retrain_counter')

def monitor_loop(check_interval=5):
    while True:
        try:
            with active_lock:
                syms=list(active_trades.keys())
            for s in syms:
                try:
                    t = active_trades.get(s)
                    if not t: continue
                    price = fetch_last_price(s)
                    if price is None:
                        tk = fetch_ticker(s)
                        price = float(tk.get('last') or t.get('entry'))
                    if price is None or price <= 0: continue
                    entry = float(t['entry']); tp = float(t['tp']); sl = float(t['sl']); side=t['side']
                    hit_tp = (side=='BUY' and price>=tp) or (side=='SELL' and price<=tp)
                    hit_be = False
                    if t.get('partial_done'):
                        partial_time = t.get('partial_time', 0)
                        if time.time() - partial_time > 1.0:
                            threshold = max(0.0005 * entry, 0.0000001 * entry)
                            if side == 'BUY':
                                if price <= entry and abs(price-entry) <= threshold:
                                    hit_be = True
                            else:
                                if price >= entry and abs(price-entry) <= threshold:
                                    hit_be = True
                    hit_sl = (side=='BUY' and price<=sl) or (side=='SELL' and price>=sl)
                    lev = fetch_and_set_max_leverage(s) or DEFAULT_LEVERAGE
                    pnl_tp = compute_estimated_pnl_usd(entry, tp, MARGIN_USD, lev, side)
                    pnl_sl = compute_estimated_pnl_usd(entry, sl, MARGIN_USD, lev, side)
                    if hit_tp:
                        send_telegram(f"Signal ({t['timeframe']}) - {t['label']}\nPair: {s}\nAction: {side}\nTarget Hit: TP\nPrice: {format_price(tp)} ✅\nProfit: (≈ ${pnl_tp:.2f})")
                        update_accuracy(t['label'], True)
                        record_trade({**t,'symbol':s}, status='closed_win')
                        with active_lock: active_trades.pop(s,None)
                        try:
                            cooldowns = db_get('cooldowns', {})
                            cooldown_until = int(time.time()*1000) + COOLDOWN_MINUTES_AFTER_CLOSE*60*1000
                            cooldowns[f"{s}|5m"] = cooldown_until
                            cooldowns[f"{s}|15m"] = cooldown_until
                            db_set('cooldowns', cooldowns)
                        except:
                            pass
                        _bump_retrain_counter_and_maybe_retrain()
                        continue
                    if hit_be:
                        send_telegram(f"Signal ({t['timeframe']}) - {t['label']}\nPair: {s}\nAction: {side}\nTarget Hit: BreakEven\nPrice: {format_price(entry)} ⚖️")
                        update_accuracy(t['label'], False)
                        record_trade({**t,'symbol':s}, status='closed_be')
                        with active_lock: active_trades.pop(s,None)
                        try:
                            cooldowns = db_get('cooldowns', {})
                            cooldown_until = int(time.time()*1000) + COOLDOWN_MINUTES_AFTER_CLOSE*60*1000
                            cooldowns[f"{s}|5m"] = cooldown_until
                            cooldowns[f"{s}|15m"] = cooldown_until
                            db_set('cooldowns', cooldowns)
                        except:
                            pass
                        _bump_retrain_counter_and_maybe_retrain()
                        continue
                    if hit_sl:
                        send_telegram(f"Signal ({t['timeframe']}) - {t['label']}\nPair: {s}\nAction: {side}\nTarget Hit: SL\nPrice: {format_price(sl)} ❌\nLoss: (≈ ${pnl_sl:.2f})")
                        update_accuracy(t['label'], False)
                        record_trade({**t,'symbol':s}, status='closed_loss')
                        with active_lock: active_trades.pop(s,None)
                        try:
                            cooldowns = db_get('cooldowns', {})
                            cooldown_until = int(time.time()*1000) + COOLDOWN_MINUTES_AFTER_CLOSE*60*1000
                            cooldowns[f"{s}|5m"] = cooldown_until
                            cooldowns[f"{s}|15m"] = cooldown_until
                            db_set('cooldowns', cooldowns)
                        except:
                            pass
                        _bump_retrain_counter_and_maybe_retrain()
                        continue
                    if side=='BUY':
                        halfway = entry + (tp-entry)*0.5
                        if price >= halfway and not t.get('partial_done'):
                            pnl_partial = compute_estimated_pnl_usd(entry, halfway, MARGIN_USD, fetch_and_set_max_leverage(s), side)
                            send_telegram(f"Signal ({t['timeframe']}) - {t['label']}\nPair: {s}\nAction: {side}\nPartial TP Hit: 50% booked, SL moved to BE\nPrice: {format_price(halfway)}\nEstimated P/L at Partial: (≈ ${pnl_partial:.2f})")
                            with active_lock:
                                active_trades[s]['partial_done'] = True
                                active_trades[s]['partial_time'] = time.time()
                                active_trades[s]['sl'] = entry
                    else:
                        halfway = entry - (entry - tp)*0.5
                        if price <= halfway and not t.get('partial_done'):
                            pnl_partial = compute_estimated_pnl_usd(entry, halfway, MARGIN_USD, fetch_and_set_max_leverage(s), side)
                            send_telegram(f"Signal ({t['timeframe']}) - {t['label']}\nPair: {s}\nAction: {side}\nPartial TP Hit: 50% booked, SL moved to BE\nPrice: {format_price(halfway)}\nEstimated P/L at Partial: (≈ ${pnl_partial:.2f})")
                            with active_lock:
                                active_trades[s]['partial_done'] = True
                                active_trades[s]['partial_time'] = time.time()
                                active_trades[s]['sl'] = entry
                except Exception:
                    safe_print_exc('monitor_inner')
            time.sleep(check_interval)
        except Exception:
            safe_print_exc('monitor_loop')
            time.sleep(5)
