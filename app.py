import dash
from dash import dcc, html, Input, Output, State, dash_table
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import numpy as np
from scipy import stats as scipy_stats
from datetime import date, timedelta
import yfinance as yf
import optimization as opt
import metrics as m
from database import get_stock_options, get_last_update, get_stock_count
import json
import base64

# Chargement au démarrage (mise à jour si > 7 jours)
STOCK_OPTIONS = get_stock_options()
print(f"Titres disponibles : {get_stock_count()} | Dernière MAJ : {get_last_update()}")

# ─── Taux sans risque (Fed / US Treasury) ─────────────────────────────────────
RF_RATE_SOURCES = [
    {"label": "T-bill 3 mois (^IRX)",   "value": "^IRX"},
    {"label": "T-note 5 ans  (^FVX)",   "value": "^FVX"},
    {"label": "T-note 10 ans (^TNX)",   "value": "^TNX"},
    {"label": "T-bond 30 ans (^TYX)",   "value": "^TYX"},
]

def fetch_rf_rate(ticker="^IRX"):
    """Récupère le taux US courant via Yahoo Finance (en %)."""
    try:
        hist = yf.Ticker(ticker).history(period="5d")
        if not hist.empty:
            return round(float(hist['Close'].iloc[-1]), 2)
    except Exception:
        pass
    return 2.0

CURRENT_RF = fetch_rf_rate("^IRX")
print(f"Taux sans risque actuel (T-bill 3M) : {CURRENT_RF:.2f}%")

app = dash.Dash(__name__, external_stylesheets=[dbc.themes.DARKLY], suppress_callback_exceptions=True)
app.title = "Portfolio Analyzer"
server = app.server  # Exposé pour gunicorn

# Injecté APRÈS tous les CSS pour avoir la priorité absolue
app.index_string = '''<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>{%title%}</title>
        {%favicon%}
        <style>
        @media print {
            #_dash-configs, ._dash-loading { display: none !important; }
            .no-print { display: none !important; }
        }
        </style>
        {%css%}
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
        <script>
        (function() {
            var BG = "#1e2130";
            var BG_HOVER = "#2d3250";
            var TEXT = "#cccccc";
            var GREEN = "#00bc8c";
            var BORDER = "#555555";

            function applyStyles() {
                // Conteneur principal du Select
                document.querySelectorAll(".Select-control").forEach(function(el) {
                    el.style.setProperty("background-color", BG, "important");
                    el.style.setProperty("border-color", BORDER, "important");
                    el.style.setProperty("box-shadow", "none", "important");
                });
                // Texte de la valeur sélectionnée
                document.querySelectorAll(".Select-value-label, .Select-single-value").forEach(function(el) {
                    el.style.setProperty("color", "white", "important");
                });
                // Placeholder
                document.querySelectorAll(".Select-placeholder").forEach(function(el) {
                    el.style.setProperty("color", "#777", "important");
                });
                // Input de recherche
                document.querySelectorAll(".Select-input, .Select-input > input").forEach(function(el) {
                    el.style.setProperty("background-color", "transparent", "important");
                    el.style.setProperty("color", "white", "important");
                });
                // Menu déroulant
                document.querySelectorAll(".Select-menu-outer, .Select-menu").forEach(function(el) {
                    el.style.setProperty("background-color", BG, "important");
                    el.style.setProperty("border-color", BORDER, "important");
                    el.style.setProperty("z-index", "99999", "important");
                });
                // Options
                document.querySelectorAll(".Select-option, .VirtualizedSelectOption").forEach(function(el) {
                    el.style.setProperty("background-color", BG, "important");
                    el.style.setProperty("color", TEXT, "important");
                });
                // Option focused/hovered
                document.querySelectorAll(".Select-option.is-focused, .VirtualizedSelectFocusedOption").forEach(function(el) {
                    el.style.setProperty("background-color", BG_HOVER, "important");
                    el.style.setProperty("color", "white", "important");
                });
                // Option sélectionnée
                document.querySelectorAll(".Select-option.is-selected, .VirtualizedSelectSelectedOption").forEach(function(el) {
                    el.style.setProperty("background-color", "rgba(0,188,140,0.15)", "important");
                    el.style.setProperty("color", GREEN, "important");
                });
                // No results
                document.querySelectorAll(".Select-noresults").forEach(function(el) {
                    el.style.setProperty("background-color", BG, "important");
                    el.style.setProperty("color", "#777", "important");
                });
            }

            // Observer pour détecter les changements DOM de React
            var observer = new MutationObserver(function() {
                applyStyles();
            });

            document.addEventListener("DOMContentLoaded", function() {
                applyStyles();
                observer.observe(document.body, { childList: true, subtree: true });
            });
        })();
        </script>
    </body>
</html>'''


STOCK_MAP   = {opt["value"]: opt["label"] for opt in STOCK_OPTIONS}
STOCK_NAMES = {opt["label"] for opt in STOCK_OPTIONS}  # pour détecter une valeur déjà sélectionnée

BENCHMARK_OPTIONS = [
    {"label": "S&P 500 (SPY)",          "value": "SPY"},
    {"label": "Nasdaq 100 (QQQ)",        "value": "QQQ"},
    {"label": "Dow Jones (DIA)",         "value": "DIA"},
    {"label": "Russell 2000 (IWM)",      "value": "IWM"},
    {"label": "FTSE 100 (^FTSE)",        "value": "^FTSE"},
    {"label": "CAC 40 (^FCHI)",          "value": "^FCHI"},
    {"label": "DAX (^GDAXI)",            "value": "^GDAXI"},
    {"label": "Euro Stoxx 50 (^STOXX50E)", "value": "^STOXX50E"},
    {"label": "Nikkei 225 (^N225)",      "value": "^N225"},
    {"label": "Hang Seng (^HSI)",        "value": "^HSI"},
    {"label": "ASX 200 (^AXJO)",         "value": "^AXJO"},
    {"label": "TSX Canada (^GSPTSE)",    "value": "^GSPTSE"},
    {"label": "IBEX 35 (^IBEX)",         "value": "^IBEX"},
    {"label": "Nifty 50 (^NSEI)",        "value": "^NSEI"},
    {"label": "MSCI World (URTH)",       "value": "URTH"},
    {"label": "MSCI Emerging (EEM)",     "value": "EEM"},
    {"label": "Or (GLD)",                "value": "GLD"},
    {"label": "Bitcoin (BTC-USD)",       "value": "BTC-USD"},
]
BENCHMARK_MAP = {b["value"]: b["label"] for b in BENCHMARK_OPTIONS}

SELECT_STYLE_HIDDEN  = {"display": "none"}
SELECT_STYLE_VISIBLE = {
    "display": "block", "position": "absolute", "width": "100%",
    "zIndex": "9999", "borderTop": "none",
    "borderRadius": "0 0 4px 4px", "marginTop": "-2px", "maxHeight": "220px"
}

def _ticker_row(idx, ticker="", weight=10):
    display_name = STOCK_MAP.get(ticker, "") if ticker else ""
    return dbc.Row([
        dbc.Col([
            html.Div([
                dbc.Input(
                    id={"type": "ticker-search", "index": idx},
                    placeholder="Rechercher une action, ETF, crypto...",
                    value=display_name,
                    autocomplete="off",
                    style={"fontSize": "13px"},
                ),
                dbc.Select(
                    id={"type": "ticker-select", "index": idx},
                    options=[],
                    value=None,
                    size=8,
                    style=SELECT_STYLE_HIDDEN,
                ),
                dbc.Input(
                    id={"type": "ticker", "index": idx},
                    type="hidden",
                    value=ticker or "",
                ),
            ], style={"position": "relative"}),
        ], width=7),
        dbc.Col([
            dbc.Input(id={"type": "weight", "index": idx}, type='number',
                      value=weight, min=0, max=100, step=1,
                      placeholder='Poids %')
        ], width=3),
        dbc.Col([
            dbc.Button("✕", id={"type": "remove", "index": idx},
                       color="danger", outline=True, size="sm",
                       style={"padding": "2px 8px"})
        ], width=2),
    ], className="mb-2", id={"type": "row", "index": idx})

BG_CARD = "#1e2130"
BG_APP = "#111827"
GREEN = "#00bc8c"
RED = "#e74c3c"
ORANGE = "#f39c12"
BLUE = "#3498db"
PURPLE = "#9b59b6"

DEFAULT_ROWS = [
    {"ticker": "AAPL", "weight": 25},
    {"ticker": "MSFT", "weight": 25},
    {"ticker": "GOOGL", "weight": 20},
    {"ticker": "NVDA", "weight": 20},
    {"ticker": "SPY",  "weight": 10},
]

current_year = date.today().year
year_options = [{"label": str(y), "value": str(y)} for y in range(2000, current_year + 1)]
month_options = [
    {"label": m, "value": str(i).zfill(2)}
    for i, m in enumerate(
        ["Jan","Fév","Mar","Avr","Mai","Jun","Jul","Aoû","Sep","Oct","Nov","Déc"], 1
    )
]

