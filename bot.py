import asyncio
import yfinance as yf
import pandas as pd
import numpy as np
import uuid
import io
import mplfinance as mpf
import matplotlib.pyplot as plt
from PIL import Image

from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from ta.trend import EMAIndicator, MACD
from ta.momentum import RSIIndicator
from ta.volatility import AverageTrueRange
from newsapi import NewsApiClient

# ================= CONFIG =================
TOKEN = "8525733732:AAFeYYcG0raJVd25e55m7Ty0Xogq1STiba4"
NEWS_API_KEY = "4f63bed65bd24a12abf30cd32eda938c"

newsapi = NewsApiClient(api_key=NEWS_API_KEY)

# ================= SYMBOL FORMAT =================
def format_symbol(symbol):
    if symbol.endswith(".NS") or symbol.endswith(".BO"):
        return symbol
    if yf.Ticker(symbol + ".NS").history(period="1d").empty:
        return symbol + ".BO"
    return symbol + ".NS"

# ================= NEWS SENTIMENT =================
def news_sentiment(symbol):
    try:
        articles = newsapi.get_everything(q=symbol, language="en", page_size=5)
        score = 0
        for article in articles["articles"]:
            title = article["title"].lower()
            if any(w in title for w in ["gain","rise","profit","growth"]):
                score += 1
            if any(w in title for w in ["loss","fall","drop","decline"]):
                score -= 1
        if score > 1:
            return "Positive"
        elif score < 0:
            return "Negative"
        else:
            return "Neutral"
    except:
        return "Unavailable"

# ================= LEVEL 6 BACKTEST =================
def backtest(df):

    capital = 1_000_000
    risk_per_trade = 0.01
    equity = capital
    peak_equity = capital

    wins = losses = total_trades = 0
    gross_profit = gross_loss = 0

    df["EMA20"] = EMAIndicator(df["Close"], 20).ema_indicator()
    df["EMA50"] = EMAIndicator(df["Close"], 50).ema_indicator()
    df["ATR"] = AverageTrueRange(df["High"], df["Low"], df["Close"]).average_true_range()

    for i in range(50, len(df)-1):

        if df["EMA20"].iloc[i] > df["EMA50"].iloc[i]:

            entry = df["Close"].iloc[i]
            atr = df["ATR"].iloc[i]

            stop = entry - (1.5 * atr)
            target = entry + atr

            risk_amount = equity * risk_per_trade

            for j in range(i+1, len(df)):

                low = df["Low"].iloc[j]
                high = df["High"].iloc[j]

                if low <= stop:
                    equity -= risk_amount
                    gross_loss += risk_amount
                    losses += 1
                    total_trades += 1
                    break

                if high >= target:
                    profit = risk_amount * ((target-entry)/(entry-stop))
                    equity += profit
                    gross_profit += profit
                    wins += 1
                    total_trades += 1
                    break

            peak_equity = max(peak_equity, equity)

    win_rate = round((wins/total_trades)*100,2) if total_trades else 0
    profit_factor = round(gross_profit/gross_loss,2) if gross_loss else 0
    max_drawdown = round(((peak_equity - equity)/peak_equity)*100,2) if peak_equity else 0
    net_return = round(((equity - capital)/capital)*100,2)

    return {
        "trades": total_trades,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "net_return": net_return,
        "max_drawdown": max_drawdown
    }

