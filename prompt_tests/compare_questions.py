#!/usr/bin/env python3
"""
对比三套 laya 问题在同一批测试推文上的表现（不改动 server.py）：
  old     = server.py 当前的 QUESTIONS
  adapted = 按 Grok 内容改写、criteria 保持列表格式的版本
  grok    = Grok 原版（criteria 用字典，用来验证 laya 是否支持这种写法）

运行（在本目录，使用与 server.py 相同的 venv）：
  python3 compare_questions.py
  python3 compare_questions.py --help
结果写到本目录的 compare_results.md 和 compare_results.json（gitignored）。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(os.environ.get("XCRYSTAL_ROOT", str(Path(__file__).resolve().parents[1])))
sys.path.insert(0, str(ROOT))

from laya_config import get_model_path  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------- 三套问题
OLD = {
    "volatile": {"type": "noul", "instructions": "这条推文是否与加密货币相关"},
    "direction": {"type": "choice", "instructions": "会导致加密货币上涨还是下跌",
                  "criteria": ["bullish", "bearish", "neutral"]},
    "impact": {"type": "score", "instructions": "对加密货币市场的影响程度",
               "criteria": ["low", "medium", "high", "extreme"]},
}

ADAPTED = {
    "volatile": {
        "type": "noul",
        "instructions": (
            "Can this post move crypto prices, even if the headline is macro or geopolitics? "
            "YES: tokens, chains, exchanges, DeFi, NFT, RWA, L2, stablecoins, ETFs, unlocks, liquidations; "
            "or macro/geopolitics that changes liquidity or risk appetite (rates, FOMC, DXY, liquidity, war, "
            "sanctions, oil shock, Iran/Israel/Taiwan, banking stress) when the link is crypto, BTC, ETH, ETFs, "
            "risk assets, or safe-haven flows. "
            "NO: pure politics, war, or rates with no market, risk-asset, or crypto hook; "
            "stock or brand ticker collisions; personal or lifestyle posts."
        ),
    },
    "scope": {
        "type": "choice",
        "instructions": (
            "Which layer of crypto does this hit? "
            "btc_eth_macro = BTC, ETH, crypto ETFs, or a macro/geopolitical shock that reprices crypto as a risk or liquidity asset. "
            "sector = L2, DeFi, memes, AI-crypto, RWA, stablecoins, or one chain. "
            "single_asset = one token, protocol, or exchange. "
            "none = no crypto transmission."
        ),
        "criteria": ["btc_eth_macro", "sector", "single_asset", "none"],
    },
    "direction": {
        "type": "choice",
        "instructions": (
            "Is the new information good or bad for the assets in scope? Judge the event, not a price forecast. "
            "bullish = easier liquidity or higher risk appetite: rate cuts, dovish surprise, dollar down, ETF inflows, "
            "peace/de-escalation, listing, partnership, product live, legal win, buyback. "
            "bearish = tighter liquidity or risk-off: hikes, hawkish surprise, dollar spike, war escalation, sanctions, "
            "banking stress, hack, halt, depeg, unlock dump, lawsuit, ban, delisting. "
            "neutral = opinion, joke, old news, mixed macro (hawkish and dovish in one post), or no new fact."
        ),
        "criteria": ["bullish", "bearish", "neutral"],
    },
    "impact": {
        "type": "score",
        "instructions": (
            "How much can this move the assets in scope within hours to a few days? "
            "low = recycled headline, pundit take, minor in-line data. "
            "medium = real data surprise, limited regional conflict, mid-tier listing or outage. "
            "high = FOMC surprise, sudden escalation, ETF flow shock, large unlock, top-venue listing, $10M+ exploit, chain halt. "
            "extreme = emergency rate move, systemic war/sanctions shock, ETF approval/ban, exchange solvency crisis, "
            "stablecoin depeg, or an event that reprices BTC/ETH itself."
        ),
        "criteria": ["low", "medium", "high", "extreme"],
    },
}

GROK = {
    "volatile": {  # 原版叫 is_crypto，这里改名只为了方便统一对比
        "type": "noul",
        "instructions": "This post can move crypto prices, even if the headline is macro or geopolitics.",
        "criteria": {
            "true": "Tokens, chains, exchanges, DeFi, NFT, RWA, L2, stables, ETFs, unlocks, liquidations; OR macro/geopolitics that changes liquidity or risk appetite for crypto (rates, FOMC, DXY, liquidity, war, sanctions, oil shock, Iran/Israel/Taiwan, banking stress) when the link is crypto, BTC, ETH, ETF, risk assets, or safe-haven flows.",
            "false": "Pure politics, war, or rates with no market/risk-asset/crypto hook. Stock or brand ticker collision. Personal/lifestyle posts.",
        },
    },
    "scope": {
        "type": "choice",
        "instructions": "Which layer does this hit?",
        "criteria": {
            "btc_eth_macro": "BTC, ETH, crypto ETFs, or a macro/geopolitical shock that reprices crypto as a risk or liquidity asset.",
            "sector": "L2, DeFi, memes, AI-crypto, RWA, stables, one chain.",
            "single_asset": "One token, protocol, or exchange.",
            "none": "No crypto transmission.",
        },
    },
    "direction": {
        "type": "choice",
        "instructions": "Is the new information good or bad for the assets in scope? Judge the event, not a price forecast.",
        "criteria": {
            "bullish": "Easier liquidity or higher risk appetite: cuts, dovish surprise, dollar down, ETF inflow, peace/de-escalation, listing, partnership, product live, legal win, buyback.",
            "bearish": "Tighter liquidity or risk-off: hikes, hawkish surprise, dollar spike, war escalation, sanctions, banking stress, hack, halt, depeg, unlock dump, lawsuit, ban, delist.",
            "neutral": "Opinion, joke, old news, mixed macro (hawkish and dovish in one post), or no new fact.",
        },
    },
    "impact": {
        "type": "score",
        "instructions": "How much can this move the assets in scope in hours to a few days?",
        "criteria": [
            "low: recycled headline, pundit take, minor data in-line",
            "medium: real data surprise, limited regional conflict, mid-tier listing or outage",
            "high: FOMC surprise, sudden escalation, ETF flow shock, large unlock, top-venue listing, $10M+ exploit, chain halt",
            "extreme: emergency rate move, systemic war/sanctions shock, ETF approve/ban, exchange solvency, stable depeg, event that reprices BTC/ETH itself",
        ],
    },
}

VARIANTS = {"old": OLD, "adapted": ADAPTED, "grok": GROK}

# ---------------------------------------------------------------- 测试推文（全部为虚构）
# expected: (是否相关, scope, direction, impact) —— 人工给的参考答案
TWEETS = [
    ("fed_cut", "BREAKING: Fed cuts rates by 50bps in a surprise move. Powell signals more cuts are coming.", (True, "btc_eth_macro", "bullish", "high")),
    ("cpi_inline", "US CPI YoY comes in at 3.1%, exactly in line with expectations.", (True, "btc_eth_macro", "neutral", "low")),
    ("iran_israel", "Iran launches missiles at Israel. Oil jumps 8%, Bitcoin drops 5% within the hour.", (True, "btc_eth_macro", "bearish", "high")),
    ("senate_bill", "Senate passes the infrastructure bill 68-32 after weeks of debate.", (False, "none", "neutral", "low")),
    ("tsla_earnings", "$TSLA earnings beat, stock up 10% after hours on strong deliveries.", (False, "none", "neutral", "low")),
    ("sol_halt", "Solana mainnet has been halted for 5 hours. Validators are coordinating a restart.", (True, "sector", "bearish", "high")),
    ("exploit", "Lending protocol Nimbus exploited for $120M. Attacker is bridging funds to Ethereum right now.", (True, "single_asset", "bearish", "high")),
    ("binance_listing", "Binance will list $ABC. Spot trading opens today at 10:00 UTC.", (True, "single_asset", "bullish", "high")),
    ("usdc_depeg", "USDC depegs to $0.88 after Circle discloses $3.3B stuck at a failed bank.", (True, "sector", "bearish", "extreme")),
    ("eth_etf", "SEC approves spot Ethereum ETF applications from all major issuers.", (True, "btc_eth_macro", "bullish", "extreme")),
    ("gm", "GM crypto fam ☀️ coffee and charts, let's have a great day", (False, "none", "neutral", "low")),
    ("opinion", "I think BTC hits 200k by the end of the year. Not financial advice.", (True, "btc_eth_macro", "neutral", "low")),
    ("etf_inflow", "Spot Bitcoin ETFs saw $1.2B in net inflows yesterday, the largest day since launch.", (True, "btc_eth_macro", "bullish", "high")),
    ("unlock", "Reminder: 1.1B $ARB (~$1B) unlocks next week, about 87% of circulating supply.", (True, "single_asset", "bearish", "high")),
    ("tariff_truce", "US and China agree to a 90-day tariff truce. Nasdaq futures up 3%, risk assets rallying.", (True, "btc_eth_macro", "bullish", "medium")),
    ("fed_mixed", "Fed minutes: officials see rate cuts later this year but warn inflation remains sticky.", (True, "btc_eth_macro", "neutral", "low")),
    ("iphone", "Apple announces the iPhone 17 with a bigger battery and a new camera.", (False, "none", "neutral", "low")),
    ("zh_hike", "美联储意外加息50个基点，美元指数暴涨，比特币跌破6万美元。", (True, "btc_eth_macro", "bearish", "extreme")),
    ("zh_withdraw", "某头部交易所突然暂停提现，官方称系统维护，社区担心交易所资不抵债。", (True, "single_asset", "bearish", "extreme")),
    ("zh_lunch", "今天的午饭太好吃了，强烈推荐公司楼下这家拉面。", (False, "none", "neutral", "low")),
    ("uni_v4", "Uniswap v4 is now live on Ethereum mainnet, with hooks.", (True, "single_asset", "bullish", "medium")),
    ("throwback", "Throwback: remember when BTC hit 69k in November 2021?", (True, "btc_eth_macro", "neutral", "low")),
    ("ticker_link", "New summer collection just dropped 👗 $LINK in bio!", (False, "none", "neutral", "low")),
    ("mixer_sanction", "US Treasury sanctions a crypto mixer; several DeFi frontends start blocking US users.", (True, "sector", "bearish", "medium")),
    ("taiwan", "China announces live-fire drills encircling Taiwan. Asian stocks slide, gold spikes.", (True, "btc_eth_macro", "bearish", "high")),
]


def parse(ans, key):
    """把 laya 的答案统一成可比较的字段；字段缺失时尽量不报错"""
    a = ans.get(key)
    if a is None:
        return None
    if "noul" in a:
        return {"value": a["noul"]}
    if "choice" in a:
        return {"value": a["choice"], "probs": a.get("probabilities")}
    if "score" in a:
        score = a["score"]
        legend = a.get("legend") or {}
        label = legend.get(str(round(score)), str(round(score, 2)))
        return {"value": str(label).split(":")[0].strip(), "raw_label": label, "score": score,
                "probs": a.get("probabilities")}
    return {"value": a}


def run():
    from laya import load  # import here so --help works without laya installed

    model_path = get_model_path()
    print("Loading Laya model...")
    agent = load(model_path)
    print("Model loaded.\n")

    results = []
    for tid, text, exp in TWEETS:
        row = {"id": tid, "text": text, "expected": exp, "variants": {}}
        for vname, qs in VARIANTS.items():
            t0 = time.time()
            try:
                out = agent.predict(text, qs)
                ans = out["answers"]
                row["variants"][vname] = {
                    "ok": True,
                    "ms": round((time.time() - t0) * 1000),
                    **{k: parse(ans, k) for k in ("volatile", "scope", "direction", "impact")},
                }
            except Exception as e:
                row["variants"][vname] = {"ok": False, "error": f"{type(e).__name__}: {e}",
                                          "trace": traceback.format_exc(limit=3)}
        results.append(row)
        print(f"done: {tid}")

    with open(os.path.join(HERE, "compare_results.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)

    # ------------------------------------------------ Markdown 报告
    def fmt(v):
        if not v.get("ok"):
            return "ERROR"
        rel = v["volatile"]["value"] if v.get("volatile") else None
        rel_s = f"{rel:.2f}" if isinstance(rel, (int, float)) else str(rel)
        parts = [rel_s]
        if v.get("scope"):
            parts.append(v["scope"]["value"])
        parts.append(v["direction"]["value"] if v.get("direction") else "-")
        parts.append(v["impact"]["value"] if v.get("impact") else "-")
        return " / ".join(str(p) for p in parts)

    lines = ["# laya 问题集对比", "",
             "每格格式：相关概率 / (scope) / direction / impact", "",
             "| id | 推文 | 参考答案 | old | adapted | grok |", "|---|---|---|---|---|---|"]
    for r in results:
        e = r["expected"]
        exp_s = f"{'相关' if e[0] else '不相关'} / {e[1]} / {e[2]} / {e[3]}"
        cells = [fmt(r["variants"][v]) for v in VARIANTS]
        lines.append(f"| {r['id']} | {r['text'][:60].replace('|', '/')} | {exp_s} | " + " | ".join(cells) + " |")

    # 准确率
    lines += ["", "## 与参考答案的一致率", "", "| 问题集 | 相关性(阈值0.5) | scope | direction | impact | 平均耗时ms | 报错数 |",
              "|---|---|---|---|---|---|---|"]
    for vname in VARIANTS:
        n = rel_ok = sc_ok = sc_n = dir_ok = imp_ok = errs = 0
        ms = []
        for r in results:
            v = r["variants"][vname]
            if not v.get("ok"):
                errs += 1
                continue
            n += 1
            ms.append(v["ms"])
            e = r["expected"]
            rel = v["volatile"]["value"] if v.get("volatile") else None
            if isinstance(rel, (int, float)) and (rel >= 0.5) == e[0]:
                rel_ok += 1
            elif isinstance(rel, bool) and rel == e[0]:
                rel_ok += 1
            if v.get("scope"):
                sc_n += 1
                sc_ok += v["scope"]["value"] == e[1]
            # direction / impact 只在参考答案为“相关”的推文上统计
            if e[0]:
                dir_ok += v["direction"]["value"] == e[2]
                imp_ok += v["impact"]["value"] == e[3]
        n_rel = sum(1 for r in results if r["expected"][0] and r["variants"][vname].get("ok"))
        pct = lambda a, b: f"{a}/{b}" if b else "-"
        lines.append(f"| {vname} | {pct(rel_ok, n)} | {pct(sc_ok, sc_n)} | {pct(dir_ok, n_rel)} | {pct(imp_ok, n_rel)} | "
                     f"{round(sum(ms)/len(ms)) if ms else '-'} | {errs} |")

    errors = [(r["id"], vn, v["error"]) for r in results for vn, v in r["variants"].items() if not v.get("ok")]
    if errors:
        lines += ["", "## 报错", ""] + [f"- {tid} [{vn}]: {err}" for tid, vn, err in errors[:20]]

    # grok 版的 impact 原始标签，用来确认 legend 会不会变成长字符串
    lines += ["", "## grok 版 impact 的原始 legend 标签（抽样）", ""]
    for r in results[:3]:
        v = r["variants"]["grok"]
        if v.get("ok") and v.get("impact"):
            lines.append(f"- {r['id']}: {v['impact'].get('raw_label')}")

    report = "\n".join(lines)
    with open(os.path.join(HERE, "compare_results.md"), "w", encoding="utf-8") as f:
        f.write(report)
    print("\n" + report)
    print(f"\n结果已写入 {HERE}/compare_results.md 和 compare_results.json")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Compare three laya QUESTIONS variants on a fixed tweet set "
        "(writes compare_results.md / .json in this directory)."
    )
    parser.parse_args(argv)  # supports --help without loading the model
    run()


if __name__ == "__main__":
    main()
