import numpy as np
from scipy.optimize import minimize


def _perf(w, mu, cov):
    ret = w @ mu
    vol = float(np.sqrt(w @ cov @ w))
    return ret, vol


def efficient_frontier(returns_df, rf=0.02, n_random=500):
    """
    Returns dict with random portfolios, efficient frontier curve,
    max-Sharpe and min-vol optimal portfolios.
    All returns/vols expressed in % (annualized).
    """
    mu = returns_df.mean().values * 252
    cov = returns_df.cov().values * 252
    n = len(mu)
    tickers = list(returns_df.columns)

    # ── Random portfolios ──────────────────────────────────────────────────
    rng = np.random.default_rng(42)
    rw = rng.dirichlet(np.ones(n), n_random)
    rand_rets  = [w @ mu for w in rw]
    rand_vols  = [np.sqrt(w @ cov @ w) for w in rw]
    rand_sh    = [(r - rf) / v if v > 0 else 0 for r, v in zip(rand_rets, rand_vols)]

    bounds = [(0.0, 1.0)] * n
    w0     = np.ones(n) / n
    eq_con = [{'type': 'eq', 'fun': lambda w: w.sum() - 1}]

    # ── Max-Sharpe ─────────────────────────────────────────────────────────
    def neg_sharpe(w):
        r, v = _perf(w, mu, cov)
        return -(r - rf) / v if v > 0 else 0.0

    res_sh = minimize(neg_sharpe, w0, method='SLSQP', bounds=bounds, constraints=eq_con)
    opt_w_sh = res_sh.x if res_sh.success else w0
    opt_r_sh, opt_v_sh = _perf(opt_w_sh, mu, cov)

    # ── Min-Vol ────────────────────────────────────────────────────────────
    res_mv = minimize(lambda w: _perf(w, mu, cov)[1], w0,
                      method='SLSQP', bounds=bounds, constraints=eq_con)
    opt_w_mv = res_mv.x if res_mv.success else w0
    opt_r_mv, opt_v_mv = _perf(opt_w_mv, mu, cov)

    # ── Frontier curve ─────────────────────────────────────────────────────
    target_rets  = np.linspace(mu.min() * 0.95, mu.max() * 1.05, 40)
    front_vols, front_rets = [], []
    for tr in target_rets:
        cons = eq_con + [{'type': 'eq', 'fun': lambda w, t=tr: w @ mu - t}]
        res = minimize(lambda w: _perf(w, mu, cov)[1], w0,
                       method='SLSQP', bounds=bounds, constraints=cons)
        if res.success:
            v = np.sqrt(res.x @ cov @ res.x)
            front_vols.append(v * 100)
            front_rets.append(tr * 100)

    return {
        'rand_vols':    [v * 100 for v in rand_vols],
        'rand_rets':    [r * 100 for r in rand_rets],
        'rand_sharpes': rand_sh,
        'front_vols':   front_vols,
        'front_rets':   front_rets,
        'opt_sharpe': {
            'vol': opt_v_sh * 100, 'ret': opt_r_sh * 100,
            'weights': opt_w_sh.tolist(),
            'sharpe': (opt_r_sh - rf) / opt_v_sh if opt_v_sh > 0 else 0,
        },
        'opt_minvol': {
            'vol': opt_v_mv * 100, 'ret': opt_r_mv * 100,
            'weights': opt_w_mv.tolist(),
        },
        'tickers': tickers,
    }
