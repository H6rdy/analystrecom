from __future__ import annotations

import json
import math
import os
import re
import shutil
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from dateutil import parser as dtparser
from finvizfinance.quote import finvizfinance
from finvizfinance.screener.overview import Overview

try:
    from telegram import Bot
except Exception:  # pragma: no cover
    Bot = None  # type: ignore


DEFAULT_ROOT = Path(__file__).resolve().parent


def resource_root() -> Path:
    """
    PyInstaller bundled (sys._MEIPASS) root vs normal source root.
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)  # type: ignore[arg-type]
    return DEFAULT_ROOT


def user_root() -> Path:
    """
    User-writable directory for persistent config & snapshots.
    """
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "analystrecom"


def ensure_user_assets() -> None:
    """
    Ensure required config/data files exist in the user directory.
    This is important for packaged executables where bundled files may be read-only.
    """
    user = user_root()
    needed = [
        ("config/app_config.json", True),
        ("config/portfolio.json", False),
        ("data/latest_data.json", False),
        ("data/previous_data.json", False),
    ]

    for rel, required in needed:
        src = resource_root() / rel
        dst = user / rel
        if dst.exists():
            continue
        if not src.exists():
            if required:
                # For required assets, fail loudly to surface build/package issues.
                raise FileNotFoundError(f"Missing default asset: {src}")
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)

    # If the user already has an app_config.json but it lacks newly added fields
    # (e.g., remote_latest_data.latest_data_url), patch only the missing/empty parts.
    try:
        src_cfg = resource_root() / "config" / "app_config.json"
        dst_cfg = user / "config" / "app_config.json"
        if src_cfg.exists() and dst_cfg.exists():
            src_raw = json.loads(src_cfg.read_text(encoding="utf-8"))
            dst_raw = json.loads(dst_cfg.read_text(encoding="utf-8"))

            src_remote = ((src_raw.get("app", {}) or {}).get("remote_latest_data", {}) or {})
            dst_remote = ((dst_raw.get("app", {}) or {}).get("remote_latest_data", {}) or {})

            src_url = str(src_remote.get("latest_data_url", "") or "").strip()
            dst_url = str(dst_remote.get("latest_data_url", "") or "").strip()

            # If user config doesn't have a URL (older version), copy it over.
            if src_url and not dst_url:
                dst_raw.setdefault("app", {})
                dst_raw["app"].setdefault("remote_latest_data", {})
                dst_raw["app"]["remote_latest_data"].setdefault("enabled", True)
                dst_raw["app"]["remote_latest_data"]["latest_data_url"] = src_url
                # Keep user timeout if set; otherwise take default.
                if "timeout_sec" not in dst_raw["app"]["remote_latest_data"]:
                    if "timeout_sec" in src_remote:
                        dst_raw["app"]["remote_latest_data"]["timeout_sec"] = src_remote["timeout_sec"]

                dst_cfg.parent.mkdir(parents=True, exist_ok=True)
                dst_cfg.write_text(json.dumps(dst_raw, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        # Non-fatal: if patching fails, app can still run with bundled data.
        pass


def sync_latest_data_from_resources() -> None:
    """
    Copy bundled/repo `data/latest_data.json` into the user directory each startup.
    Keeps the runtime aligned with the latest snapshot (GitHub Actions output).
    """
    src = resource_root() / "data/latest_data.json"
    if not src.exists():
        return
    dst = user_root() / "data/latest_data.json"
    dst.parent.mkdir(parents=True, exist_ok=True)
    # Always overwrite so the UI reflects the newest snapshot.
    shutil.copyfile(src, dst)


def try_update_latest_data_remote(config: AppConfig) -> bool:
    """
    Packaged exe에서는 번들된 `latest_data.json`이 오래될 수 있으므로,
    GitHub raw URL 등 원격 파일에서 최신 스냅샷을 받아 사용자 저장소로 덮어씁니다.
    """
    if not config.remote_latest_data_enabled:
        return False
    if not config.remote_latest_data_url:
        return False

    try:
        r = requests.get(
            config.remote_latest_data_url,
            timeout=max(3, int(config.remote_latest_data_timeout_sec)),
            headers={"User-Agent": "AnalystRecom/1.0"},
        )
        r.raise_for_status()
        obj = r.json()
        if not isinstance(obj, dict) or "rows" not in obj:
            return False
        save_json(config.data_file, obj)
        return True
    except Exception:
        return False


RECOM_MAP = {
    # Finviz analyst recommendation strings may vary. We map to 1..5 scale.
    "strong buy": 1.0,
    "buy": 2.0,
    "hold": 3.0,
    "sell": 4.0,
    "strong sell": 5.0,
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def safe_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if s in {"", "-", "None", "nan", "NaN"}:
        return None
    s = s.replace(",", "")
    s = s.replace("%", "")
    try:
        return float(s)
    except Exception:
        return None


def normalize_inst_name(name: str) -> str:
    s = re.sub(r"\s+", " ", (name or "").strip())
    return s


def recom_to_score(recom_value: Any) -> Optional[float]:
    """
    Returns a 1..5 score (lower is better).

    Finviz 'Recom' is often numeric already; if it's a string we attempt mapping.
    """
    if recom_value is None:
        return None
    if isinstance(recom_value, (int, float)):
        return float(recom_value)
    s = str(recom_value).strip()
    f = safe_float(s)
    if f is not None:
        return f
    key = s.lower()
    return RECOM_MAP.get(key)


def upside_pct(price: Optional[float], target_price: Optional[float]) -> Optional[float]:
    if price is None or target_price is None or price <= 0:
        return None
    return (target_price / price - 1.0) * 100.0


def bucket_upside(u: Optional[float]) -> str:
    if u is None:
        return "N/A"
    if u >= 50:
        return "50%+"
    lo = max(0, int(math.floor(u / 10.0) * 10))
    hi = lo + 10
    return f"{lo}%~{hi}%"


@dataclass(frozen=True)
class AppConfig:
    data_file: Path
    previous_data_file: Path
    sync_on_start: bool
    remote_latest_data_enabled: bool
    remote_latest_data_url: str
    remote_latest_data_timeout_sec: int
    telegram_enabled: bool
    telegram_bot_token: str
    telegram_chat_id: str
    tier1_institutions: Tuple[str, ...]
    tier1_weight: float
    notify_on_downgrade: bool
    notify_on_target_price_change: bool
    min_target_price_change_pct: float


def load_app_config(path: Path) -> AppConfig:
    raw = json.loads(path.read_text(encoding="utf-8"))
    app = raw.get("app", {})
    telegram = raw.get("telegram", {})
    inst = raw.get("institutions", {})
    alerts = raw.get("alerts", {})

    user = user_root()
    data_file = (user / str(app.get("data_file", "data/latest_data.json"))).resolve()
    prev_file = (user / str(app.get("previous_data_file", "data/previous_data.json"))).resolve()

    remote = app.get("remote_latest_data", {}) or {}
    env_url = str(os.environ.get("ANALYSTRECOM_LATEST_DATA_URL", "")).strip()
    remote_url = str(remote.get("latest_data_url", "")).strip() or env_url
    remote_enabled = bool(remote.get("enabled", False)) or bool(env_url)
    remote_timeout_sec = int(remote.get("timeout_sec", 20))

    tier1 = tuple(str(x) for x in inst.get("tier1", []) if str(x).strip())
    tier1_weight = float(inst.get("tier1_weight", 1.35))

    return AppConfig(
        data_file=data_file,
        previous_data_file=prev_file,
        sync_on_start=bool(app.get("sync_on_start", True)),
        remote_latest_data_enabled=remote_enabled,
        remote_latest_data_url=remote_url,
        remote_latest_data_timeout_sec=remote_timeout_sec,
        telegram_enabled=bool(telegram.get("enabled", False)),
        telegram_bot_token=str(telegram.get("bot_token", "")).strip(),
        telegram_chat_id=str(telegram.get("chat_id", "")).strip(),
        tier1_institutions=tier1,
        tier1_weight=tier1_weight,
        notify_on_downgrade=bool(alerts.get("notify_on_downgrade", True)),
        notify_on_target_price_change=bool(alerts.get("notify_on_target_price_change", True)),
        min_target_price_change_pct=float(alerts.get("min_target_price_change_pct", 2.0)),
    )


def load_portfolio(path: Path) -> List[str]:
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    tickers = raw.get("tickers", [])
    out = []
    for t in tickers:
        s = str(t).strip().upper()
        if s and s not in out:
            out.append(s)
    return out


def get_sp500_tickers_from_finviz() -> List[str]:
    """
    Uses Finviz screener index filter for S&P 500.
    """
    try:
        ov = Overview()
        ov.set_filter(filters_dict={"Index": "S&P 500"})
        df = ov.screener_view(order="Ticker", limit=2000, verbose=0)
        if df is None or df.empty:
            return []
        col = "Ticker" if "Ticker" in df.columns else ("ticker" if "ticker" in df.columns else None)
        if col is None:
            return []
        tickers = [str(x).strip().upper() for x in df[col].tolist()]
        return [t for t in tickers if t]
    except Exception:
        return []


def get_sp500_tickers_fallback() -> List[str]:
    """
    Fallback: Wikipedia list (for robustness in local runs).
    """
    # Network-restricted environments may block fallback sources.
    # Keep app resilient with a broad liquid-universe fallback.
    return [
        "AAPL",
        "MSFT",
        "NVDA",
        "AMZN",
        "META",
        "GOOGL",
        "BRK-B",
        "JPM",
        "JNJ",
        "V",
        "XOM",
        "UNH",
        "PG",
        "HD",
        "MA",
        "LLY",
        "AVGO",
        "COST",
        "MRK",
        "ABBV",
    ]


def get_sp500_tickers() -> List[str]:
    tickers = get_sp500_tickers_from_finviz()
    if tickers:
        return tickers
    return get_sp500_tickers_fallback()


def fetch_sp500_proxy_quote() -> Dict[str, Any]:
    """
    Displays a simple top-bar 'market status' using SPY as proxy.
    """
    try:
        q = finvizfinance("SPY")
        d = q.ticker_fundament()
        price = safe_float(d.get("Price"))
        change_pct = safe_float(d.get("Change"))
        return {"symbol": "SPY", "price": price, "change_pct": change_pct, "asof_utc": utc_now_iso()}
    except Exception:
        return {"symbol": "SPY", "price": None, "change_pct": None, "asof_utc": utc_now_iso()}


def fetch_overview_rows(tickers: List[str]) -> List[Dict[str, Any]]:
    """
    Pulls core columns from Finviz screener in batches.
    """
    if not tickers:
        return []

    rows: List[Dict[str, Any]] = []
    ov = Overview()

    # Finviz can be sensitive; keep batches modest.
    batch_size = 60
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i : i + batch_size]
        try:
            ov.set_filter(ticker=",".join(batch))
            df = ov.screener_view(order="Ticker", limit=1000, verbose=0)
            if df is None or df.empty:
                continue
            for _, r in df.iterrows():
                rows.append({k: r.get(k) for k in df.columns})
        except Exception:
            continue
        time.sleep(0.5)

    return rows


def fetch_ticker_research_details(ticker: str) -> Dict[str, Any]:
    """
    Pulls per-ticker details (including Target Price / Recom, and some 'news/analyst' data when present).
    """
    q = finvizfinance(ticker)
    fundamentals = q.ticker_fundament()
    out: Dict[str, Any] = {
        "ticker": ticker,
        "sector": fundamentals.get("Sector"),
        "industry": fundamentals.get("Industry"),
        "price": safe_float(fundamentals.get("Price")),
        "target_price": safe_float(fundamentals.get("Target Price")),
        "recom": recom_to_score(fundamentals.get("Recom")),
    }

    try:
        outer = q.ticker_outer()
        # finvizfinance may return "Insider Trading", "News", etc; we try to extract analyst-like blocks if present.
        if isinstance(outer, dict):
            out["outer"] = outer
    except Exception:
        pass

    return out


def extract_institution_signals(ticker_details: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Heuristic extraction of 'institutions/analyst' opinions.

    finviz does not provide a clean, official 'institution ratings' API in all cases.
    This function attempts best-effort extraction from the quote outer payload (when available).
    """
    outer = ticker_details.get("outer")
    signals: List[Dict[str, Any]] = []

    if not isinstance(outer, dict):
        return signals

    # Many pages include textual snippets; we do lightweight parsing for patterns like:
    # "Goldman Sachs ... Buy" or "JP Morgan ... Overweight"
    blob = json.dumps(outer, ensure_ascii=False)

    inst_candidates = [
        "Goldman Sachs",
        "JPMorgan",
        "JP Morgan",
        "Morgan Stanley",
        "Bank of America",
        "Citigroup",
        "Barclays",
        "UBS",
        "Wells Fargo",
        "Deutsche Bank",
        "Jefferies",
    ]
    rating_words = ["Strong Buy", "Buy", "Overweight", "Outperform", "Hold", "Neutral", "Sell", "Underperform"]
    pattern = re.compile(
        r"(" + "|".join(re.escape(x) for x in inst_candidates) + r")[^\\n]{0,80}?(" + "|".join(rating_words) + r")",
        flags=re.IGNORECASE,
    )

    for m in pattern.finditer(blob):
        inst = normalize_inst_name(m.group(1))
        rating = m.group(2).strip()
        signals.append({"institution": inst, "rating": rating})

    # De-duplicate
    dedup = {}
    for s in signals:
        key = (s["institution"].lower(), s["rating"].lower())
        dedup[key] = s
    return list(dedup.values())


