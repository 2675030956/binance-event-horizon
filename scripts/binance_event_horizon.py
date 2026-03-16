from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import requests


SPOT_PRODUCTS_URL = "https://www.binance.com/bapi/asset/v2/public/asset-service/product/get-products"
SPOT_PRODUCT_BY_SYMBOL_URL = "https://www.binance.com/bapi/asset/v2/public/asset-service/product/get-product-by-symbol"
FUTURES_TICKER_24H_URLS = [
    "https://www.binance.com/fapi/v1/ticker/24hr",
    "https://fapi.binance.com/fapi/v1/ticker/24hr",
]
FUTURES_PREMIUM_INDEX_URLS = [
    "https://www.binance.com/fapi/v1/premiumIndex",
    "https://fapi.binance.com/fapi/v1/premiumIndex",
]
FUTURES_OPEN_INTEREST_HIST_URLS = [
    "https://www.binance.com/futures/data/openInterestHist",
    "https://fapi.binance.com/futures/data/openInterestHist",
]
ALPHA_TOKEN_LIST_URL = "https://www.binance.com/bapi/defi/v1/public/wallet-direct/buw/wallet/cex/alpha/all/token/list"
SOCIAL_HYPE_URL = "https://web3.binance.com/bapi/defi/v1/public/wallet-direct/buw/wallet/market/token/pulse/social/hype/rank/leaderboard"
UNIFIED_RANK_URL = "https://web3.binance.com/bapi/defi/v1/public/wallet-direct/buw/wallet/market/token/pulse/unified/rank/list"
SMART_MONEY_INFLOW_URL = "https://web3.binance.com/bapi/defi/v1/public/wallet-direct/tracker/wallet/token/inflow/rank/query"
SMART_SIGNAL_URL = "https://web3.binance.com/bapi/defi/v1/public/wallet-direct/buw/wallet/web/signal/smart-money"
TOKEN_AUDIT_URL = "https://web3.binance.com/bapi/defi/v1/public/wallet-direct/security/token/audit"
CMS_ARTICLE_LIST_URL = "https://www.binance.com/bapi/composite/v1/public/cms/article/list/query"
CMS_ARTICLE_DETAIL_URL = "https://www.binance.com/bapi/composite/v1/public/cms/article/detail/query"

QUOTE_SUFFIXES = ["USDT", "FDUSD", "USDC", "BUSD", "BTC", "ETH"]
CHAIN_NAMES = {"56": "BSC", "8453": "Base", "CT_501": "Solana", "1": "Ethereum"}
CATALYST_LANE_RULES = [
    ("上市点火", [" will list ", " launchpool ", " hodler airdrop", "seed tag", "上线", "list "]),
    ("合约扩张", [" futures will launch ", " perpetual contract", "永续合约", "usdⓈ-margined", "usd-margined"]),
    ("服务扩展", [" margin ", " earn", " convert", "buy crypto", "vip loan", "dual investment"]),
    ("活动驱动", [" activity", "campaign", "promo", "活动", "yield arena", "奖励"]),
    ("基础设施", [" api ", " stp ", "portfolio margin", "referral", "系统", "spot api update"]),
]

DEFAULT_CONFIG: Dict[str, Any] = {
    "chains": ["56", "8453", "CT_501"],
    "social_limit_per_chain": 8,
    "unified_rank_types": [20],
    "unified_limit_per_chain": 8,
    "smart_signal_limit_per_chain": 8,
    "smart_money_limit_per_chain": 6,
    "alpha_limit": 16,
    "spot_limit": 120,
    "spot_min_quote_volume": 5000000,
    "futures_limit": 120,
    "futures_min_quote_volume": 10000000,
    "futures_probe_limit": 8,
    "announcement_catalog_ids": [48, 49, 93],
    "announcement_limit_per_catalog": 3,
    "history_dir": "output/history",
    "history_keep_files": 72,
    "request_timeout_seconds": 20,
    "request_interval_seconds": 0.08,
    "auto_refresh_seconds": 180,
    "alert_thresholds": {
        "high_funding_bps": 3.5,
        "high_oi_change_pct": 1.5,
        "low_liquidity_usd": 120000,
        "hyper_move_pct": 20.0,
    },
}


def ensure_utf8_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")


def to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip().replace(",", "").replace("%", "")
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None
    return None


def to_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        text = value.strip().replace(",", "")
        if not text:
            return None
        try:
            return int(float(text))
        except ValueError:
            return None
    return None


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def safe_log10(value: Any) -> float:
    number = to_float(value) or 0.0
    return math.log10(max(number, 1.0))


def utc_iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ts_to_iso(timestamp_ms: Any) -> Optional[str]:
    value = to_int(timestamp_ms)
    if value is None or value <= 0:
        return None
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc).isoformat()


def iso_to_datetime(value: Any) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def hours_between(start: Optional[datetime], end: Optional[datetime]) -> Optional[float]:
    if not start or not end:
        return None
    return abs((end - start).total_seconds()) / 3600.0


