#!/usr/bin/env python3
"""Evaluate reworked server analyze_tweet vs old QUESTIONS on train+heldout."""
import json, os, sys, time
from pathlib import Path

ROOT = Path(os.environ.get("XCRYSTAL_ROOT", str(Path(__file__).resolve().parents[1])))  # project root (server.py)
sys.path.insert(0, str(ROOT))

from laya_config import get_model_path

# Ensure server.py sees the resolved model path (env > project .env)
os.environ.setdefault("LAYA_MODEL_PATH", get_model_path())
os.environ.setdefault("LOG_FILE", str(Path(__file__).resolve().parent / "eval_server.log"))
os.environ.setdefault("CACHE_SIZE", "5000")

# Import after env set so server picks up paths
import server as srv
from laya import load

HERE = Path(__file__).resolve().parent
train = json.load(open(HERE / 'train_tweets.json'))
heldout = json.load(open(HERE / 'heldout_tweets.json'))

OLD_QUESTIONS = {
    "volatile": {"type": "noul", "instructions": "这条推文是否与加密货币相关"},
    "direction": {"type": "choice", "instructions": "会导致加密货币上涨还是下跌",
                  "criteria": ["bullish", "bearish", "neutral"]},
    "impact": {"type": "score", "instructions": "对加密货币市场的影响程度",
               "criteria": ["low", "medium", "high", "extreme"]},
}

def score_rows(rows, pred_fn, has_scope=True):
    n = rel_ok = sc_ok = sc_n = dir_ok = imp_ok = n_rel = 0
    rule_hits = 0
    uncertain_n = 0
    details = []
    for r in rows:
        exp = r['expected']  # [rel, scope, dir, impact]
        pred = pred_fn(r['text'], r.get('id'))
        n += 1
        vol = pred['volatile']
        rel_pred = (vol >= 0.5) if isinstance(vol, (int, float)) else bool(vol)
        if rel_pred == bool(exp[0]):
            rel_ok += 1
        scope = pred.get('scope')
        if has_scope and scope is not None:
            sc_n += 1
            if scope == exp[1]:
                sc_ok += 1
        if exp[0]:
            n_rel += 1
            if pred.get('direction') == exp[2]:
                dir_ok += 1
            if pred.get('impact') == exp[3]:
                imp_ok += 1
        if pred.get('rule_flags'):
            rule_hits += 1
        if pred.get('uncertain'):
            uncertain_n += 1
        details.append({
            'id': r['id'], 'expected': exp,
            'volatile': vol, 'scope': scope,
            'direction': pred.get('direction'),
            'direction_confidence': pred.get('direction_confidence'),
            'uncertain': pred.get('uncertain'),
            'impact': pred.get('impact'),
            'rule_flags': pred.get('rule_flags'),
        })
    return {
        'rel': f'{rel_ok}/{n}', 'scope': f'{sc_ok}/{sc_n}' if sc_n else '-',
        'dir': f'{dir_ok}/{n_rel}', 'imp': f'{imp_ok}/{n_rel}',
        'rule_hits': rule_hits, 'uncertain': uncertain_n,
        'rel_n': (rel_ok, n), 'dir_n': (dir_ok, n_rel), 'sc_n': (sc_ok, sc_n), 'imp_n': (imp_ok, n_rel),
        'details': details,
    }

print('Using model', srv.LAYA_MODEL_PATH)
print('Tickers loaded', len(srv.CRYPTO_TICKERS))
print('Uncertain threshold', srv.UNCERTAIN_THRESHOLD)

# New server path (with rules + simple_rel questions)
def new_pred(text, tid):
    return srv.analyze_tweet(text, tid)

# Old path: same agent, old questions, no rules, impact short label via round
_agent = srv.agent

def old_pred(text, tid=None):
    out = _agent.predict(text, OLD_QUESTIONS)
    a = out['answers']
    direction = a['direction']['choice']
    dir_probs = a['direction']['probabilities']
    score = a['impact']['score']
    legend = a['impact']['legend']
    raw = legend.get(str(round(score)), str(round(score)))
    short = str(raw).split(':')[0].strip()
    return {
        'volatile': a['volatile']['noul'],
        'scope': None,
        'direction': direction,
        'direction_confidence': max(dir_probs.values()),
        'uncertain': False,
        'impact': short,
        'rule_flags': [],
    }

results = {}
for name, rows in [('train', train), ('heldout', heldout)]:
    print(f'\n=== {name} NEW ===')
    t0 = time.time()
    results[f'{name}_new'] = score_rows(rows, new_pred, has_scope=True)
    print('took', round(time.time()-t0,1), 's')
    s = results[f'{name}_new']
    print(f"  rel={s['rel']} scope={s['scope']} dir={s['dir']} imp={s['imp']} "
          f"rules={s['rule_hits']} uncertain={s['uncertain']}")

    print(f'=== {name} OLD ===')
    t0 = time.time()
    results[f'{name}_old'] = score_rows(rows, old_pred, has_scope=False)
    print('took', round(time.time()-t0,1), 's')
    s = results[f'{name}_old']
    print(f"  rel={s['rel']} scope={s['scope']} dir={s['dir']} imp={s['imp']}")

# Show rule hits
print('\n=== Rule hits (new) ===')
for key in ['train_new', 'heldout_new']:
    for d in results[key]['details']:
        if d['rule_flags']:
            print(f"  {key} {d['id']}: flags={d['rule_flags']} vol={d['volatile']:.3f} scope={d['scope']}")

out_path = HERE / 'server_eval.json'
# strip details for summary md, keep full json
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

lines = ['# Server eval: old QUESTIONS vs reworked server', '',
         f'Uncertain threshold: {srv.UNCERTAIN_THRESHOLD}',
         f'Collision volatile cap: {srv.COLLISION_VOLATILE_CAP}', '',
         '| set | system | rel | scope | dir | impact | rule_hits | uncertain |',
         '|---|---|---|---|---|---|---|---|']
for name in ['train', 'heldout']:
    for sysname, key in [('old', f'{name}_old'), ('new', f'{name}_new')]:
        s = results[key]
        lines.append(
            f"| {name} | {sysname} | {s['rel']} | {s['scope']} | {s['dir']} | {s['imp']} | "
            f"{s['rule_hits']} | {s['uncertain']} |"
        )
(HERE / 'server_eval.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
print('\n'.join(lines))
print('\nWrote', out_path)
