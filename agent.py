"""
Indodax Multi-Pair Trading Agent
Strategies: RSI, EMA Crossover, MACD, Bollinger Bands + News Sentiment
Pairs: BTC/IDR, ETH/IDR, SOL/IDR, XRP/IDR, ADA/IDR
Notifications: Telegram
Features: Daily P&L report at 9:30 PM, trade history CSV
"""

import ccxt
import pandas as pd
import numpy as np
import time
import requests
import logging
import csv
import os
from datetime import datetime
from apscheduler.schedulers.blocking import BlockingScheduler

# ─────────────────────────────────────────────
# CONFIGURATION — Fill in your details
# ─────────────────────────────────────────────
API_KEY = ""
API_SECRET = ""

TELEGRAM_TOKEN = ""
TELEGRAM_CHAT_ID = ""

PAIRS = ["BTC/IDR", "ETH/IDR", "SOL/IDR", "XRP/IDR", "ADA/IDR"]

RISK_PER_TRADE = 0.25        # 25% of available balance per trade
STOP_LOSS_PCT  = 0.03        # 3% stop loss
TAKE_PROFIT_PCT = 0.06       # 6% take profit
CHECK_INTERVAL_MINUTES = 15  # How often the agent runs

# ─────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────
logging.basicConfig(
    filename="agent.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# EXCHANGE SETUP
# ─────────────────────────────────────────────
exchange = ccxt.indodax({
    "apiKey": API_KEY,
    "secret": API_SECRET,
    "enableRateLimit": True,
})

exchange.load_markets()

# ─────────────────────────────────────────────
# TELEGRAM
# ─────────────────────────────────────────────
def send_telegram(message: str):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"})
    except Exception as e:
        log.error(f"Telegram error: {e}")

# ─────────────────────────────────────────────
# TRADE HISTORY & P&L TRACKING
# ─────────────────────────────────────────────
TRADE_LOG_FILE = "trade_history.csv"
BALANCE_SNAPSHOT_FILE = "balance_snapshot.txt"

def init_trade_log():
    """Create trade history CSV if it doesn't exist."""
    if not os.path.exists(TRADE_LOG_FILE):
        with open(TRADE_LOG_FILE, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["datetime", "pair", "action", "price", "amount", "idr_value"])

def log_trade(pair: str, action: str, price: float, amount: float, idr_value: float):
    """Save every trade to CSV."""
    with open(TRADE_LOG_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), pair, action, price, amount, idr_value])

def save_balance_snapshot(total_idr: float):
    """Save today's starting balance for P&L calculation."""
    today = datetime.now().strftime("%Y-%m-%d")
    # Only save once per day (morning snapshot)
    if os.path.exists(BALANCE_SNAPSHOT_FILE):
        with open(BALANCE_SNAPSHOT_FILE, "r") as f:
            content = f.read().strip().split(",")
            if len(content) == 2 and content[0] == today:
                return  # Already saved today
    with open(BALANCE_SNAPSHOT_FILE, "w") as f:
        f.write(f"{today},{total_idr}")

def get_starting_balance() -> float:
    """Get today's starting balance snapshot."""
    if not os.path.exists(BALANCE_SNAPSHOT_FILE):
        return 0.0
    with open(BALANCE_SNAPSHOT_FILE, "r") as f:
        content = f.read().strip().split(",")
        if len(content) == 2:
            return float(content[1])
    return 0.0

def get_total_balance_in_idr() -> float:
    """Calculate total portfolio value in IDR (cash + all coins converted)."""
    try:
        balance = exchange.fetch_balance()
        total = float(balance["free"].get("IDR", 0)) + float(balance["used"].get("IDR", 0))

        for pair in PAIRS:
            coin = pair.split("/")[0]
            coin_amount = float(balance["free"].get(coin, 0)) + float(balance["used"].get(coin, 0))
            if coin_amount > 0:
                ticker = exchange.fetch_ticker(pair)
                price = ticker["last"]
                total += coin_amount * price

        return total
    except Exception as e:
        log.error(f"Balance fetch error: {e}")
        return 0.0