app.layout = dbc.Container([

    dbc.Row([
        dbc.Col([
            html.H1("Portfolio Analyzer", className="text-center text-white my-4",
                    style={"fontWeight": "800", "letterSpacing": "2px"}),
            html.P("Analyse complète de votre portefeuille avec benchmark personnalisable",
                   className="text-center text-muted mb-4"),
        ])
    ]),

    # Config panel
    dbc.Card([
        dbc.CardHeader(dbc.Row([
            dbc.Col(html.H5("Configuration", className="text-white mb-0"), width="auto"),
            dbc.Col([
                dbc.Button("💾 Sauvegarder", id='save-config-btn', color="secondary", outline=True, size="sm", className="me-2"),
                dcc.Upload(
                    id='upload-config',
                    children=dbc.Button("📂 Charger", color="secondary", outline=True, size="sm", className="me-2"),
                    accept=".json",
                    style={"display": "inline-block"},
                ),
                dbc.Button("🖨 Exporter PDF", id='pdf-btn', color="secondary", outline=True, size="sm"),
            ], className="d-flex align-items-center justify-content-end"),
        ], justify="between", align="center")),
        dbc.CardBody([

            # Ticker table
            dbc.Row([
                dbc.Col([
                    dbc.Label("Actifs du portefeuille", className="text-white fw-bold mb-2"),
                    dbc.Row([
                        dbc.Col(html.Small("Actif", className="text-muted"), width=7),
                        dbc.Col(html.Small("Poids %", className="text-muted"), width=3),
                    ], className="mb-1"),
                    html.Div(id='ticker-rows', children=[
                        _ticker_row(i, r["ticker"], r["weight"])
                        for i, r in enumerate(DEFAULT_ROWS)
                    ]),
                    dbc.Button("+ Ajouter un actif", id='add-ticker-btn',
                               color="secondary", outline=True, size="sm", className="mt-2"),
                    html.Div(id='weight-total', className="mt-1"),
                    html.Small(
                        f"{get_stock_count()} titres · MAJ : {get_last_update()}",
                        className="text-muted d-block mt-1"
                    ),
                ], md=6),

                dbc.Col([
                    dbc.Label("Période d'analyse", className="text-white fw-bold mb-2"),
                    dbc.Row([
                        dbc.Col([
                            dbc.Label("Début", className="text-muted", style={"fontSize":"12px"}),
                            dbc.Row([
                                dbc.Col([
                                    dbc.Select(id='start-month', options=month_options,
                                               value=str(date.today().month).zfill(2))
                                ], width=6),
                                dbc.Col([
                                    dbc.Select(id='start-year', options=year_options,
                                               value=str(current_year - 5))
                                ], width=6),
                            ]),
                        ], md=6),
                        dbc.Col([
                            dbc.Label("Fin", className="text-muted", style={"fontSize":"12px"}),
                            dbc.Row([
                                dbc.Col([
                                    dbc.Select(id='end-month', options=month_options,
                                               value=str(date.today().month).zfill(2))
                                ], width=6),
                                dbc.Col([
                                    dbc.Select(id='end-year', options=year_options,
                                               value=str(current_year))
                                ], width=6),
                            ]),
                        ], md=6),
                    ]),
                    html.Br(),
                    dbc.Label("Benchmark", className="text-white fw-bold"),
                    dbc.Select(
                        id='benchmark-select',
                        options=BENCHMARK_OPTIONS,
                        value="SPY",
                    ),
                    html.Br(),
                    dbc.Label("Taux sans risque (%)", className="text-white fw-bold"),
                    dbc.Row([
                        dbc.Col([
                            dbc.Select(id='rf-source', options=RF_RATE_SOURCES, value="^IRX"),
                        ], width=8),
                        dbc.Col([
                            dbc.Button("↻", id='rf-fetch-btn', color="secondary", size="sm",
                                       className="w-100", title="Récupérer le taux actuel"),
                        ], width=4),
                    ], className="mb-1"),
                    dbc.Input(id='rf-input', type='number', value=CURRENT_RF, min=0, max=20, step=0.01),
                    html.Small(id='rf-label',
                               children=f"T-bill 3M actuel : {CURRENT_RF:.2f}% (source : Yahoo Finance)",
                               className="text-muted d-block mt-1"),
                ], md=6),
            ], className="mb-3"),

            dbc.Row([
                dbc.Col([
                    dbc.Label("Capital initial (optionnel)", className="text-white fw-bold"),
                    dbc.InputGroup([
                        dbc.Input(id='capital-input', type='number', value=10000, min=0, step=100, placeholder="Ex: 10000"),
                        dbc.InputGroupText("€"),
                    ]),
                    html.Small("Laissez vide pour une analyse en base 1", className="text-muted"),
                ], md=4),
                dbc.Col([
                    dbc.Button("Analyser le portefeuille", id='analyze-btn',
                               color="success", size="lg", className="w-100 mt-4"),
                ], md=4),
                dbc.Col([
                    html.Div(id='error-msg', className="text-danger mt-2")
                ], md=4),
            ])
        ])
    ], className="mb-4", style={"background": BG_CARD, "border": "1px solid #333"}),

    dcc.Store(id='n-rows', data=len(DEFAULT_ROWS)),
    dcc.Store(id='export-store'),
    dcc.Download(id='download-csv'),
    dcc.Download(id='download-config'),

    dcc.Loading(type="circle", color=GREEN, children=[
        html.Div(id='results-container')
    ])

], fluid=True, style={"background": BG_APP, "minHeight": "100vh", "padding": "20px"})


def metric_card(title, value, color=GREEN):
    return dbc.Col([
        dbc.Card([
            dbc.CardBody([
                html.P(title, className="text-muted mb-1", style={"fontSize": "0.75rem", "textTransform": "uppercase"}),
                html.H4(value, style={"color": color, "fontWeight": "bold", "margin": 0}),
            ], style={"textAlign": "center", "padding": "12px"})
        ], style={"background": BG_CARD, "border": f"1px solid {color}44"})
    ], md=3, sm=6, className="mb-3")


def fmt(val, pct=False, decimals=2):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "N/A"
    if pct:
        return f"{val * 100:.{decimals}f}%"
    return f"{val:.{decimals}f}"


def color_val(val, good_positive=True):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "#888"
    if good_positive:
        return GREEN if val >= 0 else RED
    return RED if val >= 0 else GREEN


CHART_LAYOUT = dict(
    template='plotly_dark',
    paper_bgcolor=BG_CARD,
    plot_bgcolor=BG_CARD,
    margin=dict(l=50, r=30, t=55, b=40),
    font=dict(size=12),
)


def _badge(text, color):
    return dbc.Badge(text, style={
        "backgroundColor": color, "color": "white",
        "fontSize": "0.7rem", "padding": "3px 8px", "borderRadius": "4px", "fontWeight": "600"
    })


def _rating(val, bounds, labels, colors):
    """bounds: ascending thresholds → returns (label, color)."""
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "N/A", "#888"
    for thresh, lbl, col in zip(bounds, labels, colors):
        if val <= thresh:
            return lbl, col
    return labels[-1], colors[-1]


def _insight_block(icon, text, color="#ccc"):
    return html.Div([
        html.Span(icon + " ", style={"marginRight": "4px"}),
        html.Span(text, style={"color": color, "fontSize": "0.82rem"}),
    ], className="mb-1")


def _analysis_card(title, content_rows, border_color=None):
    bc = border_color or "#2a2e45"
    return dbc.Card([
        dbc.CardHeader(
            html.H6(title, className="mb-0", style={"color": "#aab", "fontSize": "0.8rem", "textTransform": "uppercase", "letterSpacing": "1px"}),
            style={"background": "#13172a", "padding": "8px 16px", "border": f"none"}
        ),
        dbc.CardBody(content_rows, style={"padding": "12px 16px"}),
    ], style={"background": "#171b2d", "border": f"1px solid {bc}"}, className="mb-3")


def _metric_row(name, value_str, badge_lbl, badge_col, description):
    return dbc.Row([
        dbc.Col([
            html.Div(name, style={"color": "#aaa", "fontSize": "0.72rem", "textTransform": "uppercase", "letterSpacing": "0.5px"}),
            html.Div(value_str, style={"color": badge_col, "fontWeight": "700", "fontSize": "1.15rem", "lineHeight": "1.2"}),
            _badge(badge_lbl, badge_col),
        ], md=3, style={"borderRight": "1px solid #2a2e45", "paddingRight": "12px"}),
        dbc.Col([
            html.P(description, style={"color": "#bbc", "fontSize": "0.83rem", "marginBottom": "0", "lineHeight": "1.5"}),
        ], md=9, style={"paddingLeft": "14px"}),
    ], style={"borderBottom": "1px solid #1e2235", "paddingTop": "10px", "paddingBottom": "10px", "marginLeft": "0", "marginRight": "0"})


def _ff_sig_label(t):
    """Return significance stars based on t-stat."""
    at = abs(t)
    if at > 2.576:
        return "***"
    if at > 1.960:
        return "**"
    if at > 1.645:
        return "*"
    return ""


def _ff_factor_row(label, beta, t_stat, is_pct=False):
    val_str = f"{beta*100:.2f}%/an" if is_pct else f"{beta:.3f}"
    sig = _ff_sig_label(t_stat)
    col = GREEN if beta > 0 else (RED if beta < 0 else "#888")
    return html.Div([
        dbc.Row([
            dbc.Col(html.Span(label, style={"color": "#aaa", "fontSize": "0.8rem"}), width=6),
            dbc.Col(html.Span(val_str, style={"color": col, "fontWeight": "700", "fontSize": "0.85rem"}), width=3),
            dbc.Col(html.Span(f"t={t_stat:.2f}{sig}", style={"color": "#666", "fontSize": "0.75rem"}), width=3),
        ], align="center"),
    ], style={"borderBottom": "1px solid #1e2235", "padding": "5px 0"})


def _ff_bar_chart(ff_data):
    factors = ['MKT', 'SMB', 'HML']
    betas = [ff_data['mkt_beta'], ff_data['smb_beta'], ff_data['hml_beta']]
    t_stats = [ff_data['mkt_t'], ff_data['smb_t'], ff_data['hml_t']]
    colors = [GREEN if b >= 0 else RED for b in betas]
    # SE from t-stat and beta
    ses = [abs(b / t) if abs(t) > 0.01 else 0 for b, t in zip(betas, t_stats)]
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=factors, y=betas,
        marker_color=colors,
        error_y=dict(type='data', array=ses, visible=True, color="#888"),
        text=[f"{b:.3f}" for b in betas], textposition='outside',
        name='Beta',
    ))
    fig.add_hline(y=0, line_color="#555", line_width=1)
    fig.update_layout(
        title='Expositions factorielles (β)',
        yaxis_title='Beta',
        showlegend=False,
        **CHART_LAYOUT
    )
    return fig


