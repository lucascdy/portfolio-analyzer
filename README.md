# Portfolio Analyzer

Application web d'analyse de portefeuille boursier et crypto, construite avec [Dash](https://dash.plotly.com/) et [yfinance](https://github.com/ranaroussi/yfinance).

- Recherche parmi les actions des grands indices mondiaux (S&P 500, CAC 40, DAX, Nikkei 225…) et les principales cryptomonnaies
- Métriques de performance et de risque du portefeuille
- Optimisation d'allocation
- Le portefeuille de chaque visiteur est stocké dans son navigateur : rien n'est partagé entre utilisateurs

## Utiliser l'application

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/lucascdy/portfolio-analyzer)

## Lancer en local

```bash
pip install -r requirements.txt
python app.py
```

Puis ouvrir http://127.0.0.1:8050. Au premier lancement, l'application télécharge la liste des tickers (quelques minutes).

## Déploiement

Le dépôt contient les configurations pour [Render](https://render.com) (`render.yaml`) et [Railway](https://railway.app) (`railway.toml`). Commande de démarrage :

```bash
gunicorn app:server --timeout 120 --workers 1
```