# ================= ANALYSIS =================
def analyze_stock(symbol, interval="1d"):

    symbol = format_symbol(symbol)
    period = "6mo" if interval == "1d" else "7d"

    ticker = yf.Ticker(symbol)
    df = ticker.history(period=period, interval=interval)

    if df.empty or len(df) < 50:
        return None, "❌ Not enough data"

    df["EMA20"] = EMAIndicator(df["Close"], 20).ema_indicator()
    df["EMA50"] = EMAIndicator(df["Close"], 50).ema_indicator()
    df["ATR"] = AverageTrueRange(df["High"], df["Low"], df["Close"]).average_true_range()
    df["RSI"] = RSIIndicator(df["Close"]).rsi()

    macd = MACD(df["Close"])
    df["MACD"] = macd.macd()
    df["MACD_signal"] = macd.macd_signal()

    price = df["Close"].iloc[-1]
    atr = df["ATR"].iloc[-1]
    rsi = df["RSI"].iloc[-1]

    support = df["Low"].rolling(20).min().iloc[-1]
    resistance = df["High"].rolling(20).max().iloc[-1]

    # ========= 1️⃣ MARKET TREND =========
    nifty = yf.Ticker("^NSEI")
    nifty_df = nifty.history(period="1mo")
    if not nifty_df.empty:
        nifty_ema20 = EMAIndicator(nifty_df["Close"], 20).ema_indicator().iloc[-1]
        nifty_price = nifty_df["Close"].iloc[-1]
        market_trend = "Bullish" if nifty_price > nifty_ema20 else "Bearish"
    else:
        market_trend = "Unknown"

    # ========= 2️⃣ VOLATILITY =========
    volatility = (atr / price) * 100 if price != 0 else 0
    if volatility < 1:
        vol_rating = "Low"
    elif volatility < 2:
        vol_rating = "Medium"
    else:
        vol_rating = "High"

    # ========= 3️⃣ BREAKOUT =========
    if price > resistance:
        breakout = "🔥 Breakout"
    elif price < support:
        breakout = "⚠ Breakdown"
    else:
        breakout = "Inside Range"

    # ================= TRADE SETUP =================
    entry = support * 1.01
    stop_loss = support * 0.97

    target1 = price + atr
    target2 = price + (2 * atr)

    risk = entry - stop_loss
    reward1 = target1 - entry
    reward2 = target2 - entry

 # ========= ETA (Estimated Sessions) =========
    if atr > 0:
        eta_t1 = max(1, int(abs(target1 - price) / atr))
        eta_t2 = max(1, int(abs(target2 - price) / atr))
    else:
        eta_t1 = 1
        eta_t2 = 1

    rr1 = round(reward1/risk,2) if risk>0 else 0
    rr2 = round(reward2/risk,2) if risk>0 else 0

    # ========= 4️⃣ POSITION SIZE =========
    capital = 100000
    risk_percent = 1
    risk_amount = capital * (risk_percent / 100)
    position_size = int(risk_amount / risk) if risk > 0 else 0

    # ================= CONFIDENCE =================
    long_conf = min(95, 50 + (rsi - 50))
    short_conf = min(95, 50 + (50 - rsi))

    # ================= AI BUY PROBABILITY =================
    ai_score = 0

    if df["EMA20"].iloc[-1] > df["EMA50"].iloc[-1]:
        ai_score += 30

    if rsi > 55:
        ai_score += 25
    elif rsi > 50:
        ai_score += 15

    if df["MACD"].iloc[-1] > df["MACD_signal"].iloc[-1]:
        ai_score += 20

    avg_vol = df["Volume"].rolling(20).mean().iloc[-1]
    if df["Volume"].iloc[-1] > avg_vol:
        ai_score += 15

    if price > support:
        ai_score += 10

    ai_probability = min(ai_score, 100)

    # ========= 5️⃣ TREND SCORE =========
    trend_score = 0
    if df["EMA20"].iloc[-1] > df["EMA50"].iloc[-1]: trend_score += 4
    if rsi > 55: trend_score += 3
    if df["MACD"].iloc[-1] > df["MACD_signal"].iloc[-1]: trend_score += 3

    # ================= PROBABILITY T1 BEFORE SL =================
    if rr1 > 0:
        rr_based_prob = rr1 / (1 + rr1)
        prob_t1_before_sl = round((ai_probability / 100) * rr_based_prob * 100, 2)
    else:
        prob_t1_before_sl = 0

    # ================= BACKTEST =================
    sentiment = news_sentiment(symbol)
    bt = backtest(df)

    # ========= 6️⃣ STRATEGY RISK =========
    if bt['max_drawdown'] < 10:
        risk_level = "Low"
    elif bt['max_drawdown'] < 25:
        risk_level = "Moderate"
    else:
        risk_level = "High"

    # ========= 7️⃣ SMART RATING =========
    final_score = (
        ai_probability * 0.4 +
        (trend_score * 10) * 0.3 +
        (bt['win_rate']) * 0.3
    )
    final_score = round(min(final_score, 100), 2)
    if final_score < 30:
        rating_icon = "🔴"
    elif final_score < 60:
        rating_icon = "🟠"
    else:
        rating_icon = "🟢"
        
    meter_blocks = 10
    filled = int((final_score / 100) * meter_blocks)
    confidence_meter = "▓" * filled + "░" * (meter_blocks - filled)

    # ================= FUNDAMENTAL =================
    info = ticker.info
    pe = info.get("trailingPE", 0)
    roe = info.get("returnOnEquity", 0)
    debt = info.get("debtToEquity", 0)

    fund_score = 0
    if pe and pe < 30: fund_score += 1
    if roe and roe > 0.15: fund_score += 1
    if debt and debt < 1: fund_score += 1

    fund_strength = ["Weak","Medium","Strong"][fund_score-1] if fund_score>0 else "Weak"

    tech_score = 0
    if df["EMA20"].iloc[-1] > df["EMA50"].iloc[-1]: tech_score += 1
    if rsi > 55: tech_score += 1
    if df["MACD"].iloc[-1] > df["MACD_signal"].iloc[-1]: tech_score += 1

    tech_strength = ["Weak","Medium","Strong"][tech_score-1] if tech_score>0 else "Weak"

    analysis = f"""
<b>📊 {symbol} | {interval.upper()}</b>
━━━━━━━━━━━━━━━━━━━━

💰 <b>Price</b>         ₹{price:,.2f}
📉 ATR           {atr:,.2f}
🌍 Market Trend  <b>{market_trend}</b>
⚡ Volatility    {vol_rating} ({volatility:.2f}%)
📊 Range         {breakout}

━━ <b>LEVELS</b> ━━
🧱 Support       ₹{support:,.2f}
🚧 Resistance    ₹{resistance:,.2f}

━━ <b>TRADE SETUP</b> ━━
🎯 Entry         <b>₹{entry:,.2f}</b>
🛑 Stop Loss     ₹{stop_loss:,.2f}

🏹 Target 1      ₹{target1:,.2f}
   R/R           <b>{rr1}</b>
   Confidence    {long_conf:.2f}%
   ETA           {eta_t1} session(s)

🏹 Target 2      ₹{target2:,.2f}
   R/R           <b>{rr2}</b>
   Confidence    {short_conf:.2f}%
   ETA           {eta_t2} session(s)

📦 Position Size {position_size} shares
🤖 AI Buy Probability <b>{ai_probability}%</b>
🎯 T1 Before SL  {prob_t1_before_sl:.1f}%

━━ <b>ANALYTICS</b> ━━
🧠 Technical     {tech_strength}
📊 Trend Score   {trend_score}/10
🏢 Fundamental   {fund_strength}
📰 Sentiment     {sentiment}

━━ <b>BACKTEST</b> ━━
📈 Trades        {bt['trades']}
🏆 Win Rate      {bt['win_rate']}%
💹 Profit Factor {bt['profit_factor']}
📊 Net Return    {bt['net_return']}%
📉 Max DD        {bt['max_drawdown']}%
⚠ Risk Level     {risk_level}

🏅 <b>SMART RATING</b>  {rating_icon} {final_score:.1f} / 100
Confidence Meter  <b>{confidence_meter}</b> {final_score:.2f}%

━━━━━━━━━━━━━━━━━━━━
<i>VIP STOCK BOT</i>
"""

    return df, analysis, entry, stop_loss, target1, target2, final_score

