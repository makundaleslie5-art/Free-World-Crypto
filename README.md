# Free World Crypto

Free World Crypto is a **simulation-only** crypto trading app built with FastAPI, SQLite, and a browser frontend. It uses sample market prices and demo funds; it does not handle real money or real crypto.


## Run locally

1. Create and activate a Python virtual environment.
2. Install dependencies: `pip install -r requirements.txt`
3. Start the server: `uvicorn app.main:app --reload`
4. Open `http://127.0.0.1:8000`

## Accounts and wallets

- Register with an email, login password (8+ characters), and separate funds password (12+ characters).
- New accounts receive a separate $10,000 demo wallet.
- Login sessions use bearer tokens stored by the browser and expire after 30 days.
- Every user's balance, holdings, and transaction history are stored separately.
- Buy and sell actions require login and the funds password.


## Safety

All trading is simulated using hard-coded sample prices. Demo balances have no cash value. Do not use this app for deposits, withdrawals, custody, or real trading.


## Tests

Run the test suite with: `python -m unittest discover -s tests -v`

## Market prices

- BTC, ETH and SOL reference prices are fetched server-side from CoinGecko's Simple Price API.
- The backend caches provider responses for five minutes and can use a recent cached response during a short provider outage.
- If the provider cannot be reached, the app clearly labels the configured sample-price fallback.
- FREE is a project-specific demo asset and retains its configured reference price; it is not represented as a listed market asset.
- Trades remain simulated and use the current displayed reference price; no real orders, deposits, withdrawals or custody are supported.
- To use a CoinGecko Demo API key, copy `.env.example` to `.env` and replace the placeholder with your key. The backend reads this private file at startup.
- Never commit `.env` or expose the key in browser JavaScript.
- The current candlestick and RSI graphics remain illustrative simulations. They are not historical market candles; historical chart integration is a separate next step.
