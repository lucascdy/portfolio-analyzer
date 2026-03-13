import sqlite3
import pandas as pd
import requests
import io
import os
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), "stocks.db")

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"}

# ─── Cryptos statiques ────────────────────────────────────────────────────────
CRYPTO_STATIC = [
    ("Bitcoin",       "BTC-USD"), ("Ethereum",    "ETH-USD"),
    ("Solana",        "SOL-USD"), ("BNB",          "BNB-USD"),
    ("XRP",           "XRP-USD"), ("Cardano",      "ADA-USD"),
    ("Avalanche",     "AVAX-USD"),("Dogecoin",     "DOGE-USD"),
    ("Polkadot",      "DOT-USD"), ("Chainlink",    "LINK-USD"),
    ("Polygon",       "MATIC-USD"),("Shiba Inu",   "SHIB-USD"),
    ("Litecoin",      "LTC-USD"), ("Stellar",      "XLM-USD"),
    ("Cosmos",        "ATOM-USD"),("Uniswap",      "UNI7083-USD"),
]

# ─── Sources Wikipedia : (label, url, hints_ticker, hints_nom, suffixe_yahoo) ─
WIKIPEDIA_SOURCES = [
    ("S&P 500",         "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
     ["Symbol","Ticker"],                       ["Security","Company","Name"], ""),
    ("Nasdaq-100",      "https://en.wikipedia.org/wiki/Nasdaq-100",
     ["Ticker","Symbol"],                       ["Company","Name"], ""),
    ("FTSE 100",        "https://en.wikipedia.org/wiki/FTSE_100_Index",
     ["EPIC","Ticker","Symbol"],                ["Company","Name"], ".L"),
    ("CAC 40",          "https://en.wikipedia.org/wiki/CAC_40",
     ["Ticker","Symbol","Symbole"],             ["Company","Name","Société"], ".PA"),
    ("DAX",             "https://en.wikipedia.org/wiki/DAX",
     ["Ticker","Symbol"],                       ["Company","Name"], ".DE"),
    ("Euro Stoxx 50",   "https://en.wikipedia.org/wiki/EURO_STOXX_50",
     ["Ticker","Symbol"],                       ["Company","Name"], ""),
    ("Nikkei 225",      "https://en.wikipedia.org/wiki/Nikkei_225",
     ["__NIKKEI__"],                            ["Company","Name"], ".T"),
    ("Hang Seng",       "https://en.wikipedia.org/wiki/Hang_Seng_Index",
     ["__HANG_SENG__"],                         ["Company","Name"], ".HK"),
    ("ASX 200",         "https://en.wikipedia.org/wiki/S%26P/ASX_200",
     ["Code","ASX code","Ticker","Symbol"],     ["Company","Name"], ".AX"),
    ("TSX Canada",      "https://en.wikipedia.org/wiki/S%26P/TSX_60",
     ["Ticker","Symbol"],                       ["Company","Name"], ".TO"),
    ("IBEX 35",         "https://en.wikipedia.org/wiki/IBEX_35",
     ["Ticker","Symbol","Código"],              ["Company","Name","Empresa"], ".MC"),
    ("SMI Suisse",      "https://en.wikipedia.org/wiki/Swiss_Market_Index",
     ["Ticker","Symbol"],                       ["Company","Name"], ".SW"),
    ("AEX",             "https://en.wikipedia.org/wiki/AEX_index",
     ["Ticker","Symbol"],                       ["Company","Name"], ".AS"),
    ("BEL 20",          "https://en.wikipedia.org/wiki/BEL_20",
     ["Ticker","Symbol"],                       ["Company","Name"], ".BR"),
    ("FTSE MIB",        "https://en.wikipedia.org/wiki/FTSE_MIB",
     ["Ticker","Symbol"],                       ["Company","Name"], ".MI"),
    ("Nifty 50",        "https://en.wikipedia.org/wiki/NIFTY_50",
     ["Symbol","Ticker"],                       ["Company","Name"], ".NS"),
    ("Ibovespa",        "https://en.wikipedia.org/wiki/Ibovespa",
     ["__IBOVESPA__"],                          ["Company","Name"], ".SA"),
    ("OMX Stockholm 30","https://en.wikipedia.org/wiki/OMX_Stockholm_30",
     ["Ticker","Symbol"],                       ["Company","Name"], ".ST"),
    ("PSI Portugal",    "https://en.wikipedia.org/wiki/PSI-20",
     ["Ticker","Symbol"],                       ["Company","Name"], ".LS"),
]


# ─── SQLite helpers ───────────────────────────────────────────────────────────

def _get_conn():
    return sqlite3.connect(DB_PATH)


def _db_needs_update():
    if not os.path.exists(DB_PATH):
        return True
    try:
        conn = _get_conn()
        row = conn.execute("SELECT last_update FROM meta LIMIT 1").fetchone()
        conn.close()
        if not row:
            return True
        return datetime.now() - datetime.fromisoformat(row[0]) > timedelta(days=7)
    except Exception:
        return True


