import requests, traceback, sys
from datetime import datetime
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

def send_telegram(text: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print('[telegram] token/chat id not set - skipping send')
        return
    url = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage'
    try:
        r = requests.post(url, data={'chat_id': TELEGRAM_CHAT_ID, 'text': text}, timeout=8)
        r.raise_for_status()
    except Exception as e:
        print('Telegram send failed:', e)

def safe_print_exc(tag='ERROR'):
    print(f'[{tag}]', datetime.utcnow().isoformat())
    traceback.print_exc(file=sys.stdout)
    try:
        send_telegram(f'⚠ Bot Error: {tag}\nSee logs.')
    except:
        pass

def format_price(p: float) -> str:
    try:
        if p is None or p == 0: return '0'
        s = f'{p:.8f}' if abs(p) < 1 else f'{p:.6f}'
        s = s.rstrip('0').rstrip('.')
        return s
    except:
        return str(p)
