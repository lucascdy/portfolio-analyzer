import yfinance as yf
import pandas as pd
import numpy as np
from scipy import stats

# ─── Cache des données ────────────────────────────────────────────────────────
_data_cache = {}

def download_data(tickers, start, end):
    key = (tuple(sorted(tickers)), start, end)
    if key in _data_cache:
        return _data_cache[key]
    data = yf.download(tickers, start=start, end=end, auto_adjust=True, progress=False)['Close']
    if isinstance(data, pd.Series):
        data = data.to_frame(name=tickers[0])
    data = data.dropna()
    _data_cache[key] = data
    return data


def calculate_returns(prices):
    return prices.pct_change().dropna()


def portfolio_returns(returns, weights):
    w = np.array(weights, dtype=float)
    w = w / w.sum()
    return (returns * w).sum(axis=1)


def annualized_return(returns):
    total = (1 + returns).prod()
    n_years = len(returns) / 252
    return total ** (1 / n_years) - 1


def annualized_volatility(returns):
    return returns.std() * np.sqrt(252)


def sharpe_ratio(returns, rf=0.02):
    excess = returns - rf / 252
    return (excess.mean() * 252) / (returns.std() * np.sqrt(252))


def sortino_ratio(returns, rf=0.02):
    excess = returns - rf / 252
    downside = returns[returns < 0].std() * np.sqrt(252)
    if downside == 0:
        return np.nan
    return (excess.mean() * 252) / downside


def max_drawdown(returns):
    cum = (1 + returns).cumprod()
    rolling_max = cum.cummax()
    dd = (cum - rolling_max) / rolling_max
    return dd.min()


def drawdown_series(returns):
    cum = (1 + returns).cumprod()
    rolling_max = cum.cummax()
    return (cum - rolling_max) / rolling_max


def calmar_ratio(returns):
    cagr = annualized_return(returns)
    mdd = abs(max_drawdown(returns))
    if mdd == 0:
        return np.nan
    return cagr / mdd


def value_at_risk(returns, confidence=0.95):
    return np.percentile(returns, (1 - confidence) * 100)


def conditional_var(returns, confidence=0.95):
    var = value_at_risk(returns, confidence)
    return returns[returns <= var].mean()


def beta_alpha(port_ret, bench_ret, rf=0.02):
    df = pd.concat([port_ret, bench_ret], axis=1).dropna()
    df.columns = ['portfolio', 'benchmark']
    slope, intercept, r_value, _, _ = stats.linregress(df['benchmark'], df['portfolio'])
    beta = slope
    alpha = (intercept * 252) - rf * (1 - beta)
    return beta, alpha, r_value ** 2


def information_ratio(port_ret, bench_ret):
    df = pd.concat([port_ret, bench_ret], axis=1).dropna()
    df.columns = ['portfolio', 'benchmark']
    active = df['portfolio'] - df['benchmark']
    if active.std() == 0:
        return np.nan
    return (active.mean() * 252) / (active.std() * np.sqrt(252))


def all_metrics(port_ret, bench_ret, rf=0.02):
    beta, alpha, r2 = beta_alpha(port_ret, bench_ret, rf)
    return {
        'CAGR': annualized_return(port_ret),
        'Volatilité': annualized_volatility(port_ret),
        'Sharpe Ratio': sharpe_ratio(port_ret, rf),
        'Sortino Ratio': sortino_ratio(port_ret, rf),
        'Max Drawdown': max_drawdown(port_ret),
        'Calmar Ratio': calmar_ratio(port_ret),
        'VaR 95%': value_at_risk(port_ret),
        'CVaR 95%': conditional_var(port_ret),
        'Beta': beta,
        'Alpha (annualisé)': alpha,
        'R²': r2,
        'Information Ratio': information_ratio(port_ret, bench_ret),
    }


def monte_carlo_simulation(port_ret, n_simulations=300, n_years=10):
    """Simulate future portfolio paths using bootstrapped historical returns."""
    n_days = int(n_years * 252)
    rng = np.random.default_rng(42)
    # Bootstrap from historical returns
    idx = rng.integers(0, len(port_ret), size=(n_simulations, n_days))
    daily = port_ret.values[idx]
    paths = np.cumprod(1 + daily, axis=1)
    return paths  # shape: (n_simulations, n_days)


def asset_contributions(port_returns_df, weights):
    """Return contribution and risk contribution per asset (annualized)."""
    w = np.array(weights, dtype=float)
    w = w / w.sum()
    tickers = list(port_returns_df.columns)
    asset_ret = port_returns_df.mean() * 252
    ret_contrib = w * asset_ret.values
    cov = port_returns_df.cov().values * 252
    port_vol = float(np.sqrt(w @ cov @ w))
    if port_vol == 0:
        risk_contrib = np.zeros(len(w))
    else:
        mcr = cov @ w / port_vol
        risk_contrib = w * mcr
    return ret_contrib, risk_contrib, tickers


def fama_french_proxy(port_ret):
    """
    Régression Fama-French 3 facteurs via des proxies ETF.
    MKT : SPY, SMB : IWM - SPY, HML : IVE - IVW
    Retourne les loadings, t-stats, R² ou None si indisponible.
    """
    try:
        start = port_ret.index[0].strftime('%Y-%m-%d')
        end = port_ret.index[-1].strftime('%Y-%m-%d')
        factor_tickers = ['SPY', 'IWM', 'IVE', 'IVW']
        prices = yf.download(factor_tickers, start=start, end=end,
                             auto_adjust=True, progress=False)['Close']
        if isinstance(prices, pd.Series) or prices.empty:
            return None
        prices = prices.dropna()
        rets = prices.pct_change().dropna()
        if len(rets) < 60:
            return None
        mkt = rets['SPY']
        smb = rets['IWM'] - rets['SPY']
        hml = rets['IVE'] - rets['IVW']
        df = pd.concat([port_ret, mkt, smb, hml], axis=1).dropna()
        df.columns = ['port', 'MKT', 'SMB', 'HML']
        if len(df) < 60:
            return None
        y = df['port'].values
        X = np.column_stack([np.ones(len(df)), df['MKT'].values,
                             df['SMB'].values, df['HML'].values])
        coeffs, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
        residuals = y - X @ coeffs
        n, k = X.shape
        s2 = (residuals ** 2).sum() / (n - k)
        try:
            cov = s2 * np.linalg.inv(X.T @ X)
            se = np.sqrt(np.diag(cov))
        except np.linalg.LinAlgError:
            return None
        t_stats = coeffs / np.where(se > 0, se, np.nan)
        ss_res = (residuals ** 2).sum()
        ss_tot = ((y - y.mean()) ** 2).sum()
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else np.nan
        return {
            'alpha_annual': float(coeffs[0] * 252),
            'alpha_t': float(t_stats[0]),
            'mkt_beta': float(coeffs[1]),
            'mkt_t': float(t_stats[1]),
            'smb_beta': float(coeffs[2]),
            'smb_t': float(t_stats[2]),
            'hml_beta': float(coeffs[3]),
            'hml_t': float(t_stats[3]),
            'r2': float(r2),
            'n': int(n),
        }
    except Exception:
        return None
