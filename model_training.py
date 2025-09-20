import os, pickle
from config import MODEL_FILE
from db_utils import db_get, db_set
USE_SKLEARN = True
try:
    from sklearn.ensemble import RandomForestClassifier
    import numpy as np
except Exception:
    USE_SKLEARN = False

def features_from_record(rec):
    ind_ut = 1 if rec.get('ind_ut')=='BUY' else (-1 if rec.get('ind_ut')=='SELL' else 0)
    ind_lrc = 1 if rec.get('ind_lrc')=='BUY' else (-1 if rec.get('ind_lrc')=='SELL' else 0)
    conf = float(rec.get('confidence') or 0)
    vol = 1 if (rec.get('volume')=='High') else 0
    entry = float(rec.get('entry') or 0); tp=float(rec.get('tp') or 0); sl=float(rec.get('sl') or 0)
    atr_proxy = abs(tp-entry)+abs(entry-sl)
    side = 1 if rec.get('side')=='BUY' else 0
    bb = rec.get('bollinger') or {}
    bb_width = bb.get('width') or 0
    strength = rec.get('strength_score') or 0
    return [ind_ut, ind_lrc, conf, vol, atr_proxy, side, bb_width, strength]

def _collect_training_data_from_history():
    hist = db_get('trades_history', [])
    closed = [h for h in hist if str(h.get('status','')).startswith('closed')]
    filteredX=[]; filteredy=[]
    for r in closed:
        try:
            feat = features_from_record(r)
            filteredX.append(feat[:-1])
            filteredy.append(1 if r.get('status')=='closed_win' else 0)
        except:
            pass
    return filteredX, filteredy

def train_and_save_model(X, y):
    if not USE_SKLEARN or len(X) < 50:
        print('Not enough data or sklearn not available - skipping training.')
        return None
    try:
        X = np.array(X); y = np.array(y)
        clf = RandomForestClassifier(n_estimators=60, max_depth=8, random_state=42)
        clf.fit(X,y)
        with open(MODEL_FILE,'wb') as f:
            pickle.dump(clf,f)
        print(f'Model trained on {len(X)} samples & saved.')
        return clf
    except Exception as e:
        print('train error', e)
        return None

def load_model():
    if not USE_SKLEARN:
        return None
    try:
        if os.path.exists(MODEL_FILE):
            with open(MODEL_FILE,'rb') as f:
                return pickle.load(f)
    except Exception as e:
        print('load_model error', e)
    return None
