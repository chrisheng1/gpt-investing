"""Command line interface for the GPT Investing screening algorithm."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List, Sequence

from gpt_investing import AnalysisError, analyze_universe

DEFAULT_UNIVERSE = [
    "AAPL",
    "MSFT",
    "NVDA",
    "GOOGL",
    "AMZN",
    "META",
    "TSLA",
    "JPM",
    "UNH",
    "JNJ",
    "V",
    "PG",
    "MA",
    "HD",
    "XOM",
    "CVX",
    "KO",
    "PEP",
    "MRK",
    "ABBV",
    "BAC",
    "AVGO",
    "ADBE",
    "CSCO",
    "PFE",
    "LLY",
    "ORCL",
    "TMO",
    "ACN",
    "DHR",
    "COST",
    "MCD",
    "CRM",
    "ABT",
    "TXN",
    "LIN",
    "WFC",
    "UPS",
    "PM",
    "INTC",
    "HON",
    "MS",
    "NEE",
    "UNP",
    "RTX",
    "LOW",
    "QCOM",
    "NKE",
    "AMD",
]


def _load_tickers_from_file(path: Path) -> List[str]:
    content = path.read_text(encoding="utf-8")
    tickers: List[str] = []
    for raw in content.replace(",", "\n").splitlines():
        symbol = raw.strip().upper()
        if not symbol or symbol.startswith("#"):
            continue
        tickers.append(symbol)
    return tickers


def _parse_tickers(values: Sequence[str] | None, universe_file: Path | None) -> List[str]:
    tickers: List[str] = []
    if universe_file:
        tickers.extend(_load_tickers_from_file(universe_file))
    if values:
        tickers.extend(symbol.upper() for symbol in values)
    if not tickers:
        tickers = list(DEFAULT_UNIVERSE)
    unique = sorted(set(tickers))
    if not unique:
        raise ValueError("No tickers supplied for analysis")
    return unique


def _format_percent(value: float | None) -> str:
    if value is None:
        return "   n/a"
    return f"{value * 100:6.2f}%"


def _format_ratio(value: float | None) -> str:
    if value is None:
        return "  n/a"
    return f"{value:6.2f}"


def run_cli(args: argparse.Namespace) -> int:
    try:
        tickers = _parse_tickers(args.tickers, args.universe_file)
    except ValueError as exc:
        print(f"Error: {exc}")
        return 1

    try:
        summary = analyze_universe(
            tickers,
            period=args.period,
            value_weight=args.value_weight,
            momentum_weight=args.momentum_weight,
            risk_weight=args.risk_weight,
            top_n=args.top,
        )
    except AnalysisError as exc:
        print(f"Unable to evaluate tickers: {exc}")
        return 1

    if args.format == "json":
        payload = []
        for ranked in summary.ranked:
            analysis = ranked.analysis
            payload.append(
                {
                    "ticker": ranked.ticker,
                    "composite_score": ranked.composite_score,
                    "value_score": ranked.value_score,
                    "momentum_score": ranked.momentum_score,
                    "risk_score": ranked.risk_score,
                    "momentum_21d": analysis.momentum_21d,
                    "volatility_21d": analysis.volatility_21d,
                    "pe_ratio": analysis.pe_ratio,
                    "pb_ratio": analysis.pb_ratio,
                    "free_cash_flow_yield": analysis.free_cash_flow_yield,
                    "market_cap": analysis.market_cap,
                }
            )
        print(json.dumps({"results": payload, "failures": summary.failures}, indent=2))
    else:
        headers = (
            "Rank",
            "Ticker",
            "Score",
            "Value",
            "Momentum",
            "Risk",
            "PE",
            "PB",
            "FCF Yield",
            "21d Mom",
            "21d Vol",
        )
        print(" \t".join(headers))
        for idx, ranked in enumerate(summary.ranked, start=1):
            analysis = ranked.analysis
            row = (
                f"{idx:>4}",
                f"{ranked.ticker:>6}",
                f"{ranked.composite_score:6.3f}",
                f"{ranked.value_score:6.3f}",
                f"{ranked.momentum_score:6.3f}",
                f"{ranked.risk_score:6.3f}",
                _format_ratio(analysis.pe_ratio),
                _format_ratio(analysis.pb_ratio),
                _format_percent(analysis.free_cash_flow_yield),
                _format_percent(analysis.momentum_21d),
                _format_percent(analysis.volatility_21d),
            )
            print(" \t".join(row))
        if summary.failures:
            print("\nTickers skipped due to data issues:")
            for ticker, reason in summary.failures.items():
                print(f"- {ticker}: {reason}")

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Screen for undervalued and strong short-term performers in US equities.",
    )
    parser.add_argument(
        "--tickers",
        nargs="*",
        help="List of ticker symbols to analyse. Defaults to a diversified large-cap universe.",
    )
    parser.add_argument(
        "--universe-file",
        type=Path,
        help="Optional path to a text file containing additional tickers (comma or newline separated).",
    )
    parser.add_argument(
        "--period",
        default="6mo",
        help="Yahoo Finance lookback period for the price history (default: 6mo).",
    )
    parser.add_argument(
        "--value-weight",
        type=float,
        default=0.5,
        help="Weight assigned to the value (undervaluation) score (default: 0.5).",
    )
    parser.add_argument(
        "--momentum-weight",
        type=float,
        default=0.3,
        help="Weight assigned to the momentum score (default: 0.3).",
    )
    parser.add_argument(
        "--risk-weight",
        type=float,
        default=0.2,
        help="Weight assigned to the low-volatility score (default: 0.2).",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=20,
        help="Number of top-ranked tickers to display (default: 20).",
    )
    parser.add_argument(
        "--format",
        choices=("table", "json"),
        default="table",
        help="Output format for the results (default: table).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return run_cli(args)


if __name__ == "__main__":
    raise SystemExit(main())
