"""Scoring utilities for identifying undervalued, short-term outperforming US equities."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Sequence

import math

import yfinance as yf


LOOKBACK_DAYS = 21
ANNUALIZATION_FACTOR = math.sqrt(252)


class AnalysisError(RuntimeError):
    """Raised when the analysis pipeline cannot be executed for a ticker."""


@dataclass
class StockAnalysis:
    """Container for the raw metrics computed for a ticker."""

    ticker: str
    momentum_21d: Optional[float] = None
    volatility_21d: Optional[float] = None
    pe_ratio: Optional[float] = None
    pb_ratio: Optional[float] = None
    free_cash_flow_yield: Optional[float] = None
    market_cap: Optional[float] = None
    last_updated: datetime = field(default_factory=datetime.utcnow)


@dataclass
class RankedStock:
    """Represents the scoring output for a ticker."""

    ticker: str
    composite_score: float
    value_score: float
    momentum_score: float
    risk_score: float
    analysis: StockAnalysis


@dataclass
class AnalysisSummary:
    """Container for the ranked output and any tickers that failed analysis."""

    ranked: List[RankedStock]
    failures: Dict[str, str]


def _compute_momentum(close_prices: Sequence[float]) -> float:
    if len(close_prices) <= LOOKBACK_DAYS:
        raise AnalysisError("Not enough price history to compute momentum")
    return close_prices[-1] / close_prices[-(LOOKBACK_DAYS + 1)] - 1


def _compute_volatility(returns: Sequence[float]) -> float:
    if len(returns) < LOOKBACK_DAYS:
        raise AnalysisError("Not enough return history to compute volatility")
    mean = sum(returns[-LOOKBACK_DAYS:]) / LOOKBACK_DAYS
    variance = sum((r - mean) ** 2 for r in returns[-LOOKBACK_DAYS:]) / LOOKBACK_DAYS
    return math.sqrt(variance) * ANNUALIZATION_FACTOR


def _normalize(metric: Dict[str, Optional[float]], higher_is_better: bool) -> Dict[str, float]:
    valid = {ticker: value for ticker, value in metric.items() if value is not None and math.isfinite(value)}
    if not valid:
        return {ticker: 0.0 for ticker in metric}
    min_value = min(valid.values())
    max_value = max(valid.values())
    if math.isclose(min_value, max_value):
        base_score = 1.0
        return {ticker: (base_score if ticker in valid else 0.0) for ticker in metric}
    scale = max_value - min_value
    normalized = {}
    for ticker, value in metric.items():
        if ticker not in valid:
            normalized[ticker] = 0.0
            continue
        score = (value - min_value) / scale
        if not higher_is_better:
            score = 1.0 - score
        normalized[ticker] = score
    return normalized


def _fetch_analysis(ticker: str, period: str = "6mo") -> StockAnalysis:
    ticker_data = yf.Ticker(ticker)
    history = ticker_data.history(period=period, interval="1d")
    if history.empty:
        raise AnalysisError("No price history available")
    close = history["Close"].tolist()
    momentum = _compute_momentum(close)
    returns = history["Close"].pct_change().dropna().tolist()
    volatility = _compute_volatility(returns)

    info = ticker_data.fast_info
    pe_ratio = info.get("pe_ratio") or info.get("trailing_pe")
    pb_ratio = info.get("pb_ratio") or info.get("price_to_book")
    market_cap = info.get("market_cap")

    cash_flow = ticker_data.cashflow
    free_cash_flow = None
    free_cash_flow_yield = None
    if cash_flow is not None and not cash_flow.empty:
        if "Free Cash Flow" in cash_flow.index:
            free_cash_flow = float(cash_flow.loc["Free Cash Flow"].iloc[0])
        elif "FreeCashFlow" in cash_flow.index:
            free_cash_flow = float(cash_flow.loc["FreeCashFlow"].iloc[0])
    if free_cash_flow is not None and market_cap:
        free_cash_flow_yield = free_cash_flow / market_cap

    return StockAnalysis(
        ticker=ticker,
        momentum_21d=momentum,
        volatility_21d=volatility,
        pe_ratio=pe_ratio,
        pb_ratio=pb_ratio,
        free_cash_flow_yield=free_cash_flow_yield,
        market_cap=market_cap,
    )


def analyze_universe(
    tickers: Iterable[str],
    *,
    period: str = "6mo",
    value_weight: float = 0.5,
    momentum_weight: float = 0.3,
    risk_weight: float = 0.2,
    top_n: Optional[int] = 20,
) -> AnalysisSummary:
    """Analyze and score a collection of tickers.

    Args:
        tickers: Iterable of ticker symbols to evaluate.
        period: Price history period to request from Yahoo Finance.
        value_weight: Weight applied to the undervaluation score.
        momentum_weight: Weight applied to the momentum score.
        risk_weight: Weight applied to the risk (low volatility) score.
        top_n: If provided, limits the number of tickers returned.

    Returns:
        An :class:`AnalysisSummary` with the ranked results and any tickers that
        could not be analysed.
    """

    analyses: Dict[str, StockAnalysis] = {}
    failures: Dict[str, str] = {}
    for ticker in tickers:
        try:
            analyses[ticker] = _fetch_analysis(ticker, period=period)
        except AnalysisError as exc:
            failures[ticker] = str(exc)
        except Exception as exc:  # noqa: BLE001 - propagate unexpected errors with context
            raise AnalysisError(f"Failed to analyze {ticker}: {exc}") from exc

    if not analyses:
        joined = ", ".join(f"{ticker} ({reason})" for ticker, reason in failures.items())
        raise AnalysisError(f"Unable to analyze any tickers. Reasons: {joined}")

    pe_ratios = {ticker: analysis.pe_ratio for ticker, analysis in analyses.items()}
    pb_ratios = {ticker: analysis.pb_ratio for ticker, analysis in analyses.items()}
    fcf_yields = {ticker: analysis.free_cash_flow_yield for ticker, analysis in analyses.items()}
    momenta = {ticker: analysis.momentum_21d for ticker, analysis in analyses.items()}
    volatilities = {ticker: analysis.volatility_21d for ticker, analysis in analyses.items()}

    pe_scores = _normalize(pe_ratios, higher_is_better=False)
    pb_scores = _normalize(pb_ratios, higher_is_better=False)
    fcf_scores = _normalize(fcf_yields, higher_is_better=True)
    momentum_scores = _normalize(momenta, higher_is_better=True)
    risk_scores = _normalize(volatilities, higher_is_better=False)

    ranked: List[RankedStock] = []
    for ticker, analysis in analyses.items():
        value_components: List[float] = []
        if analyses[ticker].pe_ratio is not None:
            value_components.append(pe_scores[ticker])
        if analyses[ticker].pb_ratio is not None:
            value_components.append(pb_scores[ticker])
        if analyses[ticker].free_cash_flow_yield is not None:
            value_components.append(fcf_scores[ticker])

        value_score = sum(value_components) / len(value_components) if value_components else 0.0
        composite = (
            value_weight * value_score
            + momentum_weight * momentum_scores[ticker]
            + risk_weight * risk_scores[ticker]
        )
        ranked.append(
            RankedStock(
                ticker=ticker,
                composite_score=composite,
                value_score=value_score,
                momentum_score=momentum_scores[ticker],
                risk_score=risk_scores[ticker],
                analysis=analysis,
            )
        )

    ranked.sort(key=lambda item: item.composite_score, reverse=True)
    if top_n is not None:
        ranked = ranked[:top_n]
    return AnalysisSummary(ranked=ranked, failures=failures)
