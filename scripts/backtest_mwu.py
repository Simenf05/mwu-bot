import numpy as np
import pandas as pd
import yfinance as yf
import matplotlib.pyplot as plt

from bot.strategy.mwu import MWUParams, drift_weights, update_weights_mwu


def main() -> None:
    assets = ["SPY", "QQQ", "TLT", "IEF", "GLD", "JNJ", "PG", "WMT", "XLU", "VNQ"]
    start_date = "2007-06-01"
    end_date = "2009-12-01"
    eta = 0.5

    sec_fee = 0.0000278

    raw_data = yf.download(assets, start=start_date, end=end_date)
    data = raw_data["Close"]
    high_data = raw_data["High"]
    low_data = raw_data["Low"]

    returns = data.pct_change().dropna()
    daily_spreads = ((high_data - low_data) / data).dropna() * 0.05

    n_assets = len(assets)
    weights = np.ones(n_assets) / n_assets
    portfolio_value = 1.0

    portfolio_values = [portfolio_value]

    params = MWUParams(eta=eta)

    for t in range(len(returns)):
        r = returns.iloc[t].values.astype(float)

        portfolio_return = float(np.dot(weights, r))
        portfolio_value *= (1.0 + portfolio_return)

        drifted_weights = drift_weights(weights, r)
        new_weights = update_weights_mwu(weights, r, params)

        asset_fees = daily_spreads.iloc[t].values + (sec_fee / 2.0)
        cost = float(np.sum(np.abs(new_weights - drifted_weights) * asset_fees) / 2.0)

        portfolio_value *= (1.0 - cost)
        portfolio_values.append(portfolio_value)

        weights = new_weights

    equal_weight_returns = returns.mean(axis=1)
    benchmark = (1 + equal_weight_returns).cumprod()

    portfolio_series = pd.Series(portfolio_values[1:], index=returns.index)

    plt.figure(figsize=(10, 6))
    plt.plot(portfolio_series, label="MWU Portfolio")
    plt.plot(benchmark, label="Equal Weight Benchmark")
    plt.legend()
    plt.title("Multiplicative Weights Portfolio vs Benchmark")
    plt.xlabel("Date")
    plt.ylabel("Portfolio Value")
    plt.grid()
    plt.show()

    final_weights = pd.Series(weights, index=assets)
    print("\nFinal Portfolio Weights:")
    print(final_weights)


if __name__ == "__main__":
    main()