# ─── Fetchers ─────────────────────────────────────────────────────────────────

def _get(url):
    """Requête HTTP avec User-Agent réel."""
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return r


def _fetch_us_nasdaq():
    """NASDAQ Trader : tous les titres US cotés."""
    frames = []
    sources = [
        ("https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt",    "Symbol",     "Security Name", "ETF"),
        ("https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt",     "ACT Symbol", "Security Name", "ETF"),
    ]
    for url, tcol, ncol, etf_col in sources:
        try:
            r = _get(url)
            df = pd.read_csv(io.StringIO(r.text), sep="|")
            if "Test Issue" in df.columns:
                df = df[df["Test Issue"] == "N"]
            df = df.rename(columns={tcol: "ticker", ncol: "name", etf_col: "is_etf"})
            df["ticker"] = df["ticker"].astype(str).str.strip()
            df["name"]   = df["name"].astype(str).str.strip()
            df = df[df["ticker"].str.match(r"^[\w\.\-]+$", na=False)]
            df = df[df["ticker"] != "Symbol"]
            df = df[df["name"] != "nan"]
            df = df[["ticker", "name", "is_etf"]]
            frames.append(df)
            print(f"  US ({url.split('/')[-1]}): {len(df)} titres")
        except Exception as e:
            print(f"  ERREUR NASDAQ {url.split('/')[-1]}: {e}")
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _find_col(columns, hints):
    for hint in hints:
        for col in columns:
            if hint.lower() in str(col).lower():
                return col
    return None


def _fetch_hang_seng():
    """Hang Seng : tickers au format 'SEHK: 5' → '0005.HK'"""
    try:
        r = _get("https://en.wikipedia.org/wiki/Hang_Seng_Index")
        tables = pd.read_html(io.StringIO(r.text))
        for t in tables:
            if "Ticker" in t.columns and "Name" in t.columns:
                df = t[["Ticker", "Name"]].copy()
                df.columns = ["ticker", "name"]
                df["ticker"] = df["ticker"].astype(str).str.extract(r"(\d+)").iloc[:, 0]
                df["ticker"] = df["ticker"].dropna().apply(lambda x: x.zfill(4) + ".HK")
                df = df.dropna()
                df["is_etf"] = "N"
                print(f"  Hang Seng: {len(df)} titres")
                return df[["ticker", "name", "is_etf"]]
    except Exception as e:
        print(f"  ERREUR Hang Seng: {e}")
    return pd.DataFrame()


def _fetch_nikkei():
    """Nikkei 225 : liste depuis StockAnalysis (format simple)."""
    try:
        r = _get("https://en.wikipedia.org/wiki/Nikkei_225")
        tables = pd.read_html(io.StringIO(r.text))
        # Chercher une table avec des codes numériques japonais
        for t in tables:
            cols = [str(c).lower() for c in t.columns]
            if any("code" in c or "ticker" in c for c in cols) and len(t) > 50:
                tc = _find_col(t.columns, ["Code", "Ticker", "Symbol", "code"])
                nc = _find_col(t.columns, ["Name", "Company", "name"])
                if tc and nc:
                    df = t[[tc, nc]].copy()
                    df.columns = ["ticker", "name"]
                    df["ticker"] = df["ticker"].astype(str).str.strip()
                    df = df[df["ticker"].str.match(r"^\d{4}$", na=False)]
                    df["ticker"] = df["ticker"] + ".T"
                    df["is_etf"] = "N"
                    print(f"  Nikkei 225: {len(df)} titres")
                    return df[["ticker", "name", "is_etf"]]
    except Exception as e:
        print(f"  ERREUR Nikkei: {e}")
    print("  Nikkei 225: non disponible (page Wikipedia sans tableau de titres)")
    return pd.DataFrame()


def _fetch_ibovespa():
    """Ibovespa : depuis Wikipedia avec extraction des tickers brésiliens."""
    try:
        r = _get("https://en.wikipedia.org/wiki/Ibovespa")
        tables = pd.read_html(io.StringIO(r.text))
        for t in tables:
            tc = _find_col(t.columns, ["Ticker","Symbol","Code"])
            nc = _find_col(t.columns, ["Company","Name","Empresa"])
            if tc and nc and len(t) >= 5:
                df = t[[tc, nc]].copy()
                df.columns = ["ticker", "name"]
                df["ticker"] = df["ticker"].astype(str).str.strip()
                df["name"]   = df["name"].astype(str).str.strip()
                df = df[df["ticker"].str.match(r"^[\w]+$", na=False)]
                df["ticker"] = df["ticker"] + ".SA"
                df["is_etf"] = "N"
                print(f"  Ibovespa: {len(df)} titres")
                return df[["ticker", "name", "is_etf"]]
    except Exception as e:
        print(f"  ERREUR Ibovespa: {e}")
    print("  Ibovespa: non disponible")
    return pd.DataFrame()