def get_today_trades() -> list:
    """Get all trades made today from CSV."""
    today = datetime.now().strftime("%Y-%m-%d")
    trades = []
    if not os.path.exists(TRADE_LOG_FILE):
        return trades
    with open(TRADE_LOG_FILE, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["datetime"].startswith(today):
                trades.append(row)
    return trades

def send_daily_report():
    """Send daily P&L report at 9:30 PM."""
    try:
        today = datetime.now().strftime("%d %B %Y")
        trades = get_today_trades()
        total_now = get_total_balance_in_idr()
        starting = get_starting_balance()

        # Count buys and sells
        buys  = [t for t in trades if t["action"] == "BUY"]
        sells = [t for t in trades if t["action"] == "SELL"]

        # P&L calculation
        if starting > 0:
            pnl_idr = total_now - starting
            pnl_pct = (pnl_idr / starting) * 100
            pnl_emoji = "📈" if pnl_idr >= 0 else "📉"
            pnl_sign  = "+" if pnl_idr >= 0 else ""
        else:
            pnl_idr = 0
            pnl_pct = 0
            pnl_emoji = "📊"
            pnl_sign  = ""

        # Build trade summary
        trade_lines = ""
        if trades:
            for t in trades[-5:]:  # Show last 5 trades
                action_emoji = "🟢" if t["action"] == "BUY" else "🔴"
                trade_lines += f"\n  {action_emoji} {t['action']} {t['pair']} @ `{float(t['price']):,.0f}`"
        else:
            trade_lines = "\n  No trades today"

        msg = (
            f"📊 *Daily Report — {today}*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💰 Starting Balance: `{starting:,.0f} IDR`\n"
            f"💰 Current Balance:  `{total_now:,.0f} IDR`\n"
            f"{pnl_emoji} P&L: `{pnl_sign}{pnl_idr:,.0f} IDR ({pnl_sign}{pnl_pct:.2f}%)`\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📋 Trades Today: `{len(trades)}`\n"
            f"  🟢 Buys:  `{len(buys)}`\n"
            f"  🔴 Sells: `{len(sells)}`\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🕐 Recent Trades:{trade_lines}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"⏰ Next report: tomorrow 9:30 PM"
        )
        send_telegram(msg)
        log.info("Daily P&L report sent")

    except Exception as e:
        send_telegram(f"⚠️ Error generating daily report: {e}")
        log.error(f"Daily report error: {e}")

# ─────────────────────────────────────────────
# TELEGRAM COMMAND HANDLER
# ─────────────────────────────────────────────
agent_paused = False
last_update_id = 0

COIN_EMOJI = {
    "BTC": "₿", "ETH": "Ξ", "SOL": "◎",
    "XRP": "✕", "ADA": "₳", "IDR": "💵"
}

def handle_command_balance():
    try:
        balance = exchange.fetch_balance()
        idr_free = float(balance["free"].get("IDR", 0))
        total_idr = idr_free

        lines = [f"💵 IDR:  `{idr_free:,.0f}`"]
        for pair in PAIRS:
            coin = pair.split("/")[0]
            amount = float(balance["free"].get(coin, 0))
            emoji = COIN_EMOJI.get(coin, "🔹")
            if amount > 0:
                ticker = exchange.fetch_ticker(pair)
                price = ticker["last"]
                value = amount * price
                total_idr += value
                lines.append(f"{emoji}  {coin}: `{amount:.6f}` (~`{value:,.0f} IDR`)")
            else:
                lines.append(f"{emoji}  {coin}: `0`")

        starting = get_starting_balance()
        if starting > 0:
            pnl = total_idr - starting
            pnl_pct = (pnl / starting) * 100
            pnl_sign = "+" if pnl >= 0 else ""
            pnl_line = f"\n📈 Today's P&L: `{pnl_sign}{pnl:,.0f} IDR ({pnl_sign}{pnl_pct:.2f}%)`"
        else:
            pnl_line = ""

        msg = (
            f"💰 *Current Balance*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            + "\n".join(lines) +
            f"\n━━━━━━━━━━━━━━━━━━\n"
            f"📊 Total Value: `~{total_idr:,.0f} IDR`"
            + pnl_line
        )
        send_telegram(msg)
    except Exception as e:
        send_telegram(f"⚠️ Balance error: {e}")

def handle_command_trades():
    try:
        if not os.path.exists(TRADE_LOG_FILE):
            send_telegram("📋 No trades recorded yet.")
            return

        all_trades = []
        with open(TRADE_LOG_FILE, "r") as f:
            reader = csv.DictReader(f)
            all_trades = list(reader)

        if not all_trades:
            send_telegram("📋 No trades recorded yet.")
            return

        last_trades = all_trades[-8:]
        lines = []
        for t in reversed(last_trades):
            emoji = "🟢" if t["action"] == "BUY" else "🔴"
            lines.append(
                f"{emoji} *{t['action']}* {t['pair']}\n"
                f"   Price: `{float(t['price']):,.0f}` | Amount: `{float(t['amount']):.5f}`\n"
                f"   Time: `{t['datetime']}`"
            )

        msg = f"📋 *Last {len(last_trades)} Trades*\n━━━━━━━━━━━━━━━━━━\n" + "\n\n".join(lines)
        send_telegram(msg)
    except Exception as e:
        send_telegram(f"⚠️ Trades error: {e}")

def handle_command_status():
    status = "🟢 *RUNNING*" if not agent_paused else "🔴 *PAUSED*"
    msg = (
        f"🤖 *Agent Status*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Status: {status}\n"
        f"Pairs: `{', '.join(PAIRS)}`\n"
        f"Interval: every `{CHECK_INTERVAL_MINUTES} min`\n"
        f"Risk/trade: `{int(RISK_PER_TRADE * 100)}%`\n"
        f"Stop Loss: `{int(STOP_LOSS_PCT * 100)}%`\n"
        f"Take Profit: `{int(TAKE_PROFIT_PCT * 100)}%`\n"
        f"Time: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`"
    )
    send_telegram(msg)

def poll_telegram_commands():
    """Poll for new Telegram messages and handle commands."""
    global last_update_id, agent_paused
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
        params = {"offset": last_update_id + 1, "timeout": 5}
        response = requests.get(url, params=params, timeout=10).json()

        for update in response.get("result", []):
            last_update_id = update["update_id"]
            message = update.get("message", {})
            chat_id = str(message.get("chat", {}).get("id", ""))
            text = message.get("text", "").strip().lower()

            # Only respond to your own chat
            if chat_id != str(TELEGRAM_CHAT_ID):
                continue

            if text == "/balance":
                handle_command_balance()
            elif text == "/trades":
                handle_command_trades()
            elif text == "/status":
                handle_command_status()
            elif text == "/stop":
                agent_paused = True
                send_telegram("🔴 *Agent paused.* Send /start to resume.")
            elif text == "/start":
                agent_paused = False
                send_telegram("🟢 *Agent resumed!* Monitoring markets...")
            elif text == "/help":
                send_telegram(
                    "🤖 *Available Commands*\n"
                    "━━━━━━━━━━━━━━━━━━\n"
                    "/balance — Show current holdings\n"
                    "/trades — Show last 8 trades\n"
                    "/status — Show agent status\n"
                    "/stop — Pause trading\n"
                    "/start — Resume trading\n"
                    "/help — Show this menu"
                )
    except Exception as e:
        log.warning(f"Command poll error: {e}")

# ─────────────────────────────────────────────
# FETCH OHLCV DATA
# ─────────────────────────────────────────────
def get_ohlcv(pair: str, timeframe="1h", limit=100) -> pd.DataFrame:
    ohlcv = exchange.fetch_ohlcv(pair, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    return df

# ─────────────────────────────────────────────
# TECHNICAL INDICATORS
# ─────────────────────────────────────────────
def calculate_rsi(series: pd.Series, period=14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = -delta.clip(upper=0).rolling(period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()

def calculate_macd(series: pd.Series):
    ema12 = calculate_ema(series, 12)
    ema26 = calculate_ema(series, 26)
    macd_line = ema12 - ema26
    signal_line = calculate_ema(macd_line, 9)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram

def calculate_bollinger_bands(series: pd.Series, period=20, std_dev=2):
    sma = series.rolling(period).mean()
    std = series.rolling(period).std()
    upper = sma + std_dev * std
    lower = sma - std_dev * std
    return upper, sma, lower

def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df["rsi"]              = calculate_rsi(df["close"])
    df["ema9"]             = calculate_ema(df["close"], 9)
    df["ema21"]            = calculate_ema(df["close"], 21)
    df["ema50"]            = calculate_ema(df["close"], 50)
    df["macd"], df["macd_signal"], df["macd_hist"] = calculate_macd(df["close"])
    df["bb_upper"], df["bb_mid"], df["bb_lower"]   = calculate_bollinger_bands(df["close"])
    df["volume_ma"]        = df["volume"].rolling(20).mean()
    return df

# ─────────────────────────────────────────────
# SIGNAL GENERATION
# ─────────────────────────────────────────────
def generate_signal(df: pd.DataFrame) -> dict:
    latest = df.iloc[-1]
    prev   = df.iloc[-2]
    signals = []
    score   = 0  # positive = buy bias, negative = sell bias

    # --- RSI ---
    if latest["rsi"] < 30:
        signals.append("RSI oversold (BUY)")
        score += 2
    elif latest["rsi"] > 70:
        signals.append("RSI overbought (SELL)")
        score -= 2

    # --- EMA Crossover ---
    if prev["ema9"] < prev["ema21"] and latest["ema9"] > latest["ema21"]:
        signals.append("EMA9 crossed above EMA21 (BUY)")
        score += 2
    elif prev["ema9"] > prev["ema21"] and latest["ema9"] < latest["ema21"]:
        signals.append("EMA9 crossed below EMA21 (SELL)")
        score -= 2

    # --- EMA50 Trend Filter ---
    if latest["close"] > latest["ema50"]:
        signals.append("Price above EMA50 (bullish trend)")
        score += 1
    else:
        signals.append("Price below EMA50 (bearish trend)")
        score -= 1

    # --- MACD ---
    if prev["macd"] < prev["macd_signal"] and latest["macd"] > latest["macd_signal"]:
        signals.append("MACD bullish crossover (BUY)")
        score += 2
    elif prev["macd"] > prev["macd_signal"] and latest["macd"] < latest["macd_signal"]:
        signals.append("MACD bearish crossover (SELL)")
        score -= 2

    # --- Bollinger Bands ---
    if latest["close"] < latest["bb_lower"]:
        signals.append("Price below lower BB (BUY)")
        score += 1
    elif latest["close"] > latest["bb_upper"]:
        signals.append("Price above upper BB (SELL)")
        score -= 1

    # --- Volume Confirmation ---
    if latest["volume"] > latest["volume_ma"] * 1.5:
        signals.append("High volume confirmation")
        score = int(score * 1.2)  # amplify signal on high volume

    # --- Final Decision ---
    if score >= 4:
        action = "BUY"
    elif score <= -4:
        action = "SELL"
    else:
        action = "HOLD"

    return {
        "action": action,
        "score": score,
        "signals": signals,
        "rsi": round(latest["rsi"], 2),
        "price": latest["close"],
    }

# ─────────────────────────────────────────────
# NEWS SENTIMENT (Basic — via CryptoPanic free API)
# ─────────────────────────────────────────────
def get_news_sentiment(coin: str) -> str:
    """
    Uses CryptoPanic free API for basic news sentiment.
    Sign up free at https://cryptopanic.com/developers/api/
    Add your token below.
    """
    CRYPTOPANIC_TOKEN = "YOUR_CRYPTOPANIC_TOKEN"  # optional, leave blank to skip
    if not CRYPTOPANIC_TOKEN or CRYPTOPANIC_TOKEN == "YOUR_CRYPTOPANIC_TOKEN":
        return "neutral"

    try:
        coin_symbol = coin.split("/")[0].lower()
        url = f"https://cryptopanic.com/api/v1/posts/?auth_token={CRYPTOPANIC_TOKEN}&currencies={coin_symbol}&filter=hot"
        response = requests.get(url, timeout=10).json()
        results = response.get("results", [])

        bullish = sum(1 for r in results if r.get("votes", {}).get("positive", 0) > r.get("votes", {}).get("negative", 0))
        bearish = sum(1 for r in results if r.get("votes", {}).get("negative", 0) > r.get("votes", {}).get("positive", 0))

        if bullish > bearish + 2:
            return "bullish"
        elif bearish > bullish + 2:
            return "bearish"
        return "neutral"
    except Exception as e:
        log.warning(f"News sentiment error for {coin}: {e}")
        return "neutral"

# ─────────────────────────────────────────────
# TRADE EXECUTION
# ─────────────────────────────────────────────
def get_balance_idr() -> float:
    balance = exchange.fetch_balance()
    return float(balance["free"].get("IDR", 0))

def get_coin_balance(coin: str) -> float:
    balance = exchange.fetch_balance()
    return float(balance["free"].get(coin, 0))

def execute_buy(pair: str, price: float):
    try:
        coin = pair.split("/")[0]
        idr_balance = get_balance_idr()
        amount_idr = idr_balance * RISK_PER_TRADE

        # Minimum order check
        if amount_idr < 10000:
            log.info(f"Skipping {pair} — amount {amount_idr} below minimum 10,000 IDR")
            return

        # Calculate coin amount based on IDR to spend
        amount_coin = amount_idr / price

        indodax_pair = pair.replace("/", "_").lower()
        order = exchange.create_order(pair, 'market', 'sell', coin_balance, price, {'pair': indodax_pair})
        sl_price = round(price * (1 - STOP_LOSS_PCT), 2)
        tp_price = round(price * (1 + TAKE_PROFIT_PCT), 2)

        msg = (
            f"✅ *BUY ORDER EXECUTED*\n"
            f"Pair: `{pair}`\n"
            f"Price: `{price:,.0f} IDR`\n"
            f"Amount: `{amount_coin:.8f} {coin}`\n"
            f"IDR Spent: `{amount_idr:,.0f}`\n"
            f"Stop Loss: `{sl_price:,.0f} IDR`\n"
            f"Take Profit: `{tp_price:,.0f} IDR`\n"
            f"Time: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`"
        )
        send_telegram(msg)
        log.info(f"BUY {pair} at {price} | Order: {order}")
        log_trade(pair, "BUY", price, amount_coin, amount_idr)

    except Exception as e:
        send_telegram(f"❌ BUY failed for {pair}: {e}")
        log.error(f"BUY error {pair}: {e}")

def execute_sell(pair: str, price: float):
    try:
        coin = pair.split("/")[0]
        coin_balance = get_coin_balance(coin)

        if coin_balance <= 0:
            log.info(f"No {coin} balance to sell")
            return
        
        indodax_pair = pair.replace("/", "_").lower()
        order = exchange.create_order(pair, 'market', 'sell', coin_balance, price, {'pair': indodax_pair})
        idr_received = coin_balance * price

        msg = (
            f"🔴 *SELL ORDER EXECUTED*\n"
            f"Pair: `{pair}`\n"
            f"Price: `{price:,.0f} IDR`\n"
            f"Amount: `{coin_balance:.6f} {coin}`\n"
            f"IDR Received: `{idr_received:,.0f}`\n"
            f"Time: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`"
        )
        send_telegram(msg)
        log.info(f"SELL {pair} at {price} | Order: {order}")
        log_trade(pair, "SELL", price, coin_balance, idr_received)

    except Exception as e:
        send_telegram(f"❌ SELL failed for {pair}: {e}")
        log.error(f"SELL error {pair}: {e}")

# ─────────────────────────────────────────────
# MAIN LOOP — runs every CHECK_INTERVAL_MINUTES
# ─────────────────────────────────────────────
def run_agent():
    global agent_paused
    poll_telegram_commands()  # Check for commands first

    if agent_paused:
        log.info("Agent is paused — skipping cycle")
        return

    log.info("=== Agent cycle started ===")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Running agent...")

    for pair in PAIRS:
        try:
            df = get_ohlcv(pair)
            df = add_indicators(df)
            signal = generate_signal(df)
            sentiment = get_news_sentiment(pair)

            action = signal["action"]

            # Sentiment override: if sentiment conflicts with signal, downgrade to HOLD
            if action == "BUY" and sentiment == "bearish":
                action = "HOLD"
                signal["signals"].append("⚠️ News sentiment bearish — overriding BUY to HOLD")
            elif action == "SELL" and sentiment == "bullish":
                action = "HOLD"
                signal["signals"].append("⚠️ News sentiment bullish — overriding SELL to HOLD")

            # Send alert
            emoji = "🟢" if action == "BUY" else "🔴" if action == "SELL" else "⚪"
            signals_text = "\n".join([f"  • {s}" for s in signal["signals"]])
            alert_msg = (
                f"{emoji} *{action} SIGNAL — {pair}*\n"
                f"Price: `{signal['price']:,.0f} IDR`\n"
                f"RSI: `{signal['rsi']}`\n"
                f"Score: `{signal['score']}`\n"
                f"Sentiment: `{sentiment}`\n"
                f"Signals:\n{signals_text}"
            )
            send_telegram(alert_msg)

            # Execute trade
            if action == "BUY":
                execute_buy(pair, signal["price"])
            elif action == "SELL":
                execute_sell(pair, signal["price"])

            time.sleep(1)  # Rate limit between pairs

        except Exception as e:
            log.error(f"Error processing {pair}: {e}")
            send_telegram(f"⚠️ Error on {pair}: {e}")

    log.info("=== Agent cycle complete ===")

# ─────────────────────────────────────────────
# SCHEDULER
# ─────────────────────────────────────────────
if __name__ == "__main__":
    init_trade_log()

    # Save starting balance snapshot when agent first starts
    starting_balance = get_total_balance_in_idr()
    save_balance_snapshot(starting_balance)

    send_telegram(
        f"🤖 *Trading Agent Started*\n"
        f"Monitoring: {', '.join(PAIRS)}\n"
        f"💰 Starting Balance: `{starting_balance:,.0f} IDR`\n"
        f"📊 Daily report scheduled: 9:30 PM"
    )
    print("Trading agent started. Press Ctrl+C to stop.")

    scheduler = BlockingScheduler(timezone="Asia/Jakarta")
    scheduler.add_job(run_agent, "interval", minutes=CHECK_INTERVAL_MINUTES, next_run_time=datetime.now())

    # Daily P&L report at 9:30 PM Jakarta time
    scheduler.add_job(send_daily_report, "cron", hour=21, minute=30)

    # Save balance snapshot every morning at 8:00 AM (for daily P&L baseline)
    scheduler.add_job(
        lambda: save_balance_snapshot(get_total_balance_in_idr()),
        "cron", hour=8, minute=0
    )

    try:
        scheduler.start()
    except KeyboardInterrupt:
        send_telegram("🛑 Trading Agent stopped.")
        print("Agent stopped.")

    scheduler = BlockingScheduler(timezone="Asia/Jakarta")
    scheduler.add_job(run_agent, "interval", minutes=CHECK_INTERVAL_MINUTES)

    # Daily P&L report at 9:30 PM Jakarta time
    scheduler.add_job(send_daily_report, "cron", hour=21, minute=30)

    # Save balance snapshot every morning at 8:00 AM (for daily P&L baseline)
    scheduler.add_job(
        lambda: save_balance_snapshot(get_total_balance_in_idr()),
        "cron", hour=8, minute=0
    )

    try:
        scheduler.start()
    except KeyboardInterrupt:
        send_telegram("🛑 Trading Agent stopped.")
        print("Agent stopped.")
