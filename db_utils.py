import json, os
DB_FILE = 'replit_db_fallback.json'
try:
    from replit import db as _replit_db
    USE_REPLIT_DB = True
except Exception:
    _replit_db = None
    USE_REPLIT_DB = False

def _read_json():
    try:
        with open(DB_FILE, 'r') as f:
            return json.load(f)
    except Exception:
        return {}

def _write_json(d):
    try:
        with open(DB_FILE, 'w') as f:
            json.dump(d, f, indent=2)
    except Exception:
        pass

def db_get(k, default=None):
    if USE_REPLIT_DB:
        return _replit_db.get(k, default)
    d = _read_json()
    return d.get(k, default)

def db_set(k, v):
    if USE_REPLIT_DB:
        _replit_db[k] = v
        return
    d = _read_json()
    d[k] = v
    _write_json(d)

def db_push(k, item):
    arr = db_get(k, [])
    arr.append(item)
    db_set(k, arr)