def _ff_interpretation(ff_data):
    parts = []
    mkt = ff_data['mkt_beta']
    smb = ff_data['smb_beta']
    hml = ff_data['hml_beta']
    alpha = ff_data['alpha_annual']
    parts.append(
        f"Marché : β={mkt:.2f} — {'amplification' if mkt > 1.1 else ('atténuation' if mkt < 0.9 else 'neutre')} par rapport au marché. "
    )
    if abs(smb) > 0.1:
        parts.append(
            f"Taille : β={smb:.2f} — biais {'small-cap' if smb > 0 else 'large-cap'} détecté. "
        )
    if abs(hml) > 0.1:
        parts.append(
            f"Value : β={hml:.2f} — orientation {'value' if hml > 0 else 'croissance'} significative. "
        )
    parts.append(
        f"Alpha annualisé : {alpha*100:+.2f}%/an ({_ff_sig_label(ff_data['alpha_t'])} — "
        + (f"surperformance non expliquée par les facteurs." if alpha > 0 else f"sous-performance résiduelle.")
        + f" R²={ff_data['r2']*100:.1f}% de la variance expliquée par les 3 facteurs."
    )
    return " ".join(parts)


@app.callback(
    Output({"type": "ticker-select", "index": dash.MATCH}, "options"),
    Output({"type": "ticker-select", "index": dash.MATCH}, "style"),
    Input({"type": "ticker-search", "index": dash.MATCH}, "value"),
    prevent_initial_call=True
)
def filter_ticker_options(search):
    # Si l'input affiche un nom de stock déjà sélectionné, ne pas rouvrir la liste
    if not search or len(search) < 2 or search in STOCK_NAMES:
        return [], SELECT_STYLE_HIDDEN
    q = search.lower()
    matches = [opt for opt in STOCK_OPTIONS if q in opt["label"].lower()][:35]
    if not matches:
        return [], SELECT_STYLE_HIDDEN
    return matches, SELECT_STYLE_VISIBLE


@app.callback(
    Output({"type": "ticker-search", "index": dash.MATCH}, "value"),
    Output({"type": "ticker", "index": dash.MATCH}, "value"),
    Output({"type": "ticker-select", "index": dash.MATCH}, "style", allow_duplicate=True),
    Input({"type": "ticker-select", "index": dash.MATCH}, "value"),
    prevent_initial_call=True
)
def on_ticker_selected(selected):
    if not selected:
        return dash.no_update, dash.no_update, dash.no_update
    return STOCK_MAP.get(selected, selected), selected, SELECT_STYLE_HIDDEN


@app.callback(
    Output('ticker-rows', 'children'),
    Output('n-rows', 'data'),
    Input('add-ticker-btn', 'n_clicks'),
    Input({"type": "remove", "index": dash.ALL}, 'n_clicks'),
    State('ticker-rows', 'children'),
    State('n-rows', 'data'),
    prevent_initial_call=True
)
def manage_rows(add_clicks, remove_clicks, current_rows, n):
    ctx = dash.callback_context
    if not ctx.triggered:
        return current_rows, n
    trigger = ctx.triggered[0]['prop_id']
    if 'add-ticker-btn' in trigger:
        current_rows.append(_ticker_row(n))
        return current_rows, n + 1
    # Remove: rebuild rows excluding the clicked one
    import json
    triggered_id = json.loads(trigger.split('.')[0])
    idx_to_remove = triggered_id['index']
    new_rows = []
    for r in current_rows:
        row_id = r.get('props', {}).get('id', {})
        if isinstance(row_id, dict) and row_id.get('index') == idx_to_remove:
            continue
        new_rows.append(r)
    return new_rows, n


@app.callback(
    Output('weight-total', 'children'),
    Input({"type": "weight", "index": dash.ALL}, 'value'),
)
def update_weight_total(weights):
    total = sum(w for w in weights if w is not None)
    if total > 100:
        return [
            html.Span(f"Total : {total:.0f}% ", style={"color": RED, "fontWeight": "700", "fontSize": "0.85rem"}),
            dbc.Badge("⚠ Dépasse 100%", color="danger", style={"fontSize": "0.7rem"}),
        ]
    elif total == 100:
        return html.Span(f"Total : {total:.0f}% ✓", style={"color": GREEN, "fontWeight": "700", "fontSize": "0.85rem"})
    else:
        remaining = 100 - total
        return html.Span(f"Total : {total:.0f}% (reste {remaining:.0f}%)", style={"color": "#aaa", "fontSize": "0.85rem"})


@app.callback(
    Output('rf-input', 'value'),
    Output('rf-label', 'children'),
    Input('rf-fetch-btn', 'n_clicks'),
    State('rf-source', 'value'),
    prevent_initial_call=True
)
def update_rf_rate(n_clicks, source):
    ticker = source or "^IRX"
    rate = fetch_rf_rate(ticker)
    source_label = next((s["label"] for s in RF_RATE_SOURCES if s["value"] == ticker), ticker)
    return rate, f"{source_label} actuel : {rate:.2f}% (source : Yahoo Finance)"


