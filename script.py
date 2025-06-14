import os
import asyncio
from tradingview_ta import TA_Handler, Interval
from twilio.rest import Client
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    filters, ContextTypes, Application
)
from dotenv import load_dotenv
load_dotenv()

# === Configuration ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST")  # e.g. https://your-app-name.onrender.com
WEBHOOK_URL = f"{WEBHOOK_HOST}/{TELEGRAM_TOKEN}"

# Twilio Config
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_FROM_PHONE = os.getenv("TWILIO_FROM_PHONE")
TWILIO_TO_PHONE = os.getenv("TWILIO_TO_PHONE")

# Exchanges
EXCHANGES = ["OANDA", "FOREXCOM", "FX_IDC", "SAXO", "CURRENCYCOM"]

# Globals
user_currency_pairs = {}
last_signals = {}
twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# === Utility Functions ===
def send_twilio_sms(message):
    try:
        msg = twilio_client.messages.create(
            body=message,
            from_=TWILIO_FROM_PHONE,
            to=TWILIO_TO_PHONE
        )
        print(f"✅ SMS sent: SID {msg.sid}")
    except Exception as e:
        print(f"❌ SMS failed: {e}")

def get_signal_for_pair(symbol):
    for ex in EXCHANGES:
        try:
            handler = TA_Handler(
                symbol=symbol,
                screener="forex",
                exchange=ex,
                interval=Interval.INTERVAL_5_MINUTES
            )
            analysis = handler.get_analysis()
            return analysis.summary["RECOMMENDATION"], ex
        except:
            continue
    return None, None

# === Telegram Handlers ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome! Please send me the currency pairs you want to monitor.\n"
        "Send them as comma-separated values (e.g. USDJPY, EURUSD)"
    )

async def handle_pairs_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = update.message.text
    pairs = [p.strip().upper() for p in text.split(",") if p.strip()]
    if pairs:
        user_currency_pairs[chat_id] = pairs
        await update.message.reply_text(f"✅ Now tracking: {', '.join(pairs)}")
    else:
        await update.message.reply_text("❌ Invalid input. Send comma-separated currency pairs.")

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in user_currency_pairs:
        del user_currency_pairs[chat_id]
        await update.message.reply_text("🛑 Stopped tracking your currency pairs.")
    else:
        await update.message.reply_text("ℹ️ You’re not tracking any pairs.")

# === Background Task ===
async def monitor_loop(app: Application):
    while True:
        for chat_id, pairs in user_currency_pairs.items():
            for symbol in pairs:
                try:
                    signal, exchange_used = get_signal_for_pair(symbol)
                    key = (chat_id, symbol)
                    if signal:
                        print(f"{symbol} ({exchange_used}): {signal}")
                        if signal in ["STRONG_BUY", "STRONG_SELL"] and last_signals.get(key) != signal:
                            message = f"🚨 {symbol} Alert: {signal} on {exchange_used}!"
                            await app.bot.send_message(chat_id=chat_id, text=message)
                            send_twilio_sms(message)
                            last_signals[key] = signal
                    else:
                        print(f"⚠️ No exchange data for {symbol}")
                except Exception as e:
                    print(f"❌ Error with {symbol}: {e}")
        await asyncio.sleep(300)

# === Webhook Setup ===
async def post_init(app: Application):
    print("Setting webhook...")
    await app.bot.set_webhook(url=WEBHOOK_URL)
    asyncio.create_task(monitor_loop(app))
    print("Webhook set and monitor loop started.")

# === Main Function (not async) ===
def main():
    port = int(os.getenv("PORT", 5000))

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).post_init(post_init).build()

    # Delete webhook before running (run async setup task manually)
    async def init():
        print("Deleting previous webhook...")
        await app.bot.delete_webhook()
        print("Deleted.")

    asyncio.get_event_loop().run_until_complete(init())

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_pairs_input))

    print(f"Starting webhook on port {port}")
    app.run_webhook(
        listen="0.0.0.0",
        port=port,
        webhook_url=WEBHOOK_URL,
        webhook_path=f"/{TELEGRAM_TOKEN}"
    )

if __name__ == "__main__":
    main()