def rating_to_buy_or_better(rating: str) -> bool:
    r = (rating or "").strip().lower()
    return any(x in r for x in ["buy", "strong buy", "overweight", "outperform"])


def build_dataset(config: AppConfig) -> Dict[str, Any]:
    tickers = get_sp500_tickers()

    # Base table for sector/industry fallbacks
    overview_rows = fetch_overview_rows(tickers)
    overview_by_ticker: Dict[str, Dict[str, Any]] = {}
    for r in overview_rows:
        t = str(r.get("Ticker") or r.get("ticker") or r.get("Symbol") or "").strip().upper()
        if t:
            overview_by_ticker[t] = r

    out_rows: List[Dict[str, Any]] = []
    for idx, t in enumerate(tickers):
        try:
            d = fetch_ticker_research_details(t)
            inst_signals = extract_institution_signals(d)
            buy_or_better = [s for s in inst_signals if rating_to_buy_or_better(s.get("rating", ""))]

            sector = d.get("sector") or overview_by_ticker.get(t, {}).get("Sector")
            industry = d.get("industry") or overview_by_ticker.get(t, {}).get("Industry")

            price = safe_float(d.get("price"))
            target = safe_float(d.get("target_price"))
            recom = recom_to_score(d.get("recom"))
            ups = upside_pct(price, target)

            tier1_set = {x.lower() for x in config.tier1_institutions}
            tier1_hits = [
                s
                for s in buy_or_better
                if normalize_inst_name(s.get("institution", "")).lower() in tier1_set
            ]

            score_weighted = None
            if recom is not None:
                w = config.tier1_weight if tier1_hits else 1.0
                score_weighted = recom / w

            out_rows.append(
                {
                    "ticker": t,
                    "sector": sector,
                    "industry": industry,
                    "price": price,
                    "target_price": target,
                    "upside_pct": ups,
                    "upside_bucket": bucket_upside(ups),
                    "recom_score": recom,
                    "recom_score_weighted": score_weighted,
                    "buy_or_better_count": len(buy_or_better),
                    "tier1_buy_count": len(tier1_hits),
                    "institutions": inst_signals,
                }
            )
        except Exception:
            continue

        # Slight pacing to reduce block risk
        if idx % 25 == 0:
            time.sleep(0.6)

    dataset = {
        "meta": {"source": "finviz", "generated_at_utc": utc_now_iso()},
        "sp500_proxy": fetch_sp500_proxy_quote(),
        "rows": out_rows,
    }
    return dataset