def _fetch_wikipedia(label, url, ticker_hints, name_hints, suffix):
    # Parsers spéciaux
    if ticker_hints == ["__HANG_SENG__"]:
        return _fetch_hang_seng()
    if ticker_hints == ["__NIKKEI__"]:
        return _fetch_nikkei()
    if ticker_hints == ["__IBOVESPA__"]:
        return _fetch_ibovespa()

    try:
        r = _get(url)
        tables = pd.read_html(io.StringIO(r.text))
    except Exception as e:
        print(f"  ERREUR {label}: {e}")
        return pd.DataFrame()

    for table in tables:
        tc = _find_col(table.columns, ticker_hints)
        nc = _find_col(table.columns, name_hints)
        if not tc or not nc or len(table) < 5:
            continue

        df = table[[tc, nc]].copy()
        df.columns = ["ticker", "name"]
        df = df.dropna()
        df["ticker"] = df["ticker"].astype(str).str.strip()
        df["name"]   = df["name"].astype(str).str.strip()
        df = df[df["ticker"].str.match(r"^[\w\.\-]+$", na=False)]
        df = df[df["ticker"].str.len() <= 12]
        df = df[df["ticker"] != "nan"]
        df = df[df["name"]   != "nan"]
        if len(df) < 5:
            continue

        if suffix:
            df["ticker"] = df["ticker"].apply(
                lambda t: t if t.endswith(suffix) else t + suffix
            )
        df["is_etf"] = "N"
        print(f"  {label}: {len(df)} titres")
        return df[["ticker", "name", "is_etf"]]

    print(f"  {label}: aucune table valide (colonnes non trouvées)")
    return pd.DataFrame()


# ─── Mise à jour principale ───────────────────────────────────────────────────

def update_database():
    print("\n=== Mise à jour de la base mondiale des titres ===")
    all_frames = []

    # US complet
    us = _fetch_us_nasdaq()
    if not us.empty:
        all_frames.append(us)

    # Indices mondiaux
    for label, url, th, nh, suffix in WIKIPEDIA_SOURCES:
        df = _fetch_wikipedia(label, url, th, nh, suffix)
        if not df.empty:
            all_frames.append(df)

    # Cryptos
    crypto = pd.DataFrame([
        {"ticker": t, "name": n, "is_etf": "N"} for n, t in CRYPTO_STATIC
    ])
    all_frames.append(crypto)

    if not all_frames:
        print("Aucune source n'a fonctionné.")
        return

    all_stocks = pd.concat(all_frames, ignore_index=True)
    all_stocks = all_stocks.dropna(subset=["ticker", "name"])
    all_stocks["ticker"] = all_stocks["ticker"].str.strip()
    all_stocks["name"]   = all_stocks["name"].str.strip()
    all_stocks["is_etf"] = all_stocks["is_etf"].fillna("N").astype(str).str.strip()
    all_stocks["label"]  = all_stocks["name"] + " (" + all_stocks["ticker"] + ")"
    all_stocks = all_stocks.drop_duplicates(subset=["ticker"]).sort_values("name").reset_index(drop=True)

    conn = _get_conn()
    conn.execute("CREATE TABLE IF NOT EXISTS stocks (ticker TEXT PRIMARY KEY, name TEXT, label TEXT, is_etf TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS meta (last_update TEXT)")
    conn.execute("DELETE FROM stocks")
    conn.execute("DELETE FROM meta")
    all_stocks[["ticker", "name", "label", "is_etf"]].to_sql("stocks", conn, if_exists="replace", index=False)
    conn.execute("INSERT INTO meta VALUES (?)", (datetime.now().isoformat(),))
    conn.commit()
    conn.close()
    print(f"\n=== Base mise à jour : {len(all_stocks)} titres ===\n")


# ─── API publique ─────────────────────────────────────────────────────────────

def get_stock_options():
    if _db_needs_update():
        update_database()
    try:
        conn = _get_conn()
        df = pd.read_sql("SELECT ticker, label FROM stocks ORDER BY name", conn)
        conn.close()
        return [{"label": r["label"], "value": r["ticker"]} for _, r in df.iterrows()]
    except Exception as e:
        print(f"Erreur lecture DB : {e}")
        from stocks import STOCK_OPTIONS
        return STOCK_OPTIONS


def get_last_update():
    try:
        conn = _get_conn()
        row = conn.execute("SELECT last_update FROM meta LIMIT 1").fetchone()
        conn.close()
        if row:
            return datetime.fromisoformat(row[0]).strftime("%d/%m/%Y %H:%M")
    except Exception:
        pass
    return "Inconnue"


def get_stock_count():
    try:
        conn = _get_conn()
        count = conn.execute("SELECT COUNT(*) FROM stocks").fetchone()[0]
        conn.close()
        return count
    except Exception:
        return 0


def force_update():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    update_database()