# ================= CHART =================
import io
import mplfinance as mpf
import matplotlib.pyplot as plt

def generate_chart(df, symbol, entry, stop, target1, target2, smart_rating):

    buffer = io.BytesIO()

    df_plot = df.copy()
    df_plot.index.name = "Date"

    # Premium EMA Colors
    apds = [
        mpf.make_addplot(df_plot["EMA20"], color='#29b6f6', width=2.2, label='EMA 20'),
        mpf.make_addplot(df_plot["EMA50"], color='#ff5252', width=2.2, label='EMA 50'),
    ]

    mc = mpf.make_marketcolors(
        up='#00e676',
        down='#ff1744',
        edge='inherit',
        wick='inherit',
        volume='inherit'
    )

    style = mpf.make_mpf_style(
        marketcolors=mc,
        facecolor='#0d1117',        # TradingView style dark
        gridcolor='#1f2937',        # Soft grid
        gridstyle='-',
        rc={
            "font.size": 11,
            "axes.labelcolor": "white",
            "xtick.color": "#c9d1d9",
            "ytick.color": "#c9d1d9"
        }
    )

    fig, axes = mpf.plot(
        df_plot,
        type='candle',
        style=style,
        volume=True,
        addplot=apds,
        figsize=(15,8),
        panel_ratios=(5,1.4),
        returnfig=True
    )

    ax = axes[0]

    # Clean professional title
    ax.set_title(
        f"{symbol}  |  Smart Rating: {smart_rating}/100",
        fontsize=16,
        color='white',
        pad=18,
        fontweight='bold'
    )

    # Highlight latest price
    last_price = df_plot["Close"].iloc[-1]
    ax.axhline(last_price, color='#ffd54f', linestyle='--', linewidth=1)

    # Clean trade levels (subtle)
    ax.axhline(entry, color='#00bcd4', linestyle='--', linewidth=1)
    ax.axhline(stop, color='#ff3d00', linestyle='--', linewidth=1)
    ax.axhline(target1, color='#00e676', linestyle='--', linewidth=1)
    ax.axhline(target2, color='#00c853', linestyle='--', linewidth=1)

    # Premium legend
    legend = ax.legend(loc='upper left', fontsize=11)
    legend.get_frame().set_facecolor('#161b22')
    legend.get_frame().set_alpha(0.9)
    legend.get_frame().set_edgecolor('#161b22')

    # Optimize margins
    fig.subplots_adjust(left=0.05, right=0.98, top=0.92, bottom=0.15)

    # Rotate dates cleanly
    axes[-1].tick_params(axis='x', rotation=25)

    # Subtle watermark
    ax.text(
        0.99, 0.02,
        "VIP STOCK BOT",
        transform=ax.transAxes,
        fontsize=13,
        color='gray',
        alpha=0.10,
        ha='right',
        va='bottom'
    )

    fig.patch.set_facecolor('#0d1117')

    fig.savefig(buffer, format="png", dpi=140)
    plt.close(fig)

    buffer.seek(0)
    buffer.name = "chart.png"

    return buffer
# ================= TELEGRAM =================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not update.message or not update.message.text:
        return

    text = update.message.text.upper().split()
    symbol = text[0]
    interval = "1d"

    if len(text) > 1:
        interval = text[1]

    result = analyze_stock(symbol, interval)

    if result[0] is None:
        await update.message.reply_text(result[1])
        return

    df, analysis, entry, stop_loss, target1, target2, final_score = result

    chart_buffer = generate_chart(
        df,
        symbol,
        entry,
        stop_loss,
        target1,
        target2,
        final_score
    )

    # 🔥 THIS LINE IS IMPORTANT
    await update.message.reply_photo(
        photo=chart_buffer,
        filename="chart.png"
    )

    await update.message.reply_text(
    analysis,
    parse_mode="HTML"
)
import os

PORT = int(os.environ.get("PORT", 10000))
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")

app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

async def main():
    await app.initialize()
    await app.start()
    await app.bot.set_webhook(f"{WEBHOOK_URL}/{TOKEN}")
    await app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=TOKEN
    )

print("WEBHOOK BOT STARTING...")
asyncio.run(main())