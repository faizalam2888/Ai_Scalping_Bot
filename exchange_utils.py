import ccxt, time
from config import MEXC_API_KEY, MEXC_SECRET_KEY, DEFAULT_LEVERAGE
from telegram_utils import safe_print_exc
exchange = None
def init_exchange():
    global exchange
    if exchange is not None:
        return exchange
    if not MEXC_API_KEY or not MEXC_SECRET_KEY:
        raise SystemExit('Missing MEXC credentials in env')
    exchange = ccxt.mexc({
        'apiKey': MEXC_API_KEY,
        'secret': MEXC_SECRET_KEY,
        'enableRateLimit': True,
        'options': {'defaultType': 'swap'}
    })
    return exchange

def fetch_markets_once():
    try:
        ex = init_exchange()
        return ex.load_markets()
    except Exception:
        safe_print_exc('load_markets')
        return {}

def _is_usdt_swap_sym(market):
    try:
        return market.get('type') == 'swap' and market.get('linear') and market.get('quote') == 'USDT'
    except:
        return False

def fetch_top_n_symbols(n=500):
    try:
        markets = fetch_markets_once()
        candidates = []
        for sym, m in markets.items():
            if _is_usdt_swap_sym(m):
                vol = m.get('info', {}).get('volume24h') or m.get('info', {}).get('turnover24h') or 0
                try:
                    vol = float(vol)
                except:
                    vol = 0.0
                candidates.append((sym, vol))
        candidates.sort(key=lambda x: x[1], reverse=True)
        return [s for s,_ in candidates[:n]]
    except Exception:
        safe_print_exc('fetch_top_n_symbols')
        return []

def fetch_klines(symbol, interval='15m', limit=200):
    try:
        ex = init_exchange()
        ohlcv = ex.fetch_ohlcv(symbol, timeframe=interval, limit=limit)
        return [[c[0], c[1], c[2], c[3], c[4], c[5]] for c in ohlcv] if ohlcv else []
    except Exception:
        return []

def fetch_ticker(symbol):
    try:
        ex = init_exchange()
        return ex.fetch_ticker(symbol) or {}
    except Exception:
        return {}

def fetch_orderbook(symbol, limit=50):
    try:
        ex = init_exchange()
        return ex.fetch_order_book(symbol, limit=limit) or {'bids': [], 'asks': []}
    except Exception:
        return {'bids': [], 'asks': []}

def fetch_last_price(symbol):
    try:
        t = fetch_ticker(symbol)
        info = t.get('info', {}) if isinstance(t, dict) else {}
        for k in ('markPrice','lastPrice','last'):
            v = info.get(k)
            if v is not None:
                try:
                    return float(v)
                except:
                    pass
        last = t.get('last')
        return float(last) if last is not None else None
    except Exception:
        return None

_LEVERAGE_CACHE = {}
def fetch_and_set_max_leverage(symbol):
    if symbol in _LEVERAGE_CACHE:
        return _LEVERAGE_CACHE[symbol]
    try:
        markets = fetch_markets_once()
        m = markets.get(symbol, {})
        limits = m.get('limits', {}).get('leverage', {})
        max_lev = limits.get('max') or DEFAULT_LEVERAGE
        try:
            ex = init_exchange()
            try:
                ex.set_leverage(int(max_lev), symbol, params={'marginMode': 'cross'})
            except Exception:
                try:
                    ex.set_leverage(int(max_lev), symbol)
                except:
                    pass
        except:
            pass
        _LEVERAGE_CACHE[symbol] = int(max_lev)
        return int(max_lev)
    except Exception:
        _LEVERAGE_CACHE[symbol] = DEFAULT_LEVERAGE
        return DEFAULT_LEVERAGE
