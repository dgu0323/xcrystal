# XCrystal prompt / server tests

Eval harnesses and tweet sets used while tuning QUESTIONS and the Flask server.

Server code lives in the **project / repo root** (`server.py`, `.env`, `crypto_tickers.txt`), not inside the Chrome extension.

## Files
- `train_tweets.json` — original 25 made-up tweets + reference answers
- `heldout_tweets.json` — new held-out 25 made-up tweets + reference answers
- `prompt_variants.py` — variant experiment harness (loads laya, scores variants)
- `chosen_questions.json` — winning QUESTIONS (`simple_rel`)
- `variant_summary.md` — accuracy table across variants (generated; gitignored)
- `eval_server.py` — old QUESTIONS vs reworked `server.analyze_tweet`
- `server_eval.md` — final old vs new accuracy (generated; gitignored)
- `compare_questions.py` — compare three QUESTIONS variants on an embedded tweet set (writes `compare_results.md` / `.json` here; gitignored)

## Rerun with your model

```bash
# Start the API server (from the project / repo root):
cd /path/to/repo
pip install -r requirements.txt   # once
./start.sh
# or: source .venv/bin/activate && python server.py
# → http://127.0.0.1:5678  (from .env)

# Offline eval (imports ../server.py via XCRYSTAL_ROOT / parent dir):
cd prompt_tests
python3 eval_server.py

# Optional: re-run prompt variants:
LAYA_MODEL_PATH=/path/to/laya/multilingual \
  python3 prompt_variants.py
# (or rely on LAYA_MODEL_PATH in the project-root .env)

# Optional: compare three QUESTIONS variants:
python3 compare_questions.py --help
python3 compare_questions.py
```

`eval_server.py` / `compare_questions.py` / `prompt_variants.py` add the project root to `sys.path` so `import server` and `import laya_config` resolve. Override with `XCRYSTAL_ROOT` / `LAYA_MODEL_PATH` if needed.
