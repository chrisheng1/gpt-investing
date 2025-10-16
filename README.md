# GPT Investing Screener

This repository contains a Python implementation of an algorithm that surfaces undervalued US equities that are also demonstrating strong short-term momentum. The screener downloads price and fundamental data from Yahoo Finance, combines multiple valuation and performance metrics into a composite score, and returns the top-ranked opportunities.

## How it works

The `gpt_investing` package exposes a high-level `analyze_universe` function that accepts a list of ticker symbols. For each ticker the algorithm:

1. Pulls six months of daily price history via `yfinance`.
2. Calculates a 21-trading-day price momentum and annualised volatility.
3. Collects valuation metrics (price-to-earnings, price-to-book, and free cash flow yield) using Yahoo Finance fundamentals.
4. Normalises the metrics across the universe and builds a weighted composite score favouring undervalued, high-momentum, lower-volatility names.
5. Returns the tickers sorted by the composite score, along with any symbols that could not be evaluated because of missing data.

The default weights emphasise value (50%), momentum (30%), and low volatility (20%). All weights can be customised when invoking the library or the command-line interface.

## Getting started

1. Install the dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Run the screener against the default large-cap universe:
   ```bash
   python analyze.py
   ```
3. Provide your own ticker set by passing symbols directly or by pointing to a file:
   ```bash
   python analyze.py --tickers AAPL MSFT NFLX --top 5
   python analyze.py --universe-file my_tickers.txt --format json
   ```

The CLI prints a table with the composite score, component scores, and the raw metrics for each ranked ticker. Use `--format json` to integrate the results into other tools.

## Library usage

```python
from gpt_investing import analyze_universe

summary = analyze_universe(["AAPL", "MSFT", "GOOGL"])
for ranked in summary.ranked:
    print(ranked.ticker, ranked.composite_score)
```

The returned `AnalysisSummary` object also exposes a `failures` dictionary that explains why any tickers were skipped (for example, due to missing fundamentals or insufficient price history).

## Notes and limitations

- Yahoo Finance data can occasionally be stale or incomplete. Inspect the `failures` dictionary to identify problematic symbols.
- Free cash flow data is not available for every company; when missing, the composite value score is derived from the remaining valuation metrics.
- The screener focuses on large-cap equities by default, but you can provide any tradable US ticker symbols.