@app.callback(
    Output('results-container', 'children'),
    Output('error-msg', 'children'),
    Output('export-store', 'data'),
    Input('analyze-btn', 'n_clicks'),
    State({"type": "ticker", "index": dash.ALL}, 'value'),
    State({"type": "weight", "index": dash.ALL}, 'value'),
    State('start-month', 'value'),
    State('start-year', 'value'),
    State('end-month', 'value'),
    State('end-year', 'value'),
    State('benchmark-select', 'value'),
    State('rf-input', 'value'),
    State('capital-input', 'value'),
    prevent_initial_call=True
)
def analyze(n_clicks, ticker_values, weight_values, start_month, start_year, end_month, end_year, benchmark_ticker, rf_rate, capital):
    start_date = f"{start_year}-{start_month}-01"
    end_date = f"{end_year}-{end_month}-01"
    tickers_str = ", ".join([t for t in ticker_values if t])
    weights_str = ", ".join([str(w) for w, t in zip(weight_values, ticker_values) if t and w is not None])
    try:
        tickers = [t.strip().upper() for t in tickers_str.split(',') if t.strip()]
        weights = [float(w.strip()) for w in weights_str.split(',') if w.strip()]

        if len(tickers) != len(weights):
            return None, f"Erreur : {len(tickers)} tickers mais {len(weights)} poids.", dash.no_update

        total_w = sum(weights)
        if total_w > 100:
            return None, f"Erreur : le total des poids est de {total_w:.0f}% — il ne peut pas dépasser 100%.", dash.no_update
        if total_w == 0:
            return None, "Erreur : tous les poids sont à 0%.", dash.no_update

        rf = float(rf_rate or 2.0) / 100
        bench = benchmark_ticker or 'SPY'
        bench_label = BENCHMARK_MAP.get(bench, bench)
        all_tickers = list(dict.fromkeys(tickers + [bench]))

        prices = m.download_data(all_tickers, start_date, end_date)
        missing = [t for t in tickers if t not in prices.columns]
        if missing:
            return None, f"Tickers introuvables : {', '.join(missing)}", dash.no_update
        if bench not in prices.columns:
            return None, f"Benchmark introuvable : {bench}", dash.no_update

        returns = m.calculate_returns(prices)
        port_prices = prices[tickers]
        port_returns_df = m.calculate_returns(port_prices)
        port_ret = m.portfolio_returns(port_returns_df, weights)
        bench_ret = returns[bench]
        w_norm = np.array(weights) / sum(weights)

        metrics = m.all_metrics(port_ret, bench_ret, rf)
        bench_metrics = m.all_metrics(bench_ret, bench_ret, rf)

        # ---- Prix en temps réel ----
        real_time_rows = []
        for t in tickers:
            try:
                info = yf.Ticker(t).fast_info
                price = round(float(info.last_price), 2)
                prev  = round(float(info.previous_close), 2)
                chg   = round((price - prev) / prev * 100, 2) if prev else 0
                real_time_rows.append({"Ticker": t, "Prix actuel": f"{price:,.2f}", "Variation j": f"{chg:+.2f}%"})
            except Exception:
                real_time_rows.append({"Ticker": t, "Prix actuel": "N/A", "Variation j": "N/A"})

        # ---- Charts ----

        # 1. Cumulative performance
        port_cum = (1 + port_ret).cumprod()
        bench_cum = (1 + bench_ret).cumprod()

        # ---- Capital réel ----
        cap = float(capital) if capital and capital > 0 else None
        fig_perf = go.Figure()
        fig_perf.add_trace(go.Scatter(x=port_cum.index, y=port_cum.values,
                                      name='Portefeuille', line=dict(color=GREEN, width=2.5)))
        fig_perf.add_trace(go.Scatter(x=bench_cum.index, y=bench_cum.values,
                                      name=bench_label, line=dict(color=RED, width=2, dash='dash')))
        fig_perf.update_layout(title='Performance Cumulée (base 1)', yaxis_title='Valeur', **CHART_LAYOUT)

        # 2. Drawdown
        port_dd = m.drawdown_series(port_ret)
        bench_dd = m.drawdown_series(bench_ret)
        fig_dd = go.Figure()
        fig_dd.add_trace(go.Scatter(x=port_dd.index, y=port_dd.values * 100,
                                    name='Portefeuille', fill='tozeroy',
                                    line=dict(color=ORANGE), fillcolor='rgba(243,156,18,0.15)'))
        fig_dd.add_trace(go.Scatter(x=bench_dd.index, y=bench_dd.values * 100,
                                    name=bench_label, line=dict(color=RED, dash='dash')))
        fig_dd.update_layout(title='Drawdown (%)', yaxis_title='Drawdown (%)', **CHART_LAYOUT)

        # 3. Allocation donut
        fig_alloc = go.Figure(go.Pie(
            labels=tickers, values=w_norm * 100, hole=0.45,
            marker=dict(colors=px.colors.qualitative.Pastel),
            textinfo='label+percent'
        ))
        fig_alloc.update_layout(title='Allocation', **CHART_LAYOUT)

        # 4. Correlation heatmap
        corr = port_returns_df.corr()
        fig_corr = go.Figure(go.Heatmap(
            z=corr.values, x=corr.columns, y=corr.index,
            colorscale='RdYlGn', zmin=-1, zmax=1,
            text=np.round(corr.values, 2), texttemplate='%{text}',
        ))
        fig_corr.update_layout(title='Corrélation entre actifs', **CHART_LAYOUT)

        # 5. Rolling Sharpe
        rolling_sh = (port_ret.rolling(252).mean() / port_ret.rolling(252).std()) * np.sqrt(252)
        fig_rolling = go.Figure()
        fig_rolling.add_trace(go.Scatter(x=rolling_sh.index, y=rolling_sh.values,
                                         name='Sharpe Glissant', line=dict(color=BLUE)))
        fig_rolling.add_hline(y=1, line_dash='dash', line_color='green',
                               annotation_text='Bon (1.0)', annotation_position='bottom right')
        fig_rolling.add_hline(y=0, line_dash='dash', line_color='red')
        fig_rolling.update_layout(title='Sharpe Ratio Glissant (252 jours)', yaxis_title='Sharpe', **CHART_LAYOUT)

        # 6. Monthly returns heatmap
        monthly = port_ret.resample('ME').apply(lambda x: (1 + x).prod() - 1)
        mdf = monthly.to_frame('ret')
        mdf['year'] = mdf.index.year
        mdf['month'] = mdf.index.month
        pivot = mdf.pivot(index='year', columns='month', values='ret')
        months = ['Jan', 'Fév', 'Mar', 'Avr', 'Mai', 'Jun', 'Jul', 'Aoû', 'Sep', 'Oct', 'Nov', 'Déc']
        pivot.columns = [months[c - 1] for c in pivot.columns]
        fig_monthly = go.Figure(go.Heatmap(
            z=pivot.values * 100, x=pivot.columns, y=pivot.index.astype(str),
            colorscale='RdYlGn', zmid=0,
            text=np.round(pivot.values * 100, 1), texttemplate='%{text}%',
            colorbar=dict(title='%')
        ))
        fig_monthly.update_layout(title='Rendements Mensuels (%)', **CHART_LAYOUT)

        # 7. Returns distribution
        fig_dist = go.Figure()
        fig_dist.add_trace(go.Histogram(x=port_ret.values * 100, nbinsx=80, name='Portefeuille',
                                         marker_color=GREEN, opacity=0.7))
        fig_dist.add_trace(go.Histogram(x=bench_ret.values * 100, nbinsx=80, name=bench_label,
                                         marker_color=RED, opacity=0.5))
        var_line = m.value_at_risk(port_ret) * 100
        fig_dist.add_vline(x=var_line, line_dash='dash', line_color=ORANGE,
                            annotation_text=f'VaR 95%: {var_line:.2f}%')
        fig_dist.update_layout(title='Distribution des Rendements Journaliers (%)',
                                xaxis_title='Rendement (%)', yaxis_title='Fréquence',
                                barmode='overlay', **CHART_LAYOUT)

        # ---- Metric cards ----
        PCT_KEYS = {'CAGR', 'Volatilité', 'Max Drawdown', 'VaR 95%', 'CVaR 95%', 'Alpha (annualisé)'}
        cards_data = [
            ("CAGR", fmt(metrics['CAGR'], pct=True), color_val(metrics['CAGR'])),
            ("Volatilité", fmt(metrics['Volatilité'], pct=True), ORANGE),
            ("Sharpe Ratio", fmt(metrics['Sharpe Ratio']), color_val(metrics['Sharpe Ratio'])),
            ("Sortino Ratio", fmt(metrics['Sortino Ratio']), color_val(metrics['Sortino Ratio'])),
            ("Max Drawdown", fmt(metrics['Max Drawdown'], pct=True), color_val(metrics['Max Drawdown'], False)),
            ("Calmar Ratio", fmt(metrics['Calmar Ratio']), color_val(metrics['Calmar Ratio'])),
            ("VaR 95%", fmt(metrics['VaR 95%'], pct=True), RED),
            ("CVaR 95%", fmt(metrics['CVaR 95%'], pct=True), RED),
            ("Beta", fmt(metrics['Beta']), BLUE),
            ("Alpha (annualisé)", fmt(metrics['Alpha (annualisé)'], pct=True), color_val(metrics['Alpha (annualisé)'])),
            ("R²", fmt(metrics['R²']), PURPLE),
            ("Information Ratio", fmt(metrics['Information Ratio']), color_val(metrics['Information Ratio'])),
        ]

        # ---- Insights stats ----
        # Performance
        port_final = port_cum.iloc[-1]
        bench_final = bench_cum.iloc[-1]
        outperf_total = (port_final - bench_final) / bench_final * 100
        months_outperf = (port_ret > bench_ret).sum() / len(port_ret) * 100

        # Drawdown
        n_dd_10 = int((port_dd < -0.10).sum())

        # Rolling Sharpe
        rs_valid = rolling_sh.dropna()
        pct_rs_above1 = (rs_valid > 1).sum() / len(rs_valid) * 100 if len(rs_valid) > 0 else 0
        rs_current = rs_valid.iloc[-1] if len(rs_valid) > 0 else np.nan
        rs_trend = (rs_valid.iloc[-63:].mean() - rs_valid.iloc[-252:-63].mean()) if len(rs_valid) > 252 else np.nan

        # Monthly
        flat_vals = pivot.values.flatten()
        flat_clean = flat_vals[~np.isnan(flat_vals)] * 100
        best_month_val = flat_clean.max() if len(flat_clean) > 0 else np.nan
        worst_month_val = flat_clean.min() if len(flat_clean) > 0 else np.nan
        pos_months_pct = (flat_clean > 0).sum() / len(flat_clean) * 100 if len(flat_clean) > 0 else np.nan
        annual_rets = mdf.groupby('year')['ret'].apply(lambda x: (1 + x).prod() - 1) * 100
        best_year = int(annual_rets.idxmax()) if len(annual_rets) > 0 else "N/A"
        worst_year = int(annual_rets.idxmin()) if len(annual_rets) > 0 else "N/A"
        best_year_val = annual_rets.max() if len(annual_rets) > 0 else np.nan
        worst_year_val = annual_rets.min() if len(annual_rets) > 0 else np.nan

        # Distribution
        port_clean = port_ret.dropna()
        skewness = scipy_stats.skew(port_clean)
        kurt = scipy_stats.kurtosis(port_clean)  # excess kurtosis

        # Correlation
        if len(tickers) > 1:
            corr_upper = corr.where(np.triu(np.ones(corr.shape), k=1).astype(bool)).stack()
            max_corr_pair = corr_upper.idxmax()
            max_corr_val = corr_upper.max()
            min_corr_pair = corr_upper.idxmin()
            min_corr_val = corr_upper.min()
            avg_corr = corr_upper.mean()
        else:
            max_corr_pair = min_corr_pair = ("—", "—")
            max_corr_val = min_corr_val = avg_corr = np.nan

        # ---- Metric analysis accordion ----
        sr = metrics['Sharpe Ratio']
        so = metrics['Sortino Ratio']
        cagr = metrics['CAGR']
        vol = metrics['Volatilité']
        mdd_v = metrics['Max Drawdown']
        calmar = metrics['Calmar Ratio']
        var95 = metrics['VaR 95%']
        cvar95 = metrics['CVaR 95%']
        beta = metrics['Beta']
        alpha = metrics['Alpha (annualisé)']
        r2 = metrics['R²']
        ir = metrics['Information Ratio']

        sr_lbl, sr_col = _rating(sr, [0, 0.5, 1, 2], ["Négatif","Faible","Acceptable","Bon","Excellent"], [RED,RED,ORANGE,BLUE,GREEN])
        so_lbl, so_col = _rating(so, [0, 0.5, 1, 2], ["Négatif","Faible","Acceptable","Bon","Excellent"], [RED,RED,ORANGE,BLUE,GREEN])
        cagr_lbl, cagr_col = _rating(cagr, [0, 0.05, 0.10, 0.20], ["Négatif","Faible","Modéré","Bon","Excellent"], [RED,ORANGE,ORANGE,BLUE,GREEN])
        vol_lbl, vol_col = _rating(vol, [0.10, 0.15, 0.25, 0.40], ["Très faible","Faible","Modérée","Élevée","Très élevée"], [BLUE,GREEN,ORANGE,RED,RED])
        mdd_lbl, mdd_col = _rating(mdd_v, [-0.40, -0.25, -0.15, -0.05], ["Catastrophique","Sévère","Modéré","Faible","Minimal"], [RED,RED,ORANGE,BLUE,GREEN])
        cal_lbl, cal_col = _rating(calmar, [0, 0.5, 1, 2], ["Négatif","Faible","Acceptable","Bon","Excellent"], [RED,RED,ORANGE,BLUE,GREEN])
        ir_lbl, ir_col = _rating(ir, [0, 0.3, 0.5, 1.0], ["Négatif","Faible","Acceptable","Bon","Excellent"], [RED,RED,ORANGE,BLUE,GREEN])

        beta_lbl = "Agressif" if beta > 1.2 else ("Défensif" if beta < 0.8 else "Neutre")
        beta_col = RED if beta > 1.2 else (GREEN if beta < 0.8 else BLUE)
        alpha_lbl = "Positif" if alpha > 0 else "Négatif"
        alpha_col = GREEN if alpha > 0 else RED
        r2_lbl = "Très corrélé" if r2 > 0.9 else ("Corrélé" if r2 > 0.7 else ("Partiellement" if r2 > 0.4 else "Peu corrélé"))
        r2_col = RED if r2 > 0.9 else (ORANGE if r2 > 0.7 else (BLUE if r2 > 0.4 else GREEN))

        b_cagr = bench_metrics['CAGR']
        b_vol = bench_metrics['Volatilité']
        b_mdd = bench_metrics['Max Drawdown']
        b_sr = bench_metrics['Sharpe Ratio']

        metric_rows = [
            _metric_row("CAGR", fmt(cagr, pct=True), cagr_lbl, cagr_col,
                f"Le taux de croissance annuel composé est de {cagr*100:.2f}%/an, contre {b_cagr*100:.2f}%/an pour {bench_label}. "
                + (f"Le portefeuille surperforme de +{(cagr-b_cagr)*100:.2f}%/an." if cagr > b_cagr else f"Il sous-performe de {(cagr-b_cagr)*100:.2f}%/an.")
                + " Un CAGR > 10%/an est historiquement solide sur les marchés actions."),
            _metric_row("Volatilité", fmt(vol, pct=True), vol_lbl, vol_col,
                f"Volatilité annualisée de {vol*100:.2f}%, contre {b_vol*100:.2f}% pour {bench_label}. "
                + (f"Le portefeuille est plus risqué que le benchmark (+{(vol-b_vol)*100:.2f}%)." if vol > b_vol else f"Il est plus stable que le benchmark ({(b_vol-vol)*100:.2f}% de vol en moins).")
                + " En dessous de 15% : faible ; 15-25% : modérée ; au-delà : élevée."),
            _metric_row("Sharpe Ratio", fmt(sr), sr_lbl, sr_col,
                f"Rendement excédentaire par unité de risque total : {sr:.2f} (benchmark : {b_sr:.2f}). "
                + (f"Supérieur au benchmark de +{sr-b_sr:.2f}." if sr > b_sr else f"Inférieur au benchmark de {sr-b_sr:.2f}.")
                + " Règle : < 0.5 = faible, 0.5–1 = acceptable, 1–2 = bon, > 2 = excellent."),
            _metric_row("Sortino Ratio", fmt(so), so_lbl, so_col,
                f"Le Sortino ({so:.2f}) ne pénalise que la volatilité baissière, contrairement au Sharpe. "
                + (f"Sortino > Sharpe ({so:.2f} vs {sr:.2f}) : les variations extrêmes sont surtout haussières — signe favorable." if so > sr else f"Sortino < Sharpe ({so:.2f} vs {sr:.2f}) : les mouvements extrêmes sont principalement à la baisse.")
                + " Un Sortino élevé indique une gestion efficace du risque de perte."),
            _metric_row("Max Drawdown", fmt(mdd_v, pct=True), mdd_lbl, mdd_col,
                f"La pire perte depuis un pic est de {mdd_v*100:.2f}% (benchmark : {b_mdd*100:.2f}%). "
                f"Pour récupérer d'un MDD de {abs(mdd_v)*100:.0f}%, il faut une hausse de {(1/(1+mdd_v)-1)*100:.0f}%. "
                f"Sur la période, {n_dd_10} jours sous -10% ont été observés."),
            _metric_row("Calmar Ratio", fmt(calmar), cal_lbl, cal_col,
                f"Rapport CAGR / |Max Drawdown| = {calmar:.2f}. "
                + (f"Chaque point de drawdown maximal est compensé par {calmar:.2f}% de rendement annuel — gestion du risque efficace." if calmar > 1 else f"Le rendement annuel ne compense pas encore le drawdown maximal subi — ratio à améliorer.")
                + " Un Calmar > 1 est la cible pour un portefeuille bien géré."),
            _metric_row("VaR 95%", fmt(var95, pct=True), "Risque quotidien", RED if abs(var95) > 0.03 else ORANGE,
                f"Dans 95% des séances, la perte journalière ne dépassera pas {abs(var95)*100:.2f}%. "
                f"Sur une année (~252 jours), cela représente environ {abs(var95)*100*np.sqrt(252):.1f}% de perte potentielle en conditions extrêmes. "
                f"La VaR suppose une distribution normale — elle peut sous-estimer les queues de distribution."),
            _metric_row("CVaR 95%", fmt(cvar95, pct=True), "Perte extrême", RED,
                f"Au-delà du seuil de VaR (5% pires jours), la perte moyenne attendue est de {abs(cvar95)*100:.2f}%. "
                f"Le CVaR ({abs(cvar95)*100:.2f}%) est {abs(cvar95/var95):.1f}× la VaR ({abs(var95)*100:.2f}%), "
                + ("ce rapport proche de 1.3 est normal pour une distribution gaussienne." if abs(cvar95/var95) < 1.5 else "ce rapport élevé révèle des queues de distribution épaisses (risque de pertes extrêmes plus important que prévu).")),
            _metric_row("Beta", fmt(beta), beta_lbl, beta_col,
                f"Sensibilité au benchmark {bench_label} : β = {beta:.2f}. "
                + (f"Quand le benchmark progresse de 1%, le portefeuille tend à progresser de {beta:.2f}% (+{(beta-1)*100:.0f}% d'amplification)." if beta > 1 else f"Le portefeuille atténue les mouvements du marché ({beta:.2f}% pour 1% du benchmark).")
                + " Beta > 1.2 = agressif, 0.8–1.2 = neutre, < 0.8 = défensif."),
            _metric_row("Alpha (annualisé)", fmt(alpha, pct=True), alpha_lbl, alpha_col,
                f"Surperformance annualisée au-delà de ce qu'explique le beta : {alpha*100:.2f}%/an. "
                + (f"L'alpha positif indique que le portefeuille crée de la valeur indépendamment du mouvement du marché." if alpha > 0 else f"L'alpha négatif signifie que la prise de risque de marché (beta) n'est pas suffisamment récompensée par une sélection active.")
                + f" CAPM : Rendement attendu = Rf + β × (Rm - Rf) ; l'alpha est l'écart réel."),
            _metric_row("R²", fmt(r2), r2_lbl, r2_col,
                f"R² = {r2:.2f} : {r2*100:.0f}% de la variance du portefeuille est expliquée par {bench_label}. "
                + (f"Le portefeuille se comporte presque comme un ETF passif ({r2*100:.0f}% d'exposition indicielle) — faible valeur ajoutée par la sélection active." if r2 > 0.85 else f"Le portefeuille a une dynamique propre significative ({(1-r2)*100:.0f}% de variance idiosyncrasique) — la sélection active joue un rôle important.")),
            _metric_row("Information Ratio", fmt(ir), ir_lbl, ir_col,
                f"Excès de rendement sur benchmark divisé par le tracking error : {ir:.2f}. "
                + (f"Un IR de {ir:.2f} est considéré comme {'excellent (> 1.0)' if ir > 1 else 'bon (0.5–1.0)' if ir > 0.5 else 'acceptable (0.3–0.5)' if ir > 0.3 else 'faible'}. "
                   f"{months_outperf:.0f}% des jours, le portefeuille surperforme le benchmark." if not np.isnan(ir) else "")),
        ]

        metric_analysis_card = _analysis_card("Analyse détaillée des métriques", metric_rows, GREEN + "44")

        # ---- Chart insight cards ----
        # Performance insight
        perf_color = GREEN if port_final > bench_final else RED
        perf_insights = [
            _insight_block("📈", f"Valeur finale du portefeuille : {port_final:.2f}× (base 1) — {(port_final-1)*100:.1f}% de gain total.", perf_color),
            _insight_block("📊", f"{bench_label} : {bench_final:.2f}× — {(bench_final-1)*100:.1f}% sur la même période."),
            _insight_block("⚖️", f"Écart de performance : {outperf_total:+.1f}% par rapport au benchmark.", perf_color),
            _insight_block("🗓️", f"Le portefeuille surperforme le benchmark {months_outperf:.0f}% des jours (sur {len(port_ret)} séances analysées)."),
        ]
        perf_insight_card = _analysis_card("Analyse — Performance Cumulée", perf_insights, perf_color + "55")

        # Drawdown insight
        dd_insights = [
            _insight_block("📉", f"Drawdown maximum du portefeuille : {mdd_v*100:.2f}% (benchmark : {b_mdd*100:.2f}%).", RED if mdd_v < b_mdd else GREEN),
            _insight_block("🔢", f"Jours consécutifs sous -10% : {n_dd_10}. Plus ce nombre est élevé, plus les périodes de stress sont longues."),
            _insight_block("🔄", f"Pour récupérer d'un drawdown de {abs(mdd_v)*100:.0f}%, une hausse de {(1/(1+mdd_v)-1)*100:.0f}% est nécessaire."),
            _insight_block("💡", "Comparez les zones colorées : un portefeuille bien géré a des drawdowns plus courts et moins profonds que le benchmark."),
        ]
        dd_insight_card = _analysis_card("Analyse — Drawdown", dd_insights, ORANGE + "55")

        # Rolling Sharpe insight
        rs_trend_txt = ("tendance haussière récente (+{:.2f} sur 3 mois vs période précédente)".format(rs_trend) if not np.isnan(rs_trend) and rs_trend > 0.1
                        else ("tendance baissière récente ({:.2f})".format(rs_trend) if not np.isnan(rs_trend) and rs_trend < -0.1
                              else "tendance stable sur les derniers mois"))
        rs_insights = [
            _insight_block("📊", f"Sharpe glissant actuel (252j) : {rs_current:.2f}." if not np.isnan(rs_current) else "Données insuffisantes pour le Sharpe glissant.", GREEN if (not np.isnan(rs_current) and rs_current > 1) else ORANGE),
            _insight_block("⏱️", f"{pct_rs_above1:.0f}% du temps, le Sharpe glissant est supérieur à 1 — zone de bonne performance ajustée au risque.", GREEN if pct_rs_above1 > 50 else ORANGE),
            _insight_block("📈", f"Tendance : {rs_trend_txt}."),
            _insight_block("💡", "Un Sharpe glissant qui reste durablement au-dessus de 1 signale un portefeuille robuste. En dessous de 0 : le portefeuille détruit de la valeur."),
        ]
        rs_insight_card = _analysis_card("Analyse — Sharpe Glissant", rs_insights, BLUE + "55")

        # Correlation insight
        if len(tickers) > 1:
            corr_col = RED if avg_corr > 0.7 else (ORANGE if avg_corr > 0.4 else GREEN)
            corr_insights = [
                _insight_block("🔗", f"Corrélation moyenne entre les actifs : {avg_corr:.2f}.", corr_col),
                _insight_block("⬆️", f"Paire la plus corrélée : {max_corr_pair[0]} / {max_corr_pair[1]} ({max_corr_val:.2f}) — évoluent souvent ensemble.", RED),
                _insight_block("⬇️", f"Paire la moins corrélée : {min_corr_pair[0]} / {min_corr_pair[1]} ({min_corr_val:.2f}) — meilleure diversification.", GREEN),
                _insight_block("💡", "Une corrélation élevée (> 0.8) signifie peu de diversification réelle. Idéalement, un portefeuille équilibré a une corrélation moyenne < 0.5."),
            ]
        else:
            corr_insights = [_insight_block("ℹ️", "Ajoutez au moins 2 actifs pour analyser la corrélation.")]
        corr_insight_card = _analysis_card("Analyse — Corrélation", corr_insights, PURPLE + "55")

        # Monthly insight
        mon_insights = [
            _insight_block("🏆", f"Meilleur mois : +{best_month_val:.1f}%  |  Pire mois : {worst_month_val:.1f}%.", GREEN),
            _insight_block("📅", f"Meilleure année : {best_year} (+{best_year_val:.1f}%)  |  Pire année : {worst_year} ({worst_year_val:.1f}%)."),
            _insight_block("✅", f"{pos_months_pct:.0f}% des mois sont positifs — {'bonne régularité' if pos_months_pct > 58 else 'régularité à améliorer'}.", GREEN if pos_months_pct > 58 else ORANGE),
            _insight_block("💡", "Les cases rouges concentrées révèlent des périodes de stress systémique (ex : crise). Des cases vertes régulières indiquent une performance constante."),
        ]
        mon_insight_card = _analysis_card("Analyse — Rendements Mensuels", mon_insights, GREEN + "33")

        # Distribution insight
        skew_txt = ("positive (asymétrie vers le haut — plus de gros gains que de grosses pertes)" if skewness > 0.3
                    else ("négative (asymétrie vers le bas — risque de pertes extrêmes plus élevé)" if skewness < -0.3
                          else "quasi-symétrique (proche de la normale)"))
        kurt_txt = ("leptokurtique (queues épaisses — pertes/gains extrêmes plus fréquents qu'une distribution normale)" if kurt > 1
                    else ("platykurtique (queues fines — moins d'événements extrêmes)" if kurt < -0.5
                          else "mésokurtique (distribution proche de la normale)"))
        dist_insights = [
            _insight_block("↔️", f"Asymétrie (skewness) : {skewness:.2f} — distribution {skew_txt}.", GREEN if skewness > 0 else ORANGE),
            _insight_block("📐", f"Aplatissement (kurtosis excédentaire) : {kurt:.2f} — {kurt_txt}.", RED if kurt > 1 else GREEN),
            _insight_block("📊", f"VaR 95% tracée à {var95*100:.2f}% : seuil en-dessous duquel se situent les 5% pires séances."),
            _insight_block("💡", "Une skewness positive et un kurtosis faible sont idéaux : beaucoup de petits gains, peu de grosses pertes. L'inverse caractérise les stratégies à risque de ruine."),
        ]
        dist_insight_card = _analysis_card("Analyse — Distribution des Rendements", dist_insights, RED + "33")

        # ---- Asset contributions ----
        ret_contrib, risk_contrib, contrib_tickers = m.asset_contributions(port_returns_df, weights)
        fig_contrib = go.Figure()
        fig_contrib.add_trace(go.Bar(
            name='Contribution au rendement',
            x=contrib_tickers, y=ret_contrib * 100,
            marker_color=[GREEN if v >= 0 else RED for v in ret_contrib],
            text=[f"{v*100:+.2f}%" for v in ret_contrib], textposition='outside',
        ))
        fig_contrib.add_trace(go.Bar(
            name='Contribution au risque',
            x=contrib_tickers, y=risk_contrib * 100,
            marker_color=[f"rgba(52,152,219,0.7)" for _ in risk_contrib],
            text=[f"{v*100:.2f}%" for v in risk_contrib], textposition='outside',
        ))
        fig_contrib.update_layout(title='Contribution par actif (rendement & risque annualisés)',
                                   yaxis_title='%', barmode='group', **CHART_LAYOUT)

        # ---- Monte Carlo ----
        mc_paths = m.monte_carlo_simulation(port_ret, n_simulations=300, n_years=10)
        mc_years = np.linspace(0, 10, mc_paths.shape[1])
        p10  = np.percentile(mc_paths, 10, axis=0)
        p25  = np.percentile(mc_paths, 25, axis=0)
        p50  = np.percentile(mc_paths, 50, axis=0)
        p75  = np.percentile(mc_paths, 75, axis=0)
        p90  = np.percentile(mc_paths, 90, axis=0)
        mc_cap = cap if cap else 1
        fig_mc = go.Figure()
        fig_mc.add_trace(go.Scatter(x=mc_years, y=p90 * mc_cap, name='90e percentile',
                                    line=dict(color='rgba(0,188,140,0.3)', width=0),
                                    fill=None, showlegend=False))
        fig_mc.add_trace(go.Scatter(x=mc_years, y=p10 * mc_cap, name='Intervalle 80%',
                                    line=dict(color='rgba(0,188,140,0.3)', width=0),
                                    fill='tonexty', fillcolor='rgba(0,188,140,0.08)'))
        fig_mc.add_trace(go.Scatter(x=mc_years, y=p75 * mc_cap, name='75e percentile',
                                    line=dict(color='rgba(0,188,140,0.5)', width=0),
                                    fill=None, showlegend=False))
        fig_mc.add_trace(go.Scatter(x=mc_years, y=p25 * mc_cap, name='Intervalle 50%',
                                    line=dict(color='rgba(0,188,140,0.5)', width=0),
                                    fill='tonexty', fillcolor='rgba(0,188,140,0.15)'))
        fig_mc.add_trace(go.Scatter(x=mc_years, y=p50 * mc_cap, name='Médiane (50e)',
                                    line=dict(color=GREEN, width=2.5)))
        mc_label = f"{p50[-1] * mc_cap:,.0f}{'€' if cap else '×'}"
        mc_p10_label = f"{p10[-1] * mc_cap:,.0f}{'€' if cap else '×'}"
        mc_p90_label = f"{p90[-1] * mc_cap:,.0f}{'€' if cap else '×'}"
        fig_mc.update_layout(
            title=f'Monte Carlo — 300 simulations sur 10 ans (bootstrap historique)',
            xaxis_title='Années', yaxis_title='€' if cap else 'Valeur (base 1)',
            **CHART_LAYOUT
        )

        # ---- Stress testing ----
        STRESS_PERIODS = [
            ("Dot-com Crash",        "2000-03-10", "2002-10-09"),
            ("Crise financière 2008","2008-09-01", "2009-03-09"),
            ("Flash Crash (2010)",   "2010-05-06", "2010-07-01"),
            ("COVID-19 (2020)",      "2020-02-19", "2020-03-23"),
            ("Hausse taux 2022",     "2022-01-03", "2022-12-30"),
        ]
        stress_rows = []
        for crisis_name, s_start, s_end in STRESS_PERIODS:
            mask = (port_ret.index >= s_start) & (port_ret.index <= s_end)
            bench_mask = (bench_ret.index >= s_start) & (bench_ret.index <= s_end)
            if mask.sum() < 5:
                stress_rows.append({"Crise": crisis_name, "Portefeuille": "Hors période",
                                     bench_label: "Hors période", "Écart": "—"})
                continue
            p_ret = (1 + port_ret[mask]).prod() - 1
            b_ret = (1 + bench_ret[bench_mask]).prod() - 1 if bench_mask.sum() >= 5 else np.nan
            ecart = p_ret - b_ret if not np.isnan(b_ret) else np.nan
            stress_rows.append({
                "Crise": crisis_name,
                "Portefeuille": f"{p_ret*100:+.1f}%",
                bench_label: f"{b_ret*100:+.1f}%" if not np.isnan(b_ret) else "N/A",
                "Écart": f"{ecart*100:+.1f}%" if not np.isnan(ecart) else "N/A",
            })

        # ---- Efficient frontier ----
        ef_data = None
        if len(tickers) >= 2:
            try:
                ef_data = opt.efficient_frontier(port_returns_df, rf=rf, n_random=400)
            except Exception:
                ef_data = None

        # ---- Factor Analysis (Fama-French 3 facteurs) ----
        ff_data = m.fama_french_proxy(port_ret)

        if ef_data:
            port_vol_pct = metrics['Volatilité'] * 100
            port_ret_pct = metrics['CAGR'] * 100
            fig_ef = go.Figure()
            fig_ef.add_trace(go.Scatter(
                x=ef_data['rand_vols'], y=ef_data['rand_rets'],
                mode='markers', name='Portefeuilles aléatoires',
                marker=dict(color=ef_data['rand_sharpes'], colorscale='RdYlGn',
                            size=5, opacity=0.5,
                            colorbar=dict(title='Sharpe')),
            ))
            if ef_data['front_vols']:
                fig_ef.add_trace(go.Scatter(
                    x=ef_data['front_vols'], y=ef_data['front_rets'],
                    mode='lines', name='Frontière efficiente',
                    line=dict(color=GREEN, width=2.5),
                ))
            fig_ef.add_trace(go.Scatter(
                x=[ef_data['opt_sharpe']['vol']], y=[ef_data['opt_sharpe']['ret']],
                mode='markers', name=f"Max Sharpe ({ef_data['opt_sharpe']['sharpe']:.2f})",
                marker=dict(symbol='star', size=16, color=GREEN),
            ))
            fig_ef.add_trace(go.Scatter(
                x=[ef_data['opt_minvol']['vol']], y=[ef_data['opt_minvol']['ret']],
                mode='markers', name='Min Volatilité',
                marker=dict(symbol='diamond', size=12, color=BLUE),
            ))
            fig_ef.add_trace(go.Scatter(
                x=[port_vol_pct], y=[port_ret_pct],
                mode='markers', name='Votre portefeuille',
                marker=dict(symbol='circle', size=14, color=ORANGE,
                            line=dict(color='white', width=2)),
            ))
            fig_ef.update_layout(
                title='Frontière Efficiente de Markowitz',
                xaxis_title='Volatilité annualisée (%)',
                yaxis_title='Rendement annualisé (%)',
                **CHART_LAYOUT
            )

            # Optimal weights suggestion
            opt_sh_w = ef_data['opt_sharpe']['weights']
            ef_tickers = ef_data['tickers']
            opt_weights_rows = [
                {"Actif": t, "Poids actuel": f"{w*100:.1f}%", "Poids optimal (max Sharpe)": f"{ow*100:.1f}%"}
                for t, w, ow in zip(ef_tickers, w_norm, opt_sh_w)
            ]

        # ---- Performance avec capital ----
        if cap:
            perf_title = f'Performance Cumulée (capital initial : {cap:,.0f}€)'
            fig_perf.data[0].y = port_cum.values * cap
            fig_perf.data[1].y = bench_cum.values * cap
            fig_perf.update_layout(title=perf_title, yaxis_title='€')
        else:
            fig_perf.update_layout(title='Performance Cumulée (base 1)', yaxis_title='Valeur')

        # ---- Comparison table ----
        PCT_KEYS_local = {'CAGR', 'Volatilité', 'Max Drawdown', 'VaR 95%', 'CVaR 95%', 'Alpha (annualisé)'}
        table_data = []
        for key in metrics:
            is_pct = key in PCT_KEYS_local
            table_data.append({
                'Métrique': key,
                'Portefeuille': fmt(metrics[key], pct=is_pct),
                bench_label: fmt(bench_metrics[key], pct=is_pct),
            })

        # ── Pre-build conditional sections ─────────────────────────────────
        ff_section = []
        if ff_data:
            ff_section = [
                dbc.Row([
                    dbc.Col([
                        dcc.Graph(figure=_ff_bar_chart(ff_data), config={'displayModeBar': False}),
                    ], md=7),
                    dbc.Col([
                        html.Div([
                            html.P("Régression Fama-French 3 facteurs (proxies ETF) :", style={"color": "#aab", "fontSize": "0.8rem", "marginBottom": "8px"}),
                            _ff_factor_row("Alpha (annualisé)", ff_data['alpha_annual'], ff_data['alpha_t'], is_pct=True),
                            _ff_factor_row("MKT — Marché (β)", ff_data['mkt_beta'], ff_data['mkt_t']),
                            _ff_factor_row("SMB — Taille (β)", ff_data['smb_beta'], ff_data['smb_t']),
                            _ff_factor_row("HML — Value (β)", ff_data['hml_beta'], ff_data['hml_t']),
                            html.Hr(style={"borderColor": "#2a2e45", "margin": "8px 0"}),
                            html.Div([
                                html.Span("R² = ", style={"color": "#aaa", "fontSize": "0.8rem"}),
                                html.Span(f"{ff_data['r2']*100:.1f}%", style={"color": PURPLE, "fontWeight": "700"}),
                                html.Span(f"  ({ff_data['n']} obs.)", style={"color": "#666", "fontSize": "0.75rem", "marginLeft": "8px"}),
                            ]),
                            html.Small("MKT=SPY · SMB=IWM−SPY · HML=IVE−IVW", style={"color": "#555", "fontSize": "0.72rem", "display": "block", "marginTop": "6px"}),
                        ])
                    ], md=5),
                ]),
                dbc.Accordion([
                    dbc.AccordionItem([
                        _insight_block("📐", _ff_interpretation(ff_data)),
                    ], title="Interprétation factorielle"),
                ], start_collapsed=True, flush=True, className="mt-2"),
            ]

        ef_section = []
        if ef_data:
            ef_section = [
                dbc.Row([
                    dbc.Col([dcc.Graph(figure=fig_ef, config={'displayModeBar': False})], md=8),
                    dbc.Col([
                        html.Div([
                            html.H6("Portefeuille optimal (Max Sharpe)", style={"color": "#aab", "fontSize": "0.8rem", "textTransform": "uppercase", "letterSpacing": "1px"}),
                            html.Hr(style={"borderColor": "#2a2e45", "margin": "8px 0"}),
                            _insight_block("⭐", f"Sharpe : {ef_data['opt_sharpe']['sharpe']:.2f}", GREEN),
                            _insight_block("📊", f"Vol : {ef_data['opt_sharpe']['vol']:.1f}%  |  Ret : {ef_data['opt_sharpe']['ret']:.1f}%"),
                            html.Hr(style={"borderColor": "#2a2e45", "margin": "8px 0"}),
                        ] + [
                            _insight_block("→", f"{t} : {w*100:.1f}% → {ow*100:.1f}%",
                                           GREEN if ow > w else (RED if ow < w else "#888"))
                            for t, w, ow in zip(ef_data['tickers'], w_norm, ef_data['opt_sharpe']['weights'])
                        ], style={"padding": "12px", "background": "#171b2d", "border": f"1px solid {GREEN}44", "borderRadius": "6px"}),
                    ], md=4),
                ], className="mb-2"),
            ]

        # ── Stress testing table ────────────────────────────────────────────
        stress_table = dash_table.DataTable(
            data=stress_rows,
            columns=[{"name": c, "id": c} for c in ["Crise", "Portefeuille", bench_label, "Écart"]],
            style_table={'overflowX': 'auto'},
            style_cell={'backgroundColor': '#171b2d', 'color': '#bbc',
                        'border': '1px solid #1e2235', 'textAlign': 'center', 'padding': '10px',
                        'fontSize': '0.83rem'},
            style_header={'backgroundColor': '#13172a', 'fontWeight': 'bold', 'color': '#aab',
                          'border': '1px solid #1e2235'},
            style_data_conditional=[
                {'if': {'filter_query': '{Portefeuille} contains "+"', 'column_id': 'Portefeuille'}, 'color': GREEN},
                {'if': {'filter_query': '{Portefeuille} contains "-"', 'column_id': 'Portefeuille'}, 'color': RED},
                {'if': {'filter_query': '{Écart} contains "+"', 'column_id': 'Écart'}, 'color': GREEN},
                {'if': {'filter_query': '{Écart} contains "-"', 'column_id': 'Écart'}, 'color': RED},
            ]
        )

        # ── Comparison table ────────────────────────────────────────────────
        comparison_table = dash_table.DataTable(
            data=table_data,
            columns=[{"name": c, "id": c} for c in ['Métrique', 'Portefeuille', bench_label]],
            style_table={'overflowX': 'auto'},
            style_cell={'backgroundColor': BG_CARD, 'color': 'white', 'border': '1px solid #333',
                        'textAlign': 'center', 'padding': '10px'},
            style_header={'backgroundColor': '#2d3250', 'fontWeight': 'bold', 'color': GREEN},
            style_data_conditional=[{'if': {'row_index': 'odd'}, 'backgroundColor': '#252940'}]
        )

        TAB_STYLE = {"padding": "16px 4px"}

        results = html.Div([
            dbc.Tabs([

                # ── TAB 1 : RÉSUMÉ ────────────────────────────────────────
                dbc.Tab(label="Résumé", tab_id="tab-summary", children=[
                    html.Div([
                        # Real-time prices (compact inline row)
                        dbc.Card([
                            dbc.CardBody([
                                html.Div([
                                    html.Div([
                                        html.Span(r["Ticker"], style={"color": "white", "fontWeight": "700", "fontSize": "0.85rem"}),
                                        html.Span(f" {r['Prix actuel']}", style={"color": "#ccc", "fontSize": "0.8rem", "marginLeft": "6px"}),
                                        html.Span(f" {r['Variation j']}", style={
                                            "fontSize": "0.78rem", "fontWeight": "600", "marginLeft": "4px",
                                            "color": GREEN if r['Variation j'].startswith('+') else (RED if r['Variation j'].startswith('-') else "#888")
                                        }),
                                    ], style={"display": "inline-block", "marginRight": "20px", "padding": "3px 0"})
                                    for r in real_time_rows
                                ])
                            ], style={"padding": "10px 16px"})
                        ], style={"background": "#171b2d", "border": f"1px solid {BLUE}44"}, className="mb-3"),

                        # Metric cards grid
                        dbc.Row([metric_card(t, v, c) for t, v, c in cards_data], className="mb-2"),

                        # Detailed metric analysis (collapsed)
                        dbc.Accordion([
                            dbc.AccordionItem(metric_rows, title="Analyse détaillée des métriques"),
                        ], start_collapsed=True, flush=True, className="mb-3",
                           style={"border": f"1px solid {GREEN}33", "borderRadius": "6px"}),

                        # Export toggle + button
                        html.Div([
                            dbc.Switch(id='export-toggle', label="Télécharger le CSV", value=False,
                                       style={"display": "inline-block", "marginRight": "12px", "verticalAlign": "middle"}),
                            dbc.Button("⬇ Exporter CSV", id='export-btn',
                                       color="secondary", outline=True, size="sm", disabled=True),
                        ], className="mb-3", style={"display": "flex", "alignItems": "center"}),

                        # Comparison table
                        dbc.Card([
                            dbc.CardHeader(html.H6(f"Portefeuille vs {bench_label}", className="text-white mb-0")),
                            dbc.CardBody(comparison_table),
                        ], style={"background": BG_CARD, "border": "1px solid #333"}, className="mb-2"),

                    ], style=TAB_STYLE),
                ]),

                # ── TAB 2 : PERFORMANCE ───────────────────────────────────
                dbc.Tab(label="Performance", tab_id="tab-perf", children=[
                    html.Div([
                        dbc.Row([
                            dbc.Col([dcc.Graph(figure=fig_perf, config={'displayModeBar': False})], md=8),
                            dbc.Col([dcc.Graph(figure=fig_alloc, config={'displayModeBar': False})], md=4),
                        ], className="mb-2"),
                        dbc.Accordion([
                            dbc.AccordionItem(perf_insights, title="Analyse — Performance Cumulée"),
                        ], start_collapsed=True, flush=True, className="mb-3"),

                        dbc.Row([
                            dbc.Col([dcc.Graph(figure=fig_dd, config={'displayModeBar': False})]),
                        ], className="mb-2"),
                        dbc.Accordion([
                            dbc.AccordionItem(dd_insights, title="Analyse — Drawdown"),
                        ], start_collapsed=True, flush=True, className="mb-3"),

                        dbc.Row([
                            dbc.Col([dcc.Graph(figure=fig_monthly, config={'displayModeBar': False})]),
                        ], className="mb-2"),
                        dbc.Accordion([
                            dbc.AccordionItem(mon_insights, title="Analyse — Rendements Mensuels"),
                        ], start_collapsed=True, flush=True, className="mb-2"),
                    ], style=TAB_STYLE),
                ]),

                # ── TAB 3 : RISQUE ────────────────────────────────────────
                dbc.Tab(label="Risque", tab_id="tab-risk", children=[
                    html.Div([
                        dbc.Row([
                            dbc.Col([dcc.Graph(figure=fig_contrib, config={'displayModeBar': False})]),
                        ], className="mb-2"),
                        dbc.Accordion([
                            dbc.AccordionItem([
                                _insight_block("📊", f"Meilleure contribution au rendement : {contrib_tickers[int(np.argmax(ret_contrib))]} ({ret_contrib.max()*100:+.2f}%/an).", GREEN),
                                _insight_block("⚠️", f"Actif le plus risqué : {contrib_tickers[int(np.argmax(risk_contrib))]} ({risk_contrib.max()*100:.2f}% de la vol totale).", ORANGE),
                                _insight_block("💡", "Un actif peut peser lourd en rendement sans augmenter le risque si sa corrélation avec les autres est faible."),
                            ], title="Analyse — Contribution par actif"),
                        ], start_collapsed=True, flush=True, className="mb-3"),

                        dbc.Row([
                            dbc.Col([dcc.Graph(figure=fig_rolling, config={'displayModeBar': False})], md=8),
                            dbc.Col([dcc.Graph(figure=fig_corr, config={'displayModeBar': False})], md=4),
                        ], className="mb-2"),
                        dbc.Accordion([
                            dbc.AccordionItem(rs_insights, title="Analyse — Sharpe Glissant"),
                            dbc.AccordionItem(corr_insights, title="Analyse — Corrélation"),
                        ], start_collapsed=True, flush=True, className="mb-3"),

                        dbc.Row([
                            dbc.Col([dcc.Graph(figure=fig_dist, config={'displayModeBar': False})]),
                        ], className="mb-2"),
                        dbc.Accordion([
                            dbc.AccordionItem(dist_insights, title="Analyse — Distribution des Rendements"),
                        ], start_collapsed=True, flush=True, className="mb-2"),
                    ], style=TAB_STYLE),
                ]),

                # ── TAB 4 : ANALYSE AVANCÉE ───────────────────────────────
                dbc.Tab(label="Analyse avancée", tab_id="tab-advanced", children=[
                    html.Div([
                        (dbc.Card([
                            dbc.CardHeader(html.H6("Analyse Factorielle — Fama-French 3 Facteurs",
                                className="mb-0", style={"color": "#aab", "fontSize": "0.8rem",
                                "textTransform": "uppercase", "letterSpacing": "1px"}),
                                style={"background": "#13172a", "padding": "8px 16px"}),
                            dbc.CardBody(ff_section, style={"padding": "12px 16px"}),
                        ], style={"background": "#171b2d", "border": f"1px solid {PURPLE}44"}, className="mb-3")
                        if ff_section else
                        html.P("Données insuffisantes pour l'analyse factorielle.", className="text-muted")),

                        html.Div(ef_section) if ef_section else
                        html.P("Ajoutez au moins 2 actifs pour afficher la frontière efficiente.", className="text-muted"),
                    ], style=TAB_STYLE),
                ]),

                # ── TAB 5 : PROJECTIONS ───────────────────────────────────
                dbc.Tab(label="Projections", tab_id="tab-proj", children=[
                    html.Div([
                        dbc.Row([
                            dbc.Col([dcc.Graph(figure=fig_mc, config={'displayModeBar': False})]),
                        ], className="mb-2"),
                        dbc.Accordion([
                            dbc.AccordionItem([
                                _insight_block("🎯", f"Médiane à 10 ans : {mc_label}", GREEN),
                                _insight_block("📉", f"Scénario pessimiste (10e pct.) : {mc_p10_label}", RED),
                                _insight_block("📈", f"Scénario optimiste (90e pct.) : {mc_p90_label}", GREEN),
                                _insight_block("💡", "300 simulations par bootstrap historique. Les performances passées ne garantissent pas les résultats futurs."),
                            ], title="Analyse — Monte Carlo (10 ans)"),
                        ], start_collapsed=True, flush=True, className="mb-3"),

                        dbc.Card([
                            dbc.CardHeader(html.H6("Stress Testing — Performances lors des grandes crises",
                                className="mb-0", style={"color": "#aab", "fontSize": "0.8rem",
                                "textTransform": "uppercase", "letterSpacing": "1px"}),
                                style={"background": "#13172a", "padding": "8px 16px"}),
                            dbc.CardBody(stress_table, style={"padding": "12px 16px"}),
                        ], style={"background": "#171b2d", "border": f"1px solid {RED}44"}, className="mb-2"),
                    ], style=TAB_STYLE),
                ]),

            ], active_tab="tab-summary", className="mb-4",
               style={"borderBottom": "1px solid #333"}),
        ], style={"marginTop": "8px"})

        return results, "", table_data


    except Exception as e:
        import traceback
        return None, f"Erreur : {str(e)}", dash.no_update


