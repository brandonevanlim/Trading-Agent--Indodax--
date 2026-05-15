# 🤖 Indodax Trading Agent — Setup Guide

## Step 1: Connect to your VPS
```bash
ssh root@your_vps_ip
```

## Step 2: Install Python & dependencies
```bash
sudo apt update && sudo apt install python3 python3-pip -y
pip3 install -r requirements.txt
```

## Step 3: Upload your agent
From your local machine (not VPS):
```bash
scp -r ./trading_agent root@your_vps_ip:/root/
```

## Step 4: Fill in your credentials
Open agent.py and replace:
- YOUR_INDODAX_API_KEY
- YOUR_INDODAX_API_SECRET
- YOUR_TELEGRAM_BOT_TOKEN
- YOUR_TELEGRAM_CHAT_ID

To get your Telegram Chat ID:
1. Message your bot
2. Visit: https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates
3. Look for "chat":{"id": XXXXXXX}

## Step 5: Test it first
```bash
cd /root/trading_agent
python3 agent.py
```
You should get a Telegram message saying the agent started.

## Step 6: Run 24/7 with pm2
```bash
# Install pm2
npm install -g pm2

# Start agent
pm2 start agent.py --interpreter python3 --name trading-agent

# Auto-restart on reboot
pm2 save
pm2 startup

# Monitor logs
pm2 logs trading-agent
```

## Useful pm2 commands
```bash
pm2 status              # Check if running
pm2 restart trading-agent
pm2 stop trading-agent
pm2 logs trading-agent --lines 50
```

## Optional: CryptoPanic (News Sentiment)
1. Sign up free at https://cryptopanic.com/developers/api/
2. Get your API token
3. Add it to agent.py: CRYPTOPANIC_TOKEN = "your_token"

## Strategy Summary
The agent runs every 15 minutes and checks:
| Indicator | Buy Signal | Sell Signal |
|-----------|-----------|-------------|
| RSI | < 30 (oversold) | > 70 (overbought) |
| EMA Cross | EMA9 crosses above EMA21 | EMA9 crosses below EMA21 |
| EMA50 | Price above EMA50 | Price below EMA50 |
| MACD | Bullish crossover | Bearish crossover |
| Bollinger | Price below lower band | Price above upper band |
| Volume | High volume amplifies signal | - |
| News | Bearish news cancels BUY | Bullish news cancels SELL |

A trade executes only when score >= 4 (strong confluence of signals).
Risk per trade: 25% of available IDR balance.
