# 🚀 Polymarket Intelligence Bot

AI-powered Telegram bot for Polymarket prediction market signals, whale tracking, sentiment analysis, and high-confidence trade detection.

## Features

- **AI Probability Engine** — GPT-powered market analysis with Bayesian calibration
- **Multi-Source Sentiment Analysis** — VADER NLP across Google News, GDELT, Reddit, NewsAPI, Hacker News
- **Whale Tracking** — Monitor large trades and smart-money behavior
- **Signal Generation** — High-EV trade signals with confidence scoring and risk analysis
- **Real-Time Monitoring** — Scheduled market scanning with automatic Telegram alerts
- **Category Filtering** — Crypto, Politics, Sports, Economy, AI/Tech, Global Events
- **Performance Tracking** — Win rate, ROI, accuracy, and category-level breakdown
- **Premium Formatting** — Rich Telegram messages with inline buttons and markdown
- **FastAPI Admin API** — Health checks, market data, signal history, whale data
- **Production-Ready** — Docker, Redis, PostgreSQL, systemd, Railway, Render support

## Architecture

```
src/
├── ai/                  # AI probability engine + Bayesian calibration
├── alerts/              # Alert routing and delivery
├── analytics/           # Performance tracking and metrics
├── api/                 # FastAPI admin endpoints
├── config/              # Settings and logging configuration
├── database/            # SQLAlchemy models and session management
├── polymarket/          # Polymarket API + WebSocket client
├── scheduler/           # APScheduler jobs (signal scan, whale scan)
├── sentiment/           # Sentiment analysis + news fetching + data providers
├── signals/             # Signal generation engine
├── telegram/            # Bot commands, formatting, inline buttons
├── utils/               # Shared utilities
└── whales/              # Whale tracking system
```

## Quick Start

### 1. Clone and configure

```bash
git clone <repo-url>
cd polymarket-telegram-bot
cp .env.example .env
# Edit .env with your API keys
```

### 2. Install dependencies

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Run the bot

```bash
python main.py
```

### 4. Run the API server

```bash
python main.py --api
```

## Docker Deployment

```bash
docker-compose up -d
```

This starts:
- **Bot** — Telegram polling + scheduled market scanning
- **API** — FastAPI on port 8000
- **PostgreSQL** — Database on port 5432
- **Redis** — Cache on port 6379

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | ✅ | Telegram Bot API token |
| `TELEGRAM_CHAT_ID` | ✅ | Default chat ID for alerts |
| `OPENAI_API_KEY` | ✅ | OpenAI API key |
| `NEWS_API_KEY` | ❌ | NewsAPI.org key |
| `COINGECKO_API_KEY` | ❌ | CoinGecko API key |
| `FRED_API_KEY` | ❌ | FRED economic data key |
| `THE_ODDS_API_KEY` | ❌ | Sports odds API key |
| `DATABASE_URL` | ❌ | PostgreSQL async URL |
| `REDIS_URL` | ❌ | Redis connection URL |

See `.env.example` for all options.

## Telegram Commands

| Command | Description |
|---|---|
| `/start` | Welcome message |
| `/help` | Show all commands |
| `/signals` | Latest trade signals |
| `/highconfidence` | High-confidence (80+) signals |
| `/crypto` | Crypto market signals |
| `/sports` | Sports market signals |
| `/politics` | Politics market signals |
| `/economy` | Economy/macro signals |
| `/whales` | Recent whale activity |
| `/trending` | Trending markets |
| `/top` | Top markets by volume |
| `/market [name]` | Search and analyze a market |
| `/portfolio` | Your signal portfolio |
| `/performance` | Bot performance metrics |
| `/subscribe` | Subscribe to auto-alerts |
| `/unsubscribe` | Unsubscribe from alerts |

## Data Sources

| Source | Type | Cost |
|---|---|---|
| Polymarket Gamma API | Market data | Free |
| Polymarket CLOB API | Order book, trades | Free |
| Google News RSS | News | Free |
| GDELT | News/events | Free |
| NewsAPI | News | Free tier |
| Reddit JSON API | Social sentiment | Free |
| Hacker News Algolia | Tech news | Free |
| CoinGecko | Crypto prices | Free |
| FRED | Economic data | Free |
| The Odds API | Sports odds | Free tier |
| OpenAI | AI reasoning | Pay per use |

## Signal Format

Each signal includes:
- Market title and current probability
- AI-estimated probability and expected edge
- Confidence score (0-100)
- Liquidity and volatility ratings
- Risk level assessment
- AI reasoning with multi-factor analysis
- News summary and sentiment analysis
- Whale activity summary
- Suggested entry/exit zones and time horizon

## Deployment Options

### Railway
```bash
railway up
```

### Render
Deploy using `deploy/render.yaml` blueprint.

### Ubuntu VPS
```bash
# Copy service file
sudo cp deploy/polymarket-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now polymarket-bot

# Nginx reverse proxy
sudo cp deploy/nginx.conf /etc/nginx/sites-available/polymarket
sudo ln -s /etc/nginx/sites-available/polymarket /etc/nginx/sites-enabled/
sudo systemctl reload nginx
```

## API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | Health check |
| `/api/v1/markets` | GET | List active markets |
| `/api/v1/signals` | GET | List signals |
| `/api/v1/performance` | GET | Performance metrics |
| `/api/v1/whales` | GET | Tracked whale wallets |
| `/api/v1/admin/stats` | GET | Admin statistics |
| `/api/v1/admin/broadcast` | POST | Broadcast message |

## License

MIT