@app.callback(
    Output('export-btn', 'disabled'),
    Input('export-toggle', 'value'),
)
def toggle_export_btn(enabled):
    return not bool(enabled)


app.clientside_callback(
    """
    function(n) {
        if (n) { window.print(); }
        return window.dash_clientside.no_update;
    }
    """,
    Output('pdf-btn', 'n_clicks'),
    Input('pdf-btn', 'n_clicks'),
    prevent_initial_call=True,
)


@app.callback(
    Output('download-config', 'data'),
    Input('save-config-btn', 'n_clicks'),
    State({"type": "ticker", "index": dash.ALL}, 'value'),
    State({"type": "weight", "index": dash.ALL}, 'value'),
    prevent_initial_call=True,
)
def save_config(n_clicks, tickers, weights):
    config = [
        {"ticker": t, "weight": w}
        for t, w in zip(tickers, weights)
        if t and w is not None
    ]
    content = json.dumps({"portfolio": config}, indent=2, ensure_ascii=False)
    return dict(content=content, filename="portfolio_config.json")


@app.callback(
    Output('ticker-rows', 'children', allow_duplicate=True),
    Output('n-rows', 'data', allow_duplicate=True),
    Input('upload-config', 'contents'),
    State('upload-config', 'filename'),
    prevent_initial_call=True,
)
def load_config(contents, filename):
    if not contents:
        return dash.no_update, dash.no_update
    try:
        content_type, content_string = contents.split(',')
        decoded = base64.b64decode(content_string).decode('utf-8')
        data = json.loads(decoded)
        rows_data = data.get('portfolio', [])
        if not rows_data:
            return dash.no_update, dash.no_update
        new_rows = [
            _ticker_row(i, r.get('ticker', ''), r.get('weight', 10))
            for i, r in enumerate(rows_data)
        ]
        return new_rows, len(new_rows)
    except Exception:
        return dash.no_update, dash.no_update


@app.callback(
    Output('download-csv', 'data'),
    Input('export-btn', 'n_clicks'),
    State('export-store', 'data'),
    State('export-toggle', 'value'),
    prevent_initial_call=True
)
def export_csv(n_clicks, store_data, enabled):
    if not store_data or not enabled:
        return dash.no_update
    df = pd.DataFrame(store_data)
    return dcc.send_data_frame(df.to_csv, "portfolio_metrics.csv", index=False)


if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 8050))
    app.run(debug=False, host='0.0.0.0', port=port)
