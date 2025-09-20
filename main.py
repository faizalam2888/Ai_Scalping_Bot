import time, threading
from telegram_utils import send_telegram, safe_print_exc
from exchange_utils import init_exchange, fetch_top_n_symbols, fetch_and_set_max_leverage
from analyzer import analyze_and_post
from model_training import load_model
from db_utils import db_get, db_set
from config import SYMBOLS_MANDATORY, DYNAMIC_TOP_N, CHECK_INTERVAL_MAIN
from trade_manager import monitor_loop
def seed_train_on_start():
    return load_model()
def main():
    send_telegram('Scalping Bot (Futures) Started Successfully.')
    print('Bot started. Loading model...')
    MODEL = seed_train_on_start()
    try:
        init_exchange().load_markets()
    except Exception:
        safe_print_exc('load_markets_on_start')
    mon = threading.Thread(target=monitor_loop, kwargs={'check_interval':5}, daemon=True)
    mon.start()
    dynamic_list = []
    try:
        all_symbols = fetch_top_n_symbols(500)
        chosen=[]
        for s in all_symbols:
            if s in SYMBOLS_MANDATORY: continue
            chosen.append(s)
            if len(chosen) >= DYNAMIC_TOP_N:
                break
        dynamic_list = chosen
    except Exception:
        safe_print_exc('dynamic_load')
    SYMBOLS = SYMBOLS_MANDATORY + dynamic_list
    print('Monitoring symbols:', SYMBOLS)
    for sym in SYMBOLS:
        try:
            fetch_and_set_max_leverage(sym)
        except:
            pass
    while True:
        try:
            now = time.gmtime()
            minute = now.tm_min
            for sym in SYMBOLS:
                analyze_and_post(sym, minute, MODEL)
                time.sleep(0.2)
        except KeyboardInterrupt:
            print('Stopped by user.')
            break
        except Exception:
            safe_print_exc('main_loop')
        to_sleep = CHECK_INTERVAL_MAIN - (time.time() % CHECK_INTERVAL_MAIN)
        if to_sleep < 0.05:
            to_sleep = 0.05
        time.sleep(to_sleep)
if __name__ == '__main__':
    main()