def merge_dicts(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_dicts(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    raw = path.read_text(encoding="utf-8").lstrip("\ufeff")
    if not raw.strip():
        return default
    return json.loads(raw)


def save_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def save_json(path: Path, payload: Any) -> None:
    save_text(path, json.dumps(payload, ensure_ascii=False, indent=2))


def load_report_if_exists(path: Optional[Path]) -> Optional[Dict[str, Any]]:
    if not path or not path.exists():
        return None
    try:
        payload = load_json(path, None)
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def relative_web_path(from_file: Path, to_file: Path) -> str:
    try:
        relative = os.path.relpath(str(to_file), str(from_file.parent))
    except Exception:
        relative = to_file.name
    return relative.replace("\\", "/")


def normalize_symbol(value: Any) -> str:
    text = str(value or "").strip().upper()
    return "".join(char for char in text if char.isalnum())


def normalize_text_key(value: Any) -> str:
    text = str(value or "").strip().lower()
    return "".join(char for char in text if char.isalnum() or "\u4e00" <= char <= "\u9fff")


def normalize_market_symbol(value: Any) -> str:
    text = normalize_symbol(str(value or "").replace("/", "").replace("-", ""))
    if not text:
        return ""
    if any(text.endswith(suffix) for suffix in QUOTE_SUFFIXES):
        return text
    return f"{text}USDT"


def base_from_market_symbol(symbol: Any) -> str:
    text = normalize_symbol(symbol)
    for suffix in QUOTE_SUFFIXES:
        if text.endswith(suffix) and len(text) > len(suffix):
            return text[: -len(suffix)]
    return text


def dedupe_list(items: Iterable[Any]) -> List[Any]:
    seen = set()
    output: List[Any] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        output.append(item)
    return output


def min_max_scale(values: Iterable[Optional[float]], value: Optional[float]) -> float:
    filtered = [number for number in values if number is not None]
    if value is None or not filtered:
        return 0.0
    low = min(filtered)
    high = max(filtered)
    if math.isclose(low, high):
        return 50.0 if value > 0 else 0.0
    return clamp((value - low) / (high - low) * 100.0, 0.0, 100.0)


def clip_text(value: Any, max_chars: int = 180) -> str:
    text = str(value or "").strip()
    compact = " ".join(text.split())
    if len(compact) <= max_chars:
        return compact
    return f"{compact[: max_chars - 1].rstrip()}…"


def score_band(score: Any) -> str:
    number = to_float(score) or 0.0
    if number >= 75:
        return "Prime"
    if number >= 58:
        return "Watch"
    if number >= 38:
        return "Spec"
    return "Shadow"


def severity_label(score: Any) -> str:
    number = to_float(score) or 0.0
    if number >= 82:
        return "Critical"
    if number >= 62:
        return "High"
    if number >= 42:
        return "Medium"
    return "Low"


def extract_text_segments(node: Any) -> List[str]:
    if isinstance(node, dict):
        if node.get("node") == "text":
            text = str(node.get("text") or "").strip()
            return [text] if text else []
        output: List[str] = []
        for child in node.get("child") or []:
            output.extend(extract_text_segments(child))
        return output
    if isinstance(node, list):
        output: List[str] = []
        for child in node:
            output.extend(extract_text_segments(child))
        return output
    return []


def body_json_to_summary(raw_body: Any, max_chars: int = 220) -> str:
    if not raw_body:
        return ""
    try:
        payload = json.loads(raw_body) if isinstance(raw_body, str) else raw_body
    except json.JSONDecodeError:
        return clip_text(raw_body, max_chars=max_chars)
    text = " ".join(segment for segment in extract_text_segments(payload) if segment)
    return clip_text(" ".join(text.split()), max_chars=max_chars)


def pct_from_open_close(open_price: Any, close_price: Any) -> Optional[float]:
    start = to_float(open_price)
    end = to_float(close_price)
    if start is None or end is None or math.isclose(start, 0.0):
        return None
    return (end - start) / start * 100.0


def tag_names_from_map(tag_map: Any) -> List[str]:
    output: List[str] = []
    if not isinstance(tag_map, dict):
        return output
    for group, items in tag_map.items():
        if group:
            output.append(str(group))
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict) and item.get("tagName"):
                    output.append(str(item.get("tagName")))
    return dedupe_list(output)


def extract_symbols_from_title(title: Any) -> List[str]:
    text = str(title or "")
    matches = re.findall(r"\(([A-Z0-9]{2,12})\)", text)
    blacklist = {"BINANCE", "USD", "USDT", "API", "STP", "APR"}
    return dedupe_list([match for match in matches if match not in blacklist])


def announcement_lane(title: Any) -> str:
    text = f" {str(title or '').lower()} "
    for label, keys in CATALYST_LANE_RULES:
        for key in keys:
            if key in text:
                return label
    return "系统催化"


def extract_pair_symbols(pairs: Any) -> List[str]:
    output: List[str] = []
    if not isinstance(pairs, list):
        return output
    for item in pairs:
        if isinstance(item, str):
            symbol = normalize_symbol(item)
            if 2 <= len(symbol) <= 12:
                output.append(base_from_market_symbol(symbol))
        elif isinstance(item, dict):
            for key in ["asset", "baseAsset", "spotAsset", "symbol"]:
                raw = item.get(key)
                symbol = normalize_symbol(raw)
                if not symbol:
                    continue
                if key == "symbol":
                    symbol = base_from_market_symbol(symbol)
                if 2 <= len(symbol) <= 12:
                    output.append(symbol)
    return dedupe_list(output)


def safe_first(items: Iterable[Any]) -> Any:
    for item in items:
        if item is not None:
            return item
    return None


class BinanceEventHorizonClient:
    def __init__(self, timeout_seconds: int, interval_seconds: float) -> None:
        self.timeout_seconds = timeout_seconds
        self.interval_seconds = interval_seconds
        self.session = requests.Session()
        self.session.headers.update({"Accept-Encoding": "identity", "User-Agent": "Mozilla/5.0 EventHorizon/1.0"})

    def _sleep(self) -> None:
        if self.interval_seconds > 0:
            time.sleep(self.interval_seconds)

    def _request_json(
        self,
        method: str,
        url: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        body: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Any:
        response = self.session.request(method=method, url=url, params=params, json=body, headers=headers, timeout=self.timeout_seconds)
        response.raise_for_status()
        self._sleep()
        payload = json.loads(response.content.decode("utf-8", errors="replace"))
        if isinstance(payload, dict):
            code = str(payload.get("code", ""))
            if code and code != "000000":
                raise RuntimeError(f"request failed code={code} url={url}")
            if payload.get("success") is False:
                raise RuntimeError(f"request failed success=false url={url}")
        return payload

    def _request_json_with_fallback(
        self,
        method: str,
        urls: List[str],
        *,
        params: Optional[Dict[str, Any]] = None,
        body: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Any:
        errors: List[str] = []
        for url in urls:
            try:
                return self._request_json(method, url, params=params, body=body, headers=headers)
            except Exception as exc:
                errors.append(f"{url} -> {exc}")
        raise RuntimeError("all fallback endpoints failed: " + " | ".join(errors))

    def get_spot_products(self) -> List[Dict[str, Any]]:
        payload = self._request_json("GET", SPOT_PRODUCTS_URL, params={"includeEtf": "true"})
        return payload.get("data") or []

    def get_spot_product_by_symbol(self, symbol: str) -> Dict[str, Any]:
        payload = self._request_json("GET", SPOT_PRODUCT_BY_SYMBOL_URL, params={"symbol": symbol})
        return payload.get("data") or {}

    def get_futures_tickers(self) -> List[Dict[str, Any]]:
        payload = self._request_json_with_fallback("GET", FUTURES_TICKER_24H_URLS)
        return payload if isinstance(payload, list) else []

    def get_futures_premium_index(self) -> List[Dict[str, Any]]:
        payload = self._request_json_with_fallback("GET", FUTURES_PREMIUM_INDEX_URLS)
        return payload if isinstance(payload, list) else []

    def get_open_interest_hist(self, symbol: str, limit: int = 2) -> List[Dict[str, Any]]:
        payload = self._request_json_with_fallback(
            "GET",
            FUTURES_OPEN_INTEREST_HIST_URLS,
            params={"symbol": symbol, "period": "5m", "limit": limit},
        )
        return payload if isinstance(payload, list) else []

    def get_social_hype(self, chain_id: str) -> List[Dict[str, Any]]:
        payload = self._request_json(
            "GET",
            SOCIAL_HYPE_URL,
            params={"chainId": chain_id, "sentiment": "All", "socialLanguage": "ALL", "targetLanguage": "en", "timeRange": 1},
            headers={"User-Agent": "binance-web3/2.0 (Skill)"},
        )
        return (payload.get("data") or {}).get("leaderBoardList") or []

    def get_unified_rank(self, chain_id: str, rank_type: int, size: int) -> List[Dict[str, Any]]:
        payload = self._request_json(
            "POST",
            UNIFIED_RANK_URL,
            body={"rankType": rank_type, "chainId": chain_id, "period": 50, "sortBy": 0, "orderAsc": False, "page": 1, "size": size},
            headers={"Content-Type": "application/json", "User-Agent": "binance-web3/2.0 (Skill)"},
        )
        return (payload.get("data") or {}).get("tokens") or []

    def get_smart_money_inflow(self, chain_id: str) -> List[Dict[str, Any]]:
        payload = self._request_json(
            "POST",
            SMART_MONEY_INFLOW_URL,
            body={"chainId": chain_id, "period": "24h", "tagType": 2},
            headers={"Content-Type": "application/json", "User-Agent": "binance-web3/2.0 (Skill)"},
        )
        return payload.get("data") or []

    def get_smart_signals(self, chain_id: str, page_size: int) -> List[Dict[str, Any]]:
        payload = self._request_json(
            "POST",
            SMART_SIGNAL_URL,
            body={"smartSignalType": "", "page": 1, "pageSize": page_size, "chainId": chain_id},
            headers={"Content-Type": "application/json", "User-Agent": "binance-web3/1.0 (Skill)"},
        )
        return payload.get("data") or []

    def get_alpha_tokens(self) -> List[Dict[str, Any]]:
        payload = self._request_json("GET", ALPHA_TOKEN_LIST_URL)
        return payload.get("data") or []

    def get_announcement_catalogs(self, page_size: int = 50) -> List[Dict[str, Any]]:
        payload = self._request_json(
            "GET",
            CMS_ARTICLE_LIST_URL,
            params={"type": 1, "pageNo": 1, "pageSize": page_size},
            headers={"User-Agent": "Mozilla/5.0", "Accept-Encoding": "identity"},
        )
        return (payload.get("data") or {}).get("catalogs") or []

    def get_announcement_detail(self, article_code: str) -> Dict[str, Any]:
        payload = self._request_json(
            "GET",
            CMS_ARTICLE_DETAIL_URL,
            params={"articleCode": article_code},
            headers={"User-Agent": "Mozilla/5.0", "Accept-Encoding": "identity"},
        )
        return payload.get("data") or {}

    def audit_token(self, chain_id: str, contract_address: str) -> Dict[str, Any]:
        payload = self._request_json(
            "POST",
            TOKEN_AUDIT_URL,
            body={"binanceChainId": chain_id, "contractAddress": contract_address, "requestId": str(uuid.uuid4())},
            headers={"Content-Type": "application/json", "User-Agent": "binance-web3/1.4 (Skill)", "source": "agent"},
        )
        return payload.get("data") or {}


class EventHorizonBuilder:
    def __init__(
        self,
        config: Dict[str, Any],
        *,
        previous_report: Optional[Dict[str, Any]] = None,
        history_reports: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        self.config = config
        self.client = BinanceEventHorizonClient(
            timeout_seconds=to_int(config.get("request_timeout_seconds")) or 20,
            interval_seconds=to_float(config.get("request_interval_seconds")) or 0.0,
        )
        self.generated_at_dt = datetime.now(timezone.utc)
        self.generated_at = self.generated_at_dt.isoformat()
        self.previous_report = previous_report or {}
        self.history_reports = [item for item in (history_reports or []) if isinstance(item, dict)]
        self.previous_asset_index = self.index_assets(self.previous_report.get("asset_matrix") or [])
        self.warnings: List[str] = []
        self.audit_cache: Dict[tuple[str, str], Dict[str, Any]] = {}
        self.cex_base_symbols: set[str] = set()
        self.alpha_symbols: set[str] = set()

    def index_assets(self, items: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        output: Dict[str, Dict[str, Any]] = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key") or item.get("symbol") or "")
            if key:
                output[key] = item
        return output

    def safe_call(self, label: str, func: Any, *args: Any, fallback: Any = None, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            self.warnings.append(f"{label}: {exc}")
            return fallback

    def build(self, focus_symbol: Optional[str] = None) -> Dict[str, Any]:
        context = self.collect_context(focus_symbol)
        assets = self.build_asset_matrix(context)
        catalysts = self.build_catalyst_reactor(context, assets)
        self.apply_catalyst_placeholders(assets, catalysts)
        self.apply_catalysts_to_assets(assets, catalysts)
        self.apply_focus_audit(assets, focus_symbol)
        asset_matrix = self.finalize_asset_scores(assets)
        temporal_shift = self.build_temporal_shift(asset_matrix)
        signal_constellation = self.build_signal_constellation(asset_matrix, context, catalysts)
        gravity_alerts = self.build_gravity_alerts(asset_matrix, context)
        market_phase = self.build_market_phase(asset_matrix, signal_constellation, catalysts, gravity_alerts, temporal_shift)
        scenarios = self.build_scenarios(asset_matrix, catalysts, gravity_alerts)
        orbit_watchlist = self.build_orbit_watchlist(asset_matrix)
        focus_asset = self.build_focus_asset(focus_symbol, asset_matrix, context)
        live_brief = self.build_live_brief(market_phase, signal_constellation, scenarios, gravity_alerts, orbit_watchlist, focus_asset)
        broadcast_pack = self.build_broadcast_pack(market_phase, signal_constellation, scenarios, gravity_alerts, orbit_watchlist, focus_asset, live_brief)

        return {
            "skill": "binance-event-horizon",
            "generated_at": self.generated_at,
            "meta": {
                "focus_symbol": focus_symbol or "",
                "chains": self.config.get("chains") or [],
                "auto_refresh_seconds": to_int(self.config.get("auto_refresh_seconds")) or 180,
                "source_digest": context.get("source_digest") or {},
                "warnings_count": len(self.warnings),
            },
            "market_phase": market_phase,
            "temporal_shift": temporal_shift,
            "signal_constellation": signal_constellation,
            "scenario_engine": scenarios,
            "catalyst_reactor": catalysts,
            "gravity_alerts": gravity_alerts,
            "orbit_watchlist": orbit_watchlist,
            "focus_asset": focus_asset,
            "live_brief": live_brief,
            "broadcast_pack": broadcast_pack,
            "asset_matrix": asset_matrix[:18],
            "warnings": self.warnings,
        }

    def collect_context(self, focus_symbol: Optional[str]) -> Dict[str, Any]:
        spot_products = self.safe_call("spot_products", self.client.get_spot_products, fallback=[])
        spot_min_quote_volume = to_float(self.config.get("spot_min_quote_volume")) or 0.0
        filtered_spot_products = [
            item
            for item in spot_products
            if (item.get("st") == "TRADING")
            and str(item.get("q") or "").upper() == "USDT"
            and (to_float(item.get("qv")) or 0.0) >= spot_min_quote_volume
        ]
        filtered_spot_products.sort(key=lambda item: to_float(item.get("qv")) or 0.0, reverse=True)
        filtered_spot_products = filtered_spot_products[: (to_int(self.config.get("spot_limit")) or 120)]

        futures_tickers = self.safe_call("futures_tickers", self.client.get_futures_tickers, fallback=[])
        futures_min_quote_volume = to_float(self.config.get("futures_min_quote_volume")) or 0.0
        filtered_futures_tickers = [
            item
            for item in futures_tickers
            if str(item.get("symbol") or "").endswith("USDT") and (to_float(item.get("quoteVolume")) or 0.0) >= futures_min_quote_volume
        ]
        filtered_futures_tickers.sort(
            key=lambda item: ((to_float(item.get("quoteVolume")) or 0.0) * max(abs(to_float(item.get("priceChangePercent")) or 0.0), 1.0)),
            reverse=True,
        )
        filtered_futures_tickers = filtered_futures_tickers[: (to_int(self.config.get("futures_limit")) or 120)]

        self.cex_base_symbols = {normalize_symbol(item.get("b")) for item in filtered_spot_products if normalize_symbol(item.get("b"))}
        self.cex_base_symbols.update(base_from_market_symbol(item.get("symbol")) for item in filtered_futures_tickers if base_from_market_symbol(item.get("symbol")))

        premium_index = self.safe_call("futures_premium_index", self.client.get_futures_premium_index, fallback=[])
        premium_index_map = {str(item.get("symbol") or ""): item for item in premium_index if isinstance(item, dict)}

        alpha_tokens = self.safe_call("alpha_tokens", self.client.get_alpha_tokens, fallback=[])
        alpha_tokens.sort(
            key=lambda item: ((to_float(item.get("volume24h")) or 0.0), (to_int(item.get("listingTime")) or 0)),
            reverse=True,
        )
        alpha_tokens = alpha_tokens[: (to_int(self.config.get("alpha_limit")) or 16)]
        self.alpha_symbols = {normalize_symbol(item.get("symbol")) for item in alpha_tokens if normalize_symbol(item.get("symbol"))}

        social_by_chain: Dict[str, List[Dict[str, Any]]] = {}
        unified_by_chain: Dict[str, List[Dict[str, Any]]] = {}
        signals_by_chain: Dict[str, List[Dict[str, Any]]] = {}
        inflow_by_chain: Dict[str, List[Dict[str, Any]]] = {}

        for chain_id in self.config.get("chains") or []:
            social_items = self.safe_call(f"social_hype:{chain_id}", self.client.get_social_hype, chain_id, fallback=[])
            social_by_chain[chain_id] = social_items[: (to_int(self.config.get("social_limit_per_chain")) or 8)]

            unified_items: List[Dict[str, Any]] = []
            for rank_type in self.config.get("unified_rank_types") or [20]:
                unified_items.extend(
                    self.safe_call(
                        f"unified_rank:{chain_id}:{rank_type}",
                        self.client.get_unified_rank,
                        chain_id,
                        to_int(rank_type) or 20,
                        to_int(self.config.get("unified_limit_per_chain")) or 8,
                        fallback=[],
                    )
                )
            unified_by_chain[chain_id] = unified_items[: (to_int(self.config.get("unified_limit_per_chain")) or 8)]

            signals_by_chain[chain_id] = self.safe_call(
                f"smart_signals:{chain_id}",
                self.client.get_smart_signals,
                chain_id,
                to_int(self.config.get("smart_signal_limit_per_chain")) or 8,
                fallback=[],
            )
            inflow_by_chain[chain_id] = self.safe_call(
                f"smart_money_inflow:{chain_id}",
                self.client.get_smart_money_inflow,
                chain_id,
                fallback=[],
            )[: (to_int(self.config.get("smart_money_limit_per_chain")) or 6)]

        announcement_items = self.collect_announcements()
        open_interest_map = self.collect_open_interest_map(filtered_futures_tickers, focus_symbol)

        focus_spot_product: Dict[str, Any] = {}
        normalized_focus_market_symbol = normalize_market_symbol(focus_symbol)
        if normalized_focus_market_symbol:
            focus_spot_product = self.safe_call(
                f"spot_product_by_symbol:{normalized_focus_market_symbol}",
                self.client.get_spot_product_by_symbol,
                normalized_focus_market_symbol,
                fallback={},
            )

        source_digest = {
            "spot_pairs": len(filtered_spot_products),
            "futures_pairs": len(filtered_futures_tickers),
            "alpha_tokens": len(alpha_tokens),
            "social_hype_items": sum(len(items) for items in social_by_chain.values()),
            "unified_rank_items": sum(len(items) for items in unified_by_chain.values()),
            "smart_signal_items": sum(len(items) for items in signals_by_chain.values()),
            "smart_money_items": sum(len(items) for items in inflow_by_chain.values()),
            "official_announcements": len(announcement_items),
            "oi_probed_symbols": len(open_interest_map),
        }

        return {
            "spot_products": filtered_spot_products,
            "futures_tickers": filtered_futures_tickers,
            "premium_index_map": premium_index_map,
            "open_interest_map": open_interest_map,
            "alpha_tokens": alpha_tokens,
            "social_by_chain": social_by_chain,
            "unified_by_chain": unified_by_chain,
            "signals_by_chain": signals_by_chain,
            "inflow_by_chain": inflow_by_chain,
            "announcement_items": announcement_items,
            "focus_spot_product": focus_spot_product,
            "source_digest": source_digest,
        }

    def collect_announcements(self) -> List[Dict[str, Any]]:
        catalogs = self.safe_call("announcement_catalogs", self.client.get_announcement_catalogs, fallback=[])
        wanted_ids = {to_int(item) for item in (self.config.get("announcement_catalog_ids") or [])}
        limit_per_catalog = to_int(self.config.get("announcement_limit_per_catalog")) or 3
        output: List[Dict[str, Any]] = []
        for catalog in catalogs:
            catalog_id = to_int(catalog.get("catalogId"))
            if wanted_ids and catalog_id not in wanted_ids:
                continue
            catalog_name = str(catalog.get("catalogName") or "")
            for article in (catalog.get("articles") or [])[:limit_per_catalog]:
                code = str(article.get("code") or "")
                if not code:
                    continue
                detail = self.safe_call(f"announcement_detail:{code}", self.client.get_announcement_detail, code, fallback={})
                pair_symbols = extract_pair_symbols(detail.get("pairs") or [])
                summary = body_json_to_summary(detail.get("body") or detail.get("contentJson"), max_chars=260)
                title = str(detail.get("title") or article.get("title") or "")
                output.append(
                    {
                        "catalog_id": catalog_id,
                        "catalog_name": catalog_name,
                        "code": code,
                        "title": title,
                        "lane": announcement_lane(title),
                        "published_at": ts_to_iso(detail.get("publishDate") or article.get("releaseDate")),
                        "summary": summary,
                        "symbols": dedupe_list(extract_symbols_from_title(title) + pair_symbols),
                        "detail_url": f"{CMS_ARTICLE_DETAIL_URL}?articleCode={code}",
                    }
                )
        output.sort(key=lambda item: item.get("published_at") or "", reverse=True)
        return output

    def collect_open_interest_map(self, futures_tickers: List[Dict[str, Any]], focus_symbol: Optional[str]) -> Dict[str, Dict[str, Any]]:
        limit = to_int(self.config.get("futures_probe_limit")) or 8
        probe_symbols: List[str] = []
        for item in futures_tickers:
            symbol = str(item.get("symbol") or "")
            if not symbol:
                continue
            probe_symbols.append(symbol)
            if len(dedupe_list(probe_symbols)) >= limit:
                break
        normalized_focus_market_symbol = normalize_market_symbol(focus_symbol)
        if normalized_focus_market_symbol:
            probe_symbols.insert(0, normalized_focus_market_symbol)
        probe_symbols = dedupe_list(probe_symbols)[:limit]

        output: Dict[str, Dict[str, Any]] = {}
        for symbol in probe_symbols:
            rows = self.safe_call(f"open_interest_hist:{symbol}", self.client.get_open_interest_hist, symbol, fallback=[])
            if len(rows) < 2:
                continue
            start_value = to_float(rows[0].get("sumOpenInterestValue"))
            end_value = to_float(rows[-1].get("sumOpenInterestValue"))
            if start_value is None or end_value is None or math.isclose(start_value, 0.0):
                continue
            change_pct = (end_value - start_value) / start_value * 100.0
            output[symbol] = {
                "open_interest_value": end_value,
                "open_interest_change_5m_pct": change_pct,
                "timestamp": ts_to_iso(rows[-1].get("timestamp")),
            }
        return output

    def build_asset_matrix(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        assets: Dict[str, Dict[str, Any]] = {}
        contract_index: Dict[str, str] = {}

        def choose_key(symbol: str, chain_id: str, contract_address: str, prefer_global: bool) -> str:
            if contract_address and contract_address in contract_index:
                return contract_index[contract_address]
            if symbol:
                if prefer_global or symbol in self.cex_base_symbols or symbol in self.alpha_symbols:
                    return symbol
                if chain_id:
                    return f"{chain_id}:{symbol}"
                return symbol
            if contract_address:
                return f"{chain_id or 'chain'}:{contract_address[-10:]}"
            return f"anon:{len(assets) + 1}"

        def get_or_create_asset(
            *,
            symbol: Any = "",
            display_name: Any = "",
            chain_id: Any = "",
            contract_address: Any = "",
            prefer_global: bool = False,
        ) -> Dict[str, Any]:
            normalized_symbol = normalize_symbol(symbol)
            normalized_chain = str(chain_id or "").strip()
            normalized_contract = str(contract_address or "").strip().lower()
            key = choose_key(normalized_symbol, normalized_chain, normalized_contract, prefer_global)
            if key not in assets:
                assets[key] = {
                    "key": key,
                    "symbol": normalized_symbol or key.split(":")[-1],
                    "display_name": str(display_name or normalized_symbol or key.split(":")[-1]),
                    "chain_ids": [],
                    "chain_labels": [],
                    "contract_addresses": [],
                    "source_list": [],
                    "source_hits": 0,
                    "theme_tags": [],
                    "risk_codes": [],
                    "official_titles": [],
                    "spot_symbol": None,
                    "futures_symbol": None,
                    "display_price": None,
                    "display_change_pct": None,
                    "display_volume_24h": None,
                    "spot_price": None,
                    "spot_change_pct": None,
                    "spot_quote_volume": None,
                    "futures_price": None,
                    "futures_change_pct": None,
                    "futures_quote_volume": None,
                    "funding_bps": None,
                    "oi_change_pct_5m": None,
                    "onchain_price": None,
                    "onchain_change_pct": None,
                    "onchain_volume_24h": None,
                    "liquidity": None,
                    "market_cap": None,
                    "holders": None,
                    "social_hype": None,
                    "social_sentiment": None,
                    "social_summary": "",
                    "social_kol_count": None,
                    "smart_money_inflow": None,
                    "smart_money_traders": None,
                    "smart_signal_count": None,
                    "smart_signal_direction": None,
                    "smart_signal_max_gain_pct": None,
                    "smart_signal_status": None,
                    "alpha_mul_point": None,
                    "alpha_volume_24h": None,
                    "alpha_listing_time": None,
                    "official_hits": 0,
                    "official_lanes": [],
                    "audit_risk_level": None,
                    "audit_caution_num": None,
                    "velocity_label": "New",
                    "opportunity_score": 0.0,
                    "gravity_score": 0.0,
                }
            asset = assets[key]
            if display_name and len(str(display_name)) > len(str(asset.get("display_name") or "")):
                asset["display_name"] = str(display_name)
            if normalized_symbol and (not asset.get("symbol") or len(normalized_symbol) <= 12):
                asset["symbol"] = normalized_symbol
            if normalized_chain:
                if normalized_chain not in asset["chain_ids"]:
                    asset["chain_ids"].append(normalized_chain)
                chain_label = CHAIN_NAMES.get(normalized_chain, normalized_chain)
                if chain_label not in asset["chain_labels"]:
                    asset["chain_labels"].append(chain_label)
            if normalized_contract:
                if normalized_contract not in asset["contract_addresses"]:
                    asset["contract_addresses"].append(normalized_contract)
                contract_index[normalized_contract] = key
            return asset

        def add_source(asset: Dict[str, Any], source_name: str) -> None:
            if source_name not in asset["source_list"]:
                asset["source_list"].append(source_name)
                asset["source_hits"] += 1

        def add_tags(asset: Dict[str, Any], items: Iterable[str]) -> None:
            for item in items:
                text = str(item or "").strip()
                if text and text not in asset["theme_tags"]:
                    asset["theme_tags"].append(text)

        for product in context.get("spot_products") or []:
            base_symbol = normalize_symbol(product.get("b"))
            if not base_symbol:
                continue
            asset = get_or_create_asset(symbol=base_symbol, display_name=product.get("an") or base_symbol, prefer_global=True)
            add_source(asset, "spot")
            add_tags(asset, product.get("tags") or [])
            asset["spot_symbol"] = str(product.get("s") or "")
            asset["spot_price"] = to_float(product.get("c"))
            asset["spot_change_pct"] = pct_from_open_close(product.get("o"), product.get("c"))
            asset["spot_quote_volume"] = to_float(product.get("qv"))

        premium_index_map = context.get("premium_index_map") or {}
        open_interest_map = context.get("open_interest_map") or {}
        for ticker in context.get("futures_tickers") or []:
            market_symbol = str(ticker.get("symbol") or "")
            base_symbol = base_from_market_symbol(market_symbol)
            if not base_symbol:
                continue
            asset = get_or_create_asset(symbol=base_symbol, display_name=base_symbol, prefer_global=True)
            add_source(asset, "futures")
            asset["futures_symbol"] = market_symbol
            asset["futures_price"] = to_float(ticker.get("lastPrice"))
            asset["futures_change_pct"] = to_float(ticker.get("priceChangePercent"))
            asset["futures_quote_volume"] = to_float(ticker.get("quoteVolume"))
            premium = premium_index_map.get(market_symbol) or {}
            funding_rate = to_float(premium.get("lastFundingRate"))
            asset["funding_bps"] = funding_rate * 10000.0 if funding_rate is not None else asset.get("funding_bps")
            oi_item = open_interest_map.get(market_symbol) or {}
            asset["oi_change_pct_5m"] = to_float(oi_item.get("open_interest_change_5m_pct"))

        for token in context.get("alpha_tokens") or []:
            symbol = normalize_symbol(token.get("symbol"))
            asset = get_or_create_asset(
                symbol=symbol,
                display_name=token.get("name") or symbol,
                chain_id=token.get("chainId"),
                contract_address=token.get("contractAddress"),
                prefer_global=True,
            )
            add_source(asset, "alpha")
            if to_int(token.get("mulPoint")):
                add_tags(asset, ["Alpha", f"{to_int(token.get('mulPoint'))}x Alpha Points"])
            else:
                add_tags(asset, ["Alpha"])
            asset["onchain_price"] = to_float(token.get("price")) or asset.get("onchain_price")
            asset["onchain_change_pct"] = to_float(token.get("percentChange24h")) or asset.get("onchain_change_pct")
            asset["onchain_volume_24h"] = to_float(token.get("volume24h")) or asset.get("onchain_volume_24h")
            asset["liquidity"] = max(to_float(token.get("liquidity")) or 0.0, to_float(asset.get("liquidity")) or 0.0) or asset.get("liquidity")
            asset["market_cap"] = max(to_float(token.get("marketCap")) or 0.0, to_float(asset.get("market_cap")) or 0.0) or asset.get("market_cap")
            asset["holders"] = max(to_float(token.get("holders")) or 0.0, to_float(asset.get("holders")) or 0.0) or asset.get("holders")
            asset["alpha_mul_point"] = max(to_int(token.get("mulPoint")) or 0, to_int(asset.get("alpha_mul_point")) or 0) or asset.get("alpha_mul_point")
            asset["alpha_volume_24h"] = to_float(token.get("volume24h")) or asset.get("alpha_volume_24h")
            asset["alpha_listing_time"] = ts_to_iso(token.get("listingTime")) or asset.get("alpha_listing_time")

        for chain_id, items in (context.get("unified_by_chain") or {}).items():
            for token in items:
                symbol = normalize_symbol(token.get("symbol"))
                asset = get_or_create_asset(
                    symbol=symbol,
                    display_name=((token.get("metaInfo") or {}).get("name") or token.get("symbol") or symbol),
                    chain_id=chain_id,
                    contract_address=token.get("contractAddress"),
                    prefer_global=symbol in self.cex_base_symbols or symbol in self.alpha_symbols,
                )
                add_source(asset, "unified_rank")
                add_tags(asset, tag_names_from_map(token.get("tokenTag")))
                asset["onchain_price"] = to_float(token.get("price")) or asset.get("onchain_price")
                asset["onchain_change_pct"] = to_float(token.get("percentChange24h")) or asset.get("onchain_change_pct")
                asset["onchain_volume_24h"] = to_float(token.get("volume24h")) or asset.get("onchain_volume_24h")
                asset["liquidity"] = max(to_float(token.get("liquidity")) or 0.0, to_float(asset.get("liquidity")) or 0.0) or asset.get("liquidity")
                asset["market_cap"] = max(to_float(token.get("marketCap")) or 0.0, to_float(asset.get("market_cap")) or 0.0) or asset.get("market_cap")
                asset["holders"] = max(to_float(token.get("holders")) or 0.0, to_float(asset.get("holders")) or 0.0) or asset.get("holders")
                audit_info = token.get("auditInfo") or {}
                asset["audit_risk_level"] = max(to_int(audit_info.get("riskLevel")) or 0, to_int(asset.get("audit_risk_level")) or 0) or asset.get("audit_risk_level")
                asset["audit_caution_num"] = max(to_int(audit_info.get("cautionNum")) or 0, to_int(asset.get("audit_caution_num")) or 0) or asset.get("audit_caution_num")
                asset["risk_codes"] = dedupe_list((asset.get("risk_codes") or []) + list(audit_info.get("riskCodes") or []))
                token_tags = tag_names_from_map(token.get("tokenTag"))
                if any("4x alpha" in tag.lower() for tag in token_tags):
                    asset["alpha_mul_point"] = max(to_int(asset.get("alpha_mul_point")) or 0, 4)

        for chain_id, items in (context.get("social_by_chain") or {}).items():
            for item in items:
                meta_info = item.get("metaInfo") or {}
                symbol = normalize_symbol(meta_info.get("symbol"))
                asset = get_or_create_asset(
                    symbol=symbol,
                    display_name=symbol or meta_info.get("symbol") or "Token",
                    chain_id=chain_id,
                    contract_address=meta_info.get("contractAddress"),
                    prefer_global=symbol in self.cex_base_symbols or symbol in self.alpha_symbols,
                )
                add_source(asset, "social_hype")
                add_tags(asset, tag_names_from_map(item.get("tagInfoList")))
                social_info = item.get("socialHypeInfo") or {}
                market_info = item.get("marketInfo") or {}
                asset["social_hype"] = max(to_float(social_info.get("socialHype")) or 0.0, to_float(asset.get("social_hype")) or 0.0) or asset.get("social_hype")
                asset["social_sentiment"] = social_info.get("sentiment") or asset.get("social_sentiment")
                asset["social_summary"] = clip_text(
                    social_info.get("socialSummaryDetailTranslated")
                    or social_info.get("socialSummaryDetail")
                    or social_info.get("socialSummaryBriefTranslated")
                    or social_info.get("socialSummaryBrief"),
                    max_chars=220,
                )
                asset["social_kol_count"] = max(to_float(social_info.get("kolCount")) or 0.0, to_float(asset.get("social_kol_count")) or 0.0) or asset.get("social_kol_count")
                asset["market_cap"] = max(to_float(market_info.get("marketCap")) or 0.0, to_float(asset.get("market_cap")) or 0.0) or asset.get("market_cap")

        for chain_id, items in (context.get("signals_by_chain") or {}).items():
            for item in items:
                symbol = normalize_symbol(item.get("ticker"))
                asset = get_or_create_asset(
                    symbol=symbol,
                    display_name=item.get("ticker") or symbol,
                    chain_id=chain_id,
                    contract_address=item.get("contractAddress"),
                    prefer_global=symbol in self.cex_base_symbols or symbol in self.alpha_symbols,
                )
                add_source(asset, "smart_signal")
                add_tags(asset, tag_names_from_map(item.get("tokenTag")))
                asset["smart_signal_count"] = max(to_float(item.get("signalCount")) or 0.0, to_float(asset.get("smart_signal_count")) or 0.0) or asset.get("smart_signal_count")
                asset["smart_signal_direction"] = item.get("direction") or asset.get("smart_signal_direction")
                max_gain = to_float(item.get("maxGain"))
                if max_gain is not None:
                    if abs(max_gain) <= 1:
                        max_gain *= 100.0
                    asset["smart_signal_max_gain_pct"] = max(max_gain, to_float(asset.get("smart_signal_max_gain_pct")) or 0.0)
                asset["smart_signal_status"] = item.get("status") or asset.get("smart_signal_status")
                asset["onchain_price"] = to_float(item.get("currentPrice")) or asset.get("onchain_price")

        for chain_id, items in (context.get("inflow_by_chain") or {}).items():
            for item in items:
                name = str(item.get("tokenName") or "Token")
                symbol = normalize_symbol(name)
                contract_address = str(item.get("ca") or "").strip().lower()
                asset = get_or_create_asset(
                    symbol=symbol,
                    display_name=name,
                    chain_id=chain_id,
                    contract_address=contract_address,
                    prefer_global=symbol in self.cex_base_symbols or symbol in self.alpha_symbols,
                )
                add_source(asset, "smart_money")
                add_tags(asset, tag_names_from_map(item.get("tokenTag")))
                asset["onchain_price"] = to_float(item.get("price")) or asset.get("onchain_price")
                asset["onchain_change_pct"] = to_float(item.get("priceChangeRate")) or asset.get("onchain_change_pct")
                asset["onchain_volume_24h"] = to_float(item.get("volume")) or asset.get("onchain_volume_24h")
                asset["liquidity"] = max(to_float(item.get("liquidity")) or 0.0, to_float(asset.get("liquidity")) or 0.0) or asset.get("liquidity")
                asset["market_cap"] = max(to_float(item.get("marketCap")) or 0.0, to_float(asset.get("market_cap")) or 0.0) or asset.get("market_cap")
                asset["holders"] = max(to_float(item.get("holders")) or 0.0, to_float(asset.get("holders")) or 0.0) or asset.get("holders")
                asset["smart_money_inflow"] = max(to_float(item.get("inflow")) or 0.0, to_float(asset.get("smart_money_inflow")) or 0.0) or asset.get("smart_money_inflow")
                asset["smart_money_traders"] = max(to_float(item.get("traders")) or 0.0, to_float(asset.get("smart_money_traders")) or 0.0) or asset.get("smart_money_traders")
                asset["audit_risk_level"] = max(to_int(item.get("tokenRiskLevel")) or 0, to_int(asset.get("audit_risk_level")) or 0) or asset.get("audit_risk_level")
                asset["audit_caution_num"] = max(to_int(item.get("tokenCautionNum")) or 0, to_int(asset.get("audit_caution_num")) or 0) or asset.get("audit_caution_num")
                asset["risk_codes"] = dedupe_list((asset.get("risk_codes") or []) + list(item.get("tokenRiskCodes") or []))

        focus_spot_product = context.get("focus_spot_product") or {}
        if focus_spot_product:
            symbol = normalize_symbol(focus_spot_product.get("b"))
            asset = get_or_create_asset(symbol=symbol, display_name=focus_spot_product.get("an") or symbol, prefer_global=True)
            add_source(asset, "focus_spot")
            add_tags(asset, focus_spot_product.get("tags") or [])
            asset["spot_symbol"] = str(focus_spot_product.get("s") or asset.get("spot_symbol") or "")
            asset["spot_price"] = to_float(focus_spot_product.get("c")) or asset.get("spot_price")
            asset["spot_change_pct"] = pct_from_open_close(focus_spot_product.get("o"), focus_spot_product.get("c")) or asset.get("spot_change_pct")
            asset["spot_quote_volume"] = to_float(focus_spot_product.get("qv")) or asset.get("spot_quote_volume")

        return list(assets.values())

    def build_catalyst_reactor(self, context: Dict[str, Any], assets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        items = []
        for item in context.get("announcement_items") or []:
            entry = dict(item)
            entry["linked_assets"] = []
            entry["impact_score"] = 0
            items.append(entry)
        return items

    def apply_catalyst_placeholders(self, assets: List[Dict[str, Any]], catalysts: List[Dict[str, Any]]) -> None:
        existing_symbols = {normalize_symbol(item.get("symbol")): item for item in assets if normalize_symbol(item.get("symbol"))}
        for catalyst in catalysts:
            for symbol in catalyst.get("symbols") or []:
                normalized_symbol = normalize_symbol(symbol)
                if not normalized_symbol or normalized_symbol in existing_symbols:
                    continue
                placeholder = {
                    "key": normalized_symbol,
                    "symbol": normalized_symbol,
                    "display_name": normalized_symbol,
                    "chain_ids": [],
                    "chain_labels": [],
                    "contract_addresses": [],
                    "source_list": ["official"],
                    "source_hits": 1,
                    "theme_tags": [],
                    "risk_codes": [],
                    "official_titles": [],
                    "spot_symbol": None,
                    "futures_symbol": f"{normalized_symbol}USDT",
                    "display_price": None,
                    "display_change_pct": None,
                    "display_volume_24h": None,
                    "spot_price": None,
                    "spot_change_pct": None,
                    "spot_quote_volume": None,
                    "futures_price": None,
                    "futures_change_pct": None,
                    "futures_quote_volume": None,
                    "funding_bps": None,
                    "oi_change_pct_5m": None,
                    "onchain_price": None,
                    "onchain_change_pct": None,
                    "onchain_volume_24h": None,
                    "liquidity": None,
                    "market_cap": None,
                    "holders": None,
                    "social_hype": None,
                    "social_sentiment": None,
                    "social_summary": "",
                    "social_kol_count": None,
                    "smart_money_inflow": None,
                    "smart_money_traders": None,
                    "smart_signal_count": None,
                    "smart_signal_direction": None,
                    "smart_signal_max_gain_pct": None,
                    "smart_signal_status": None,
                    "alpha_mul_point": None,
                    "alpha_volume_24h": None,
                    "alpha_listing_time": None,
                    "official_hits": 0,
                    "official_lanes": [],
                    "audit_risk_level": None,
                    "audit_caution_num": None,
                    "velocity_label": "New",
                    "opportunity_score": 0.0,
                    "gravity_score": 0.0,
                }
                assets.append(placeholder)
                existing_symbols[normalized_symbol] = placeholder

    def apply_catalysts_to_assets(self, assets: List[Dict[str, Any]], catalysts: List[Dict[str, Any]]) -> None:
        symbol_index = {normalize_symbol(item.get("symbol")): item for item in assets if normalize_symbol(item.get("symbol"))}
        name_index = {normalize_text_key(item.get("display_name")): item for item in assets if normalize_text_key(item.get("display_name"))}
        for catalyst in catalysts:
            linked_keys: List[str] = []
            title_text = str(catalyst.get("title") or "")
            normalized_title = normalize_text_key(title_text)
            for symbol in catalyst.get("symbols") or []:
                asset = symbol_index.get(normalize_symbol(symbol))
                if asset:
                    linked_keys.append(asset["key"])
            if not linked_keys:
                for name_key, asset in name_index.items():
                    if len(name_key) >= 3 and name_key in normalized_title:
                        linked_keys.append(asset["key"])
            linked_keys = dedupe_list(linked_keys)
            catalyst["linked_assets"] = linked_keys
            catalyst["impact_score"] = clamp(40 + len(linked_keys) * 12 + (10 if catalyst.get("lane") in {"上市点火", "合约扩张"} else 0), 0, 100)
            for key in linked_keys:
                asset = next((item for item in assets if item.get("key") == key), None)
                if not asset:
                    continue
                asset["official_hits"] = (to_int(asset.get("official_hits")) or 0) + 1
                asset["official_titles"] = dedupe_list((asset.get("official_titles") or []) + [title_text])
                asset["official_lanes"] = dedupe_list((asset.get("official_lanes") or []) + [str(catalyst.get("lane") or "")])
                if "official" not in asset["source_list"]:
                    asset["source_list"].append("official")
                    asset["source_hits"] += 1

    def apply_focus_audit(self, assets: List[Dict[str, Any]], focus_symbol: Optional[str]) -> None:
        if not focus_symbol:
            return
        normalized = normalize_symbol(focus_symbol)
        market_symbol = normalize_market_symbol(focus_symbol)
        focus_candidates = []
        for asset in assets:
            if normalize_symbol(asset.get("symbol")) == normalized or normalize_market_symbol(asset.get("spot_symbol") or asset.get("futures_symbol") or asset.get("symbol")) == market_symbol:
                focus_candidates.append(asset)
        if not focus_candidates:
            return
        focus_asset = focus_candidates[0]
        contract_addresses = focus_asset.get("contract_addresses") or []
        chain_ids = focus_asset.get("chain_ids") or []
        if not contract_addresses or not chain_ids:
            return
        contract_address = str(contract_addresses[0] or "")
        chain_id = str(chain_ids[0] or "")
        if not contract_address or not chain_id:
            return
        cache_key = (chain_id, contract_address)
        if cache_key not in self.audit_cache:
            self.audit_cache[cache_key] = self.safe_call(
                f"audit_token:{chain_id}:{contract_address}",
                self.client.audit_token,
                chain_id,
                contract_address,
                fallback={},
            )
        audit_info = self.audit_cache.get(cache_key) or {}
        if not audit_info:
            return
        focus_asset["audit_risk_level"] = max(to_int(audit_info.get("riskLevel")) or 0, to_int(focus_asset.get("audit_risk_level")) or 0) or focus_asset.get("audit_risk_level")
        focus_asset["audit_caution_num"] = max(to_int(audit_info.get("cautionNum")) or 0, to_int(focus_asset.get("audit_caution_num")) or 0) or focus_asset.get("audit_caution_num")
        focus_asset["risk_codes"] = dedupe_list((focus_asset.get("risk_codes") or []) + list(audit_info.get("riskCodes") or []))

    def build_asset_thesis(self, asset: Dict[str, Any]) -> str:
        reasons: List[str] = []
        if (to_float(asset.get("official_score")) or 0.0) >= 55:
            reasons.append("官方催化已入场")
        if (to_float(asset.get("smart_money_score")) or 0.0) >= 55:
            reasons.append("聪明钱或信号确认偏强")
        if (to_float(asset.get("leverage_score")) or 0.0) >= 55:
            reasons.append("合约热度明显抬升")
        if (to_float(asset.get("alpha_score")) or 0.0) >= 55:
            reasons.append("Alpha 前沿强度高")
        if (to_float(asset.get("social_score")) or 0.0) >= 55:
            reasons.append("社媒热度已形成外部引力")
        if (to_float(asset.get("risk_score")) or 0.0) >= 60:
            reasons.append("同时伴随较高坍缩风险")
        if not reasons:
            reasons.append("多源信号有初步共振，但尚未形成绝对单边")
        return "；".join(reasons[:3])

    def finalize_asset_scores(self, assets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        now = self.generated_at_dt
        raw_market_values: List[Optional[float]] = []
        raw_social_values: List[Optional[float]] = []
        raw_smart_values: List[Optional[float]] = []
        raw_official_values: List[Optional[float]] = []
        raw_leverage_values: List[Optional[float]] = []
        raw_alpha_values: List[Optional[float]] = []
        raw_risk_values: List[Optional[float]] = []

        for asset in assets:
            display_price = safe_first([to_float(asset.get("futures_price")), to_float(asset.get("spot_price")), to_float(asset.get("onchain_price"))])
            display_change_pct = safe_first([to_float(asset.get("futures_change_pct")), to_float(asset.get("spot_change_pct")), to_float(asset.get("onchain_change_pct"))])
            display_volume_24h = max(
                to_float(asset.get("spot_quote_volume")) or 0.0,
                to_float(asset.get("futures_quote_volume")) or 0.0,
                to_float(asset.get("onchain_volume_24h")) or 0.0,
                to_float(asset.get("alpha_volume_24h")) or 0.0,
            )
            asset["display_price"] = display_price
            asset["display_change_pct"] = display_change_pct
            asset["display_volume_24h"] = display_volume_24h or None

            launch_age_hours = hours_between(iso_to_datetime(asset.get("alpha_listing_time")), now)
            recent_alpha_bonus = 10.0 if launch_age_hours is not None and launch_age_hours <= 96 else 0.0
            theme_tags_text = " | ".join(asset.get("theme_tags") or []).lower()
            risk_codes_text = " | ".join(asset.get("risk_codes") or []).lower()
            low_liquidity_threshold = to_float((self.config.get("alert_thresholds") or {}).get("low_liquidity_usd")) or 120000.0
            hyper_move_threshold = to_float((self.config.get("alert_thresholds") or {}).get("hyper_move_pct")) or 20.0

            market_raw = safe_log10(display_volume_24h or 1) * 18.0 + clamp(abs(display_change_pct or 0.0), 0.0, 45.0) * 1.6 + min((to_int(asset.get("source_hits")) or 0) * 3.0, 18.0)
            social_raw = safe_log10(to_float(asset.get("social_hype")) or 1) * 14.0 + min((to_float(asset.get("social_kol_count")) or 0.0) / 20.0, 18.0) + (10.0 if str(asset.get("social_sentiment") or "").lower() == "positive" else 4.0 if asset.get("social_sentiment") else 0.0)
            smart_raw = safe_log10((to_float(asset.get("smart_money_inflow")) or 0.0) + 1.0) * 24.0 + min((to_float(asset.get("smart_signal_count")) or 0.0) * 4.5, 22.0) + min(abs(to_float(asset.get("smart_signal_max_gain_pct")) or 0.0) * 0.8, 26.0)
            official_raw = (to_float(asset.get("official_hits")) or 0.0) * 20.0 + (12.0 if "上市点火" in (asset.get("official_lanes") or []) else 0.0) + (8.0 if "合约扩张" in (asset.get("official_lanes") or []) else 0.0)
            leverage_raw = abs(to_float(asset.get("funding_bps")) or 0.0) * 4.5 + abs(to_float(asset.get("oi_change_pct_5m")) or 0.0) * 7.0 + min(abs(to_float(asset.get("futures_change_pct")) or 0.0), 28.0)
            alpha_raw = (to_float(asset.get("alpha_mul_point")) or 0.0) * 10.0 + safe_log10((to_float(asset.get("alpha_volume_24h")) or 0.0) + 1.0) * 16.0 + recent_alpha_bonus
            risk_raw = (
                (to_float(asset.get("audit_risk_level")) or 0.0) * 24.0
                + (to_float(asset.get("audit_caution_num")) or 0.0) * 10.0
                + (18.0 if "wash trading" in theme_tags_text or "wash trading" in risk_codes_text else 0.0)
                + (18.0 if "insider" in theme_tags_text else 0.0)
                + (16.0 if "dev close position" in theme_tags_text else 0.0)
                + (14.0 if "low liquidity" in theme_tags_text else 0.0)
                + (14.0 if (to_float(asset.get("liquidity")) or 0.0) < low_liquidity_threshold and (to_float(asset.get("social_hype")) or 0.0) > 100000 else 0.0)
                + (10.0 if abs(to_float(asset.get("display_change_pct")) or 0.0) >= hyper_move_threshold and (to_float(asset.get("liquidity")) or 0.0) < low_liquidity_threshold * 1.8 else 0.0)
            )

            asset["_raw_market"] = market_raw
            asset["_raw_social"] = social_raw
            asset["_raw_smart"] = smart_raw
            asset["_raw_official"] = official_raw
            asset["_raw_leverage"] = leverage_raw
            asset["_raw_alpha"] = alpha_raw
            asset["_raw_risk"] = risk_raw
            raw_market_values.append(market_raw)
            raw_social_values.append(social_raw)
            raw_smart_values.append(smart_raw)
            raw_official_values.append(official_raw)
            raw_leverage_values.append(leverage_raw)
            raw_alpha_values.append(alpha_raw)
            raw_risk_values.append(risk_raw)

        for asset in assets:
            market_score = min_max_scale(raw_market_values, to_float(asset.get("_raw_market")))
            social_score = min_max_scale(raw_social_values, to_float(asset.get("_raw_social")))
            smart_score = min_max_scale(raw_smart_values, to_float(asset.get("_raw_smart")))
            official_score = min_max_scale(raw_official_values, to_float(asset.get("_raw_official")))
            leverage_score = min_max_scale(raw_leverage_values, to_float(asset.get("_raw_leverage")))
            alpha_score = min_max_scale(raw_alpha_values, to_float(asset.get("_raw_alpha")))
            risk_score = min_max_scale(raw_risk_values, to_float(asset.get("_raw_risk")))
            composite_score = clamp(market_score * 0.24 + social_score * 0.16 + smart_score * 0.18 + official_score * 0.14 + leverage_score * 0.14 + alpha_score * 0.14, 0.0, 100.0)
            opportunity_score = clamp(composite_score - risk_score * 0.35 + min((to_float(asset.get("source_hits")) or 0.0) * 2.0, 12.0), 0.0, 100.0)
            gravity_score = clamp(risk_score * 0.55 + leverage_score * 0.45, 0.0, 100.0)
            previous = self.previous_asset_index.get(asset["key"]) or {}
            previous_score = to_float(previous.get("opportunity_score")) or 0.0
            delta = opportunity_score - previous_score
            if not previous:
                velocity_label = "New"
            elif delta >= 12:
                velocity_label = "Accelerating"
            elif delta >= 4:
                velocity_label = "Strengthening"
            elif delta <= -10:
                velocity_label = "Fading"
            else:
                velocity_label = "Stable"

            asset["market_score"] = round(market_score, 2)
            asset["social_score"] = round(social_score, 2)
            asset["smart_money_score"] = round(smart_score, 2)
            asset["official_score"] = round(official_score, 2)
            asset["leverage_score"] = round(leverage_score, 2)
            asset["alpha_score"] = round(alpha_score, 2)
            asset["risk_score"] = round(risk_score, 2)
            asset["composite_score"] = round(composite_score, 2)
            asset["opportunity_score"] = round(opportunity_score, 2)
            asset["gravity_score"] = round(gravity_score, 2)
            asset["velocity_label"] = velocity_label
            asset["priority_band"] = score_band(opportunity_score)
            asset["gravity_severity"] = severity_label(gravity_score)
            asset["thesis"] = self.build_asset_thesis(asset)

        assets.sort(key=lambda item: (to_float(item.get("opportunity_score")) or 0.0, to_float(item.get("composite_score")) or 0.0, to_float(item.get("display_volume_24h")) or 0.0), reverse=True)
        return assets

    def build_temporal_shift(self, asset_matrix: List[Dict[str, Any]]) -> Dict[str, Any]:
        previous_phase = ((self.previous_report.get("market_phase") or {}).get("phase_name")) or ""
        new_assets = [item for item in asset_matrix if item.get("velocity_label") == "New"][:3]
        accelerating = [item for item in asset_matrix if item.get("velocity_label") in {"Accelerating", "Strengthening"}][:3]
        fading = [item for item in asset_matrix if item.get("velocity_label") == "Fading"][:3]
        return {
            "previous_generated_at": self.previous_report.get("generated_at"),
            "previous_phase": previous_phase,
            "phase_transition_hint": "新周期" if not previous_phase else f"由 {previous_phase} 漂移而来",
            "new_arrivals": [{"symbol": item.get("symbol"), "display_name": item.get("display_name")} for item in new_assets],
            "accelerating_assets": [{"symbol": item.get("symbol"), "display_name": item.get("display_name")} for item in accelerating],
            "fading_assets": [{"symbol": item.get("symbol"), "display_name": item.get("display_name")} for item in fading],
        }

    def build_signal_constellation(self, asset_matrix: List[Dict[str, Any]], context: Dict[str, Any], catalysts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        def lane_assets(predicate: Any, limit: int = 4) -> List[Dict[str, Any]]:
            return [item for item in asset_matrix if predicate(item)][:limit]

        lanes = [
            {"id": "official_catalyst_belt", "title": "官方催化带", "summary": "公告、上新、合约扩张和功能接入正在驱动再定价。", "items": lane_assets(lambda item: (to_float(item.get("official_score")) or 0.0) >= 45)},
            {"id": "smart_money_jump", "title": "聪明钱跃迁层", "summary": "智能信号和聪明钱流入正在把部分资产从普通热度抬升到可跟踪状态。", "items": lane_assets(lambda item: (to_float(item.get("smart_money_score")) or 0.0) >= 45)},
            {"id": "leverage_thermal_layer", "title": "杠杆热层", "summary": "资金费率与持仓跃迁代表合约市场已经进入高温区域。", "items": lane_assets(lambda item: (to_float(item.get("leverage_score")) or 0.0) >= 45)},
            {"id": "alpha_frontier", "title": "Alpha 前沿层", "summary": "Alpha 早期信号正在为部分代币提供更前置的观察窗口。", "items": lane_assets(lambda item: (to_float(item.get("alpha_score")) or 0.0) >= 45)},
            {"id": "social_gravity_field", "title": "社媒引力场", "summary": "社媒热度并不等于确定性，但它定义了注意力引力中心。", "items": lane_assets(lambda item: (to_float(item.get("social_score")) or 0.0) >= 45)},
            {"id": "launchpad_swarm", "title": "Launchpad 迷因团", "summary": "低流动性的新币冲击集中在聪明钱流入与 Launch Platform 标签聚集区。", "items": lane_assets(lambda item: any("launch" in str(tag).lower() or "fourmeme" in str(tag).lower() for tag in (item.get("theme_tags") or [])))},
        ]

        output: List[Dict[str, Any]] = []
        for lane in lanes:
            items = lane["items"]
            if not items:
                continue
            intensity = sum((to_float(item.get("opportunity_score")) or 0.0) for item in items) / len(items)
            output.append({"id": lane["id"], "title": lane["title"], "summary": lane["summary"], "intensity": round(intensity, 2), "count": len(items), "assets": [{"symbol": item.get("symbol"), "display_name": item.get("display_name"), "score": item.get("opportunity_score"), "thesis": item.get("thesis")} for item in items]})
        output.sort(key=lambda item: to_float(item.get("intensity")) or 0.0, reverse=True)
        return output

    def build_market_phase(self, asset_matrix: List[Dict[str, Any]], signal_constellation: List[Dict[str, Any]], catalysts: List[Dict[str, Any]], gravity_alerts: List[Dict[str, Any]], temporal_shift: Dict[str, Any]) -> Dict[str, Any]:
        top_assets = asset_matrix[:6]
        avg_opportunity = sum((to_float(item.get("opportunity_score")) or 0.0) for item in top_assets) / max(len(top_assets), 1)
        leverage_temperature = sum((to_float(item.get("leverage_score")) or 0.0) for item in top_assets) / max(len(top_assets), 1)
        catalyst_pressure = sum((to_float(item.get("impact_score")) or 0.0) for item in catalysts[:6]) / max(min(len(catalysts), 6), 1)
        gravity_pressure = sum((to_float(item.get("gravity_score")) or 0.0) for item in gravity_alerts[:6]) / max(min(len(gravity_alerts), 6), 1)
        signal_density = sum((to_float(item.get("intensity")) or 0.0) for item in signal_constellation[:5]) / max(min(len(signal_constellation), 5), 1)
        social_vs_money_spread = 0.0
        if top_assets:
            social_vs_money_spread = sum((to_float(item.get("social_score")) or 0.0) for item in top_assets) / len(top_assets) - sum((to_float(item.get("smart_money_score")) or 0.0) for item in top_assets) / len(top_assets)
        if avg_opportunity >= 68 and leverage_temperature >= 58:
            phase_name = "奇点扩张"
            phase_summary = "高密度机会和高杠杆热区同时出现，市场进入明显的能量放大阶段。"
        elif catalyst_pressure >= 58 and avg_opportunity >= 58:
            phase_name = "点火窗口"
            phase_summary = "官方催化和市场承接开始重叠，短线更容易出现非线性放大。"
        elif social_vs_money_spread >= 14:
            phase_name = "高热分歧"
            phase_summary = "注意力先跑，资金确认跟得不够，容易出现热度先行的分歧行情。"
        else:
            phase_name = "引力压缩"
            phase_summary = "市场并非无机会，但需要更严格地筛掉拥挤和高风险噪音。"
        top_asset = top_assets[0] if top_assets else {}
        return {"phase_name": phase_name, "phase_summary": phase_summary, "signal_density": round(signal_density, 2), "leverage_temperature": round(leverage_temperature, 2), "catalyst_pressure": round(catalyst_pressure, 2), "gravity_pressure": round(gravity_pressure, 2), "top_asset": {"symbol": top_asset.get("symbol"), "display_name": top_asset.get("display_name"), "opportunity_score": top_asset.get("opportunity_score")}, "phase_transition_hint": temporal_shift.get("phase_transition_hint")}

    def build_scenarios(self, asset_matrix: List[Dict[str, Any]], catalysts: List[Dict[str, Any]], gravity_alerts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        used_keys: set[str] = set()
        scenarios: List[Dict[str, Any]] = []

        def pick(predicate: Any) -> Optional[Dict[str, Any]]:
            for item in asset_matrix:
                if item.get("key") in used_keys:
                    continue
                if predicate(item):
                    used_keys.add(item["key"])
                    return item
            return None

        official_asset = pick(lambda item: (to_float(item.get("official_score")) or 0.0) >= 55)
        if official_asset:
            scenarios.append({"title": f"{official_asset.get('symbol')} 点火突破窗", "archetype": "Official Ignition", "horizon": "6h-24h", "probability": round(clamp((to_float(official_asset.get('opportunity_score')) or 0.0) * 0.9, 0, 95), 1), "primary_asset": official_asset.get("symbol"), "trigger": "新增配套产品、现货承接或公告后二次流动性扩散出现。", "invalidation": "公告热度消散但成交与信号没有跟上。", "rationale": official_asset.get("thesis")})
        leverage_asset = pick(lambda item: (to_float(item.get("leverage_score")) or 0.0) >= 60)
        if leverage_asset:
            scenarios.append({"title": f"{leverage_asset.get('symbol')} 杠杆挤压带", "archetype": "Leverage Expansion", "horizon": "3h-12h", "probability": round(clamp((to_float(leverage_asset.get('opportunity_score')) or 0.0) * 0.88, 0, 93), 1), "primary_asset": leverage_asset.get("symbol"), "trigger": "资金费率和 5 分钟持仓继续共振，价格保持强势不回吐。", "invalidation": "资金费率回落且持仓收缩，热度无法延续。", "rationale": leverage_asset.get("thesis")})
        smart_asset = pick(lambda item: (to_float(item.get("smart_money_score")) or 0.0) >= 52)
        if smart_asset:
            scenarios.append({"title": f"{smart_asset.get('symbol')} 聪明钱跟随窗", "archetype": "Smart Money Follow-Through", "horizon": "6h-24h", "probability": round(clamp((to_float(smart_asset.get('opportunity_score')) or 0.0) * 0.86, 0, 91), 1), "primary_asset": smart_asset.get("symbol"), "trigger": "信号数量增加或流入重新放大，价格不跌回触发前区间。", "invalidation": "信号失活，或流入回落到无辨识度水平。", "rationale": smart_asset.get("thesis")})
        alpha_asset = pick(lambda item: (to_float(item.get("alpha_score")) or 0.0) >= 50)
        if alpha_asset:
            scenarios.append({"title": f"{alpha_asset.get('symbol')} Alpha 先行扩散", "archetype": "Alpha Frontier Expansion", "horizon": "12h-24h", "probability": round(clamp((to_float(alpha_asset.get('opportunity_score')) or 0.0) * 0.82, 0, 88), 1), "primary_asset": alpha_asset.get("symbol"), "trigger": "Alpha 交易强度延续，并向更主流交易层扩散。", "invalidation": "早期热度快速熄火，承接没有跟上。", "rationale": alpha_asset.get("thesis")})
        high_risk_asset = pick(lambda item: (to_float(item.get("gravity_score")) or 0.0) >= 62)
        if high_risk_asset:
            scenarios.append({"title": f"{high_risk_asset.get('symbol')} 高热坍缩预案", "archetype": "Gravity Collapse", "horizon": "1h-6h", "probability": round(clamp((to_float(high_risk_asset.get('gravity_score')) or 0.0) * 0.9, 0, 96), 1), "primary_asset": high_risk_asset.get("symbol"), "trigger": "低流动性、高杠杆或风险标签继续共振，价格出现快速回吐。", "invalidation": "风险标签消退且流动性明显补强。", "rationale": high_risk_asset.get("thesis")})
        return scenarios[:5]

    def build_gravity_alerts(self, asset_matrix: List[Dict[str, Any]], context: Dict[str, Any]) -> List[Dict[str, Any]]:
        output: List[Dict[str, Any]] = []
        for asset in asset_matrix:
            gravity_score = to_float(asset.get("gravity_score")) or 0.0
            if gravity_score < 42:
                continue
            reasons: List[str] = []
            if (to_float(asset.get("risk_score")) or 0.0) >= 60:
                reasons.append("链上风险或标签风险偏高")
            if (to_float(asset.get("leverage_score")) or 0.0) >= 60:
                reasons.append("合约杠杆热度偏高")
            if (to_float(asset.get("liquidity")) or 0.0) > 0 and (to_float(asset.get("liquidity")) or 0.0) < 120000:
                reasons.append("流动性偏薄")
            if any("wash" in str(code).lower() for code in (asset.get("risk_codes") or [])):
                reasons.append("存在洗盘类风险标记")
            output.append({"symbol": asset.get("symbol"), "display_name": asset.get("display_name"), "gravity_score": asset.get("gravity_score"), "severity": severity_label(gravity_score), "summary": "；".join(reasons[:3]) or "多项风险因子正在叠加", "action": "降低主观确定性，优先观察承接和风险是否继续放大。"})
        output.sort(key=lambda item: to_float(item.get("gravity_score")) or 0.0, reverse=True)
        return output[:8]

    def build_orbit_watchlist(self, asset_matrix: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        output: List[Dict[str, Any]] = []
        for item in asset_matrix[:10]:
            official_score = to_float(item.get("official_score")) or 0.0
            leverage_score = to_float(item.get("leverage_score")) or 0.0
            alpha_score = to_float(item.get("alpha_score")) or 0.0
            risk_score = to_float(item.get("risk_score")) or 0.0
            if official_score >= 60:
                orbit_type = "Catalyst Orbit"
                trigger = "公告后是否出现二次产品扩散、成交承接和话题外溢。"
            elif leverage_score >= 60:
                orbit_type = "Volatility Orbit"
                trigger = "资金费率与持仓继续抬升，价格不回吐。"
            elif alpha_score >= 55:
                orbit_type = "Frontier Orbit"
                trigger = "Alpha 强度延续，并向更主流市场层扩张。"
            elif risk_score >= 60:
                orbit_type = "Shadow Orbit"
                trigger = "只观察，不追高；重点盯坍缩速度。"
            else:
                orbit_type = "Core Orbit"
                trigger = "量价与信号继续共振。"
            output.append({"symbol": item.get("symbol"), "display_name": item.get("display_name"), "orbit_type": orbit_type, "priority": item.get("priority_band"), "opportunity_score": item.get("opportunity_score"), "current_price": item.get("display_price"), "change_pct": item.get("display_change_pct"), "trigger": trigger, "invalidate": "成交衰减、信号钝化或风险层突然抬升。", "thesis": item.get("thesis")})
        return output[:8]

    def build_focus_asset(self, focus_symbol: Optional[str], asset_matrix: List[Dict[str, Any]], context: Dict[str, Any]) -> Dict[str, Any]:
        normalized_focus = normalize_symbol(focus_symbol)
        focus_market_symbol = normalize_market_symbol(focus_symbol)
        chosen: Optional[Dict[str, Any]] = None
        for item in asset_matrix:
            if normalized_focus and (normalize_symbol(item.get("symbol")) == normalized_focus or normalize_market_symbol(item.get("spot_symbol") or item.get("futures_symbol") or item.get("symbol")) == focus_market_symbol):
                chosen = item
                break
        if not chosen and asset_matrix:
            chosen = asset_matrix[0]
        if not chosen:
            return {}
        return {"symbol": chosen.get("symbol"), "display_name": chosen.get("display_name"), "headline": f"{chosen.get('symbol')} 当前位于 {chosen.get('priority_band')} 级观测轨道", "summary": chosen.get("thesis"), "current_price": chosen.get("display_price"), "change_pct": chosen.get("display_change_pct"), "score_stack": [{"label": "市场动能", "score": chosen.get("market_score")}, {"label": "社媒引力", "score": chosen.get("social_score")}, {"label": "聪明钱确认", "score": chosen.get("smart_money_score")}, {"label": "官方催化", "score": chosen.get("official_score")}, {"label": "杠杆温度", "score": chosen.get("leverage_score")}, {"label": "Alpha 强度", "score": chosen.get("alpha_score")}, {"label": "坍缩风险", "score": chosen.get("risk_score")}], "trigger_stack": ["价格维持在当前强势区间之上，不出现公告后快速回落。", "若存在合约，资金费率和持仓变化继续共振更强。", "若存在 Alpha / 链上信号，需观察热度是否继续扩散到更大流动性层。"], "invalidation_stack": ["出现量价背离但信号数量没有继续扩张。", "低流动性风险放大或风险标签被再次触发。", "热度继续上涨，但资金和承接开始掉队。"], "official_titles": chosen.get("official_titles") or [], "source_list": chosen.get("source_list") or []}

    def build_live_brief(self, market_phase: Dict[str, Any], signal_constellation: List[Dict[str, Any]], scenarios: List[Dict[str, Any]], gravity_alerts: List[Dict[str, Any]], orbit_watchlist: List[Dict[str, Any]], focus_asset: Dict[str, Any]) -> List[str]:
        lines: List[str] = []
        if market_phase.get("phase_name"):
            lines.append(f"当前市场相位是「{market_phase['phase_name']}」，核心判断是：{market_phase.get('phase_summary')}")
        if signal_constellation:
            top_lane = signal_constellation[0]
            top_assets = "、".join(item.get("symbol") or "-" for item in top_lane.get("assets") or [] if item.get("symbol"))
            lines.append(f"最强信号轨道是「{top_lane.get('title')}」，当前核心资产集中在：{top_assets or '暂无明确集中点'}。")
        if scenarios:
            first = scenarios[0]
            lines.append(f"最值得跟踪的场景是「{first.get('title')}」，窗口在 {first.get('horizon')}。")
        if gravity_alerts:
            alert = gravity_alerts[0]
            lines.append(f"最高优先级引力预警来自 {alert.get('symbol')}，原因是：{alert.get('summary')}")
        if orbit_watchlist:
            watch_symbols = "、".join(item.get("symbol") or "-" for item in orbit_watchlist[:3])
            lines.append(f"当前优先观察轨道前三是：{watch_symbols}。")
        if focus_asset.get("symbol"):
            lines.append(f"聚焦资产为 {focus_asset.get('symbol')}，当前摘要：{focus_asset.get('summary')}")
        return lines[:6]

    def build_broadcast_pack(self, market_phase: Dict[str, Any], signal_constellation: List[Dict[str, Any]], scenarios: List[Dict[str, Any]], gravity_alerts: List[Dict[str, Any]], orbit_watchlist: List[Dict[str, Any]], focus_asset: Dict[str, Any], live_brief: List[str]) -> Dict[str, Any]:
        top_lane = signal_constellation[0] if signal_constellation else {}
        top_watch = orbit_watchlist[0] if orbit_watchlist else {}
        headline = f"{market_phase.get('phase_name', '事件地平线')}：{top_lane.get('title', '多源信号')} 正在主导市场注意力"
        x_post = clip_text(f"我做了一个「币安事件地平线」：把现货、合约、Alpha、聪明钱、社媒热度和官方公告折叠成未来情景驾驶舱。 当前相位={market_phase.get('phase_name', '-')}，最强轨道={top_lane.get('title', '-')}，优先观察={top_watch.get('symbol', '-')}，最高风险={gravity_alerts[0].get('symbol', '-') if gravity_alerts else '-'}。", max_chars=270)
        square_post = clip_text("今天的币安事件地平线显示，市场并不是简单的普涨或普跌，而是进入了由官方催化、杠杆温度和链上注意力共同塑形的多层结构。"
            f"当前相位是「{market_phase.get('phase_name', '-')}」，最强轨道来自「{top_lane.get('title', '-')}」，优先观察资产是 {top_watch.get('symbol', '-')}。如果继续出现二次承接和信号扩散，短线会更容易进入非线性放大；但高热和低流动性共振的资产也正在靠近引力井。", max_chars=600)
        return {"headline": headline, "x_post": x_post, "square_post": square_post, "talking_points": live_brief[:5], "openclaw_prompts": ["使用 $binance-event-horizon 生成最新币安事件地平线报告", f"使用 $binance-event-horizon 聚焦分析 {focus_asset.get('symbol') or 'BTCUSDT'}", "使用 $binance-event-horizon 输出今天最值得盯的场景与广播封包"]}


def load_history_reports(history_dir: Path, keep_files: int) -> List[Dict[str, Any]]:
    if not history_dir.exists():
        return []
    files = sorted(history_dir.glob("*.json"), reverse=True)[:keep_files]
    output: List[Dict[str, Any]] = []
    for file in files:
        report = load_report_if_exists(file)
        if report:
            output.append(report)
    return output


def save_history_snapshot(history_dir: Path, report: Dict[str, Any], keep_files: int) -> None:
    history_dir.mkdir(parents=True, exist_ok=True)
    timestamp = (report.get("generated_at") or utc_iso_now()).replace(":", "-")
    target = history_dir / f"{timestamp}.json"
    save_json(target, report)
    files = sorted(history_dir.glob("*.json"), reverse=True)
    for stale in files[keep_files:]:
        try:
            stale.unlink()
        except OSError:
            continue


def render_markdown(report: Dict[str, Any]) -> str:
    lines: List[str] = [
        "# 币安事件地平线",
        "",
        f"- 生成时间：{report.get('generated_at')}",
        f"- 市场相位：{((report.get('market_phase') or {}).get('phase_name')) or '-'}",
        f"- 相位摘要：{((report.get('market_phase') or {}).get('phase_summary')) or '-'}",
        "",
        "## 信号星图",
    ]
    for lane in report.get("signal_constellation") or []:
        lines.append(f"- {lane.get('title')} | 强度 {to_float(lane.get('intensity')) or 0:.1f} | 资产：" + "、".join(item.get("symbol") or "-" for item in (lane.get("assets") or [])[:4]))
    lines.extend(["", "## 场景引擎"])
    for item in report.get("scenario_engine") or []:
        lines.append(f"- {item.get('title')} | {item.get('archetype')} | 窗口 {item.get('horizon')} | 触发：{item.get('trigger')}")
    lines.extend(["", "## 引力预警"])
    for item in report.get("gravity_alerts") or []:
        lines.append(f"- {item.get('symbol')} | {item.get('severity')} | {item.get('summary')}")
    lines.extend(["", "## 优先观察轨道"])
    for item in report.get("orbit_watchlist") or []:
        lines.append(f"- {item.get('symbol')} | {item.get('orbit_type')} | {item.get('thesis')}")
    focus_asset = report.get("focus_asset") or {}
    if focus_asset:
        lines.extend(["", "## 聚焦资产", f"- {focus_asset.get('symbol')} | {focus_asset.get('headline')}", f"- 摘要：{focus_asset.get('summary')}"])
    broadcast_pack = report.get("broadcast_pack") or {}
    lines.extend(["", "## 广播封包", f"- 标题：{broadcast_pack.get('headline') or '-'}", f"- X：{broadcast_pack.get('x_post') or '-'}", f"- Square：{broadcast_pack.get('square_post') or '-'}"])
    return "\n".join(lines) + "\n"


def render_html(report: Dict[str, Any], template_path: Path, data_url: str, auto_refresh_seconds: int) -> str:
    template = template_path.read_text(encoding="utf-8")
    embedded_json = json.dumps(report, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = template.replace("__REPORT_JSON__", embedded_json)
    html = html.replace("__DATA_URL__", data_url)
    html = html.replace("__AUTO_REFRESH_SECONDS__", str(auto_refresh_seconds))
    return html


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate the Binance Event Horizon report.")
    parser.add_argument("--config", type=Path, default=None, help="Path to config json")
    parser.add_argument("--json-output", type=Path, default=None, help="Path to output json")
    parser.add_argument("--markdown-output", type=Path, default=None, help="Path to output markdown")
    parser.add_argument("--html-output", type=Path, default=None, help="Path to output html")
    parser.add_argument("--focus-symbol", type=str, default="", help="Optional token or trading pair to focus on")
    parser.add_argument("--previous-json", type=Path, default=None, help="Optional previous report json for temporal shift")
    return parser.parse_args()


def main() -> int:
    ensure_utf8_stdout()
    args = parse_args()
    project_root = Path(__file__).resolve().parent.parent
    config = dict(DEFAULT_CONFIG)
    if args.config:
        config = merge_dicts(config, load_json(args.config, {}))
    history_dir = Path(config.get("history_dir") or "output/history")
    if not history_dir.is_absolute():
        history_dir = project_root / history_dir
    keep_files = to_int(config.get("history_keep_files")) or 72
    previous_report = load_report_if_exists(args.previous_json)
    if not previous_report and args.json_output:
        previous_report = load_report_if_exists(args.json_output)
    history_reports = load_history_reports(history_dir, keep_files)
    builder = EventHorizonBuilder(config, previous_report=previous_report, history_reports=history_reports)
    report = builder.build(focus_symbol=(args.focus_symbol or "").strip())
    if args.json_output:
        save_json(args.json_output, report)
    if args.markdown_output:
        save_text(args.markdown_output, render_markdown(report))
    if args.html_output:
        template_path = project_root / "assets" / "report_template.html"
        json_target = args.json_output if args.json_output else args.html_output.with_suffix(".json")
        data_url = relative_web_path(args.html_output, json_target)
        html = render_html(report, template_path, data_url, to_int(config.get("auto_refresh_seconds")) or 180)
        save_text(args.html_output, html)
    if args.json_output and "demo" not in [part.lower() for part in args.json_output.parts]:
        save_history_snapshot(history_dir, report, keep_files)
    print(json.dumps({"status": "ok", "generated_at": report.get("generated_at"), "warnings": report.get("warnings") or []}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