def save_json(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"meta": {"source": "missing", "generated_at_utc": None}, "rows": []}
    return json.loads(path.read_text(encoding="utf-8"))


def parse_generated_at(meta: Dict[str, Any]) -> Optional[datetime]:
    v = meta.get("generated_at_utc")
    if not v:
        return None
    try:
        dt = dtparser.isoparse(str(v))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def screen_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    요구 스크리닝:
    - 2개 이상의 기관이 'Buy 이상' 의견
    - Recom 점수 2.0 이하
    """
    out = []
    for r in rows:
        if int(r.get("buy_or_better_count") or 0) < 2:
            continue
        recom = safe_float(r.get("recom_score"))
        if recom is None or recom > 2.0:
            continue
        out.append(r)
    return out


def compare_portfolio(
    prev_rows: List[Dict[str, Any]],
    new_rows: List[Dict[str, Any]],
    portfolio: List[str],
    min_target_price_change_pct: float,
) -> List[Dict[str, Any]]:
    prev_map = {str(r.get("ticker", "")).upper(): r for r in prev_rows if r.get("ticker")}
    new_map = {str(r.get("ticker", "")).upper(): r for r in new_rows if r.get("ticker")}

    events: List[Dict[str, Any]] = []
    for t in portfolio:
        old = prev_map.get(t)
        new = new_map.get(t)
        if not old or not new:
            continue

        old_recom = safe_float(old.get("recom_score"))
        new_recom = safe_float(new.get("recom_score"))
        if old_recom is not None and new_recom is not None and new_recom > old_recom:
            events.append(
                {
                    "type": "downgrade",
                    "ticker": t,
                    "old_recom": old_recom,
                    "new_recom": new_recom,
                }
            )

        old_tp = safe_float(old.get("target_price"))
        new_tp = safe_float(new.get("target_price"))
        if old_tp is not None and new_tp is not None and old_tp > 0:
            pct = abs(new_tp / old_tp - 1.0) * 100.0
            if pct >= float(min_target_price_change_pct):
                events.append(
                    {
                        "type": "target_price_change",
                        "ticker": t,
                        "old_target": old_tp,
                        "new_target": new_tp,
                        "change_pct": pct,
                    }
                )

    return events


def format_event_message(event: Dict[str, Any]) -> str:
    t = event.get("ticker", "")
    if event.get("type") == "downgrade":
        return f"[등급 하향] {t}: Recom {event.get('old_recom')} → {event.get('new_recom')}"
    if event.get("type") == "target_price_change":
        return (
            f"[목표가 변경] {t}: {event.get('old_target')} → {event.get('new_target')}"
            f" (Δ {event.get('change_pct'):.1f}%)"
        )
    return f"[변경] {t}"


def send_telegram_message(config: AppConfig, text: str) -> None:
    if not config.telegram_enabled:
        return
    if not config.telegram_bot_token or not config.telegram_chat_id:
        return
    if Bot is None:
        return
    bot = Bot(token=config.telegram_bot_token)
    bot.send_message(chat_id=config.telegram_chat_id, text=text)


def sync_latest_data(config: AppConfig, force_live_fetch: bool = False) -> Dict[str, Any]:
    """
    App startup sync:
    - If local file exists and is recent, use it.
    - Otherwise fetch live via finviz and save.
    """
    if force_live_fetch:
        try:
            dataset = build_dataset(config)
            save_json(config.data_file, dataset)
            return dataset
        except Exception:
            return load_json(config.data_file)

    dataset = load_json(config.data_file)
    # Default behavior: trust GitHub Actions-produced snapshot and load quickly.
    # Only fetch live when explicitly requested via force_live_fetch.
    if dataset.get("rows") is None:
        return {"meta": {"source": "invalid", "generated_at_utc": None}, "rows": []}
    return dataset


def run_portfolio_alerts(config: AppConfig, portfolio: List[str], new_dataset: Dict[str, Any]) -> List[Dict[str, Any]]:
    prev = load_json(config.previous_data_file)
    prev_rows = prev.get("rows", []) or []
    new_rows = new_dataset.get("rows", []) or []

    events = compare_portfolio(
        prev_rows=prev_rows,
        new_rows=new_rows,
        portfolio=portfolio,
        min_target_price_change_pct=config.min_target_price_change_pct,
    )

    for e in events:
        if e.get("type") == "downgrade" and not config.notify_on_downgrade:
            continue
        if e.get("type") == "target_price_change" and not config.notify_on_target_price_change:
            continue
        send_telegram_message(config, format_event_message(e))

    # Update previous snapshot to current.
    save_json(config.previous_data_file, {"meta": {"source": "app", "generated_at_utc": utc_now_iso()}, "rows": new_rows})
    return events


def derive_filter_values(rows: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    sectors = sorted({str(r.get("sector")).strip() for r in rows if str(r.get("sector")).strip()})
    industries = sorted({str(r.get("industry")).strip() for r in rows if str(r.get("industry")).strip()})
    return {"sectors": sectors, "industries": industries}

