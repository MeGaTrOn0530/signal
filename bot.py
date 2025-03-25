import json
import os
import logging
import random
from datetime import datetime
import requests
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Get environment variables
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY", "")
METALS_API_KEY = os.getenv("METALS_API_KEY", "")
EXCHANGE_RATE_API_KEY = os.getenv("EXCHANGE_RATE_API_KEY", "")

# File to store user alerts
ALERTS_FILE = "user_alerts.json"
# File to store initial prices
INITIAL_PRICES_FILE = "initial_prices.json"

# Conversation states
SELECTING_CURRENCY = 1
ENTERING_PRICE = 2
DELETING_ALERT = 3

# Initialize alerts storage
if os.path.exists(ALERTS_FILE):
    with open(ALERTS_FILE, 'r') as f:
        user_alerts = json.load(f)
else:
    user_alerts = {}

# Initialize initial prices storage
if os.path.exists(INITIAL_PRICES_FILE):
    with open(INITIAL_PRICES_FILE, 'r') as f:
        initial_prices = json.load(f)
else:
    initial_prices = {}

# Save alerts to file
def save_alerts():
    with open(ALERTS_FILE, 'w') as f:
        json.dump(user_alerts, f)

# Save initial prices to file
def save_initial_prices():
    with open(INITIAL_PRICES_FILE, 'w') as f:
        json.dump(initial_prices, f)

# Last prices for simulation
last_prices = {
    "BTCUSD": None,
    "XAUUSD": 3017.64,  # Starting price from screenshot
    "GBPJPY": 195.50    # Starting price
}

# Get price data from APIs with simulation for more dynamic prices
async def get_price(symbol):
    symbol = symbol.upper()
    
    try:
        if symbol == "BTCUSD":
            # CoinGecko API for Bitcoin
            response = requests.get("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd")
            data = response.json()
            price = data.get("bitcoin", {}).get("usd")
            if price:
                last_prices["BTCUSD"] = price
                return price
        
        # For XAUUSD and GBPJPY, simulate price changes to make them dynamic
        elif symbol == "XAUUSD" or symbol == "GBPJPY":
            current_price = last_prices[symbol]
            
            # Simulate market volatility (small random changes)
            if symbol == "XAUUSD":
                # Gold typically has smaller percentage moves
                change_percent = random.uniform(-0.1, 0.1)  # -0.1% to +0.1%
                new_price = current_price * (1 + change_percent/100)
                # Keep price within realistic range
                new_price = max(min(new_price, 3050), 2990)
            else:  # GBPJPY
                change_percent = random.uniform(-0.2, 0.2)  # -0.2% to +0.2%
                new_price = current_price * (1 + change_percent/100)
                # Keep price within realistic range
                new_price = max(min(new_price, 200), 190)
            
            last_prices[symbol] = new_price
            return new_price
    
    except Exception as e:
        logger.error(f"Error fetching {symbol}: {e}")
    
    # Fallback to last known price or default
    return last_prices.get(symbol) or {
        "BTCUSD": 65000.00,
        "XAUUSD": 3017.64,
        "GBPJPY": 195.50
    }.get(symbol)

# Main keyboard
def get_main_keyboard():
    keyboard = [
        ["💰 BTCUSD", "🥇 XAUUSD", "💱 GBPJPY"],
        ["⏰ Mening signallarim", "➕ Signal qo'shish"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# Currency selection keyboard for alerts
def get_currency_keyboard():
    keyboard = [
        ["💰 BTCUSD signal", "🥇 XAUUSD signal", "💱 GBPJPY signal"],
        ["🔙 Orqaga"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# Delete alert keyboard
def get_delete_keyboard(user_id):
    keyboard = []
    
    if user_id in user_alerts:
        for symbol, alerts in user_alerts[user_id].items():
            for i, alert in enumerate(alerts):
                keyboard.append([f"🗑️ {symbol}: {alert['target_price']:.2f}"])
    
    keyboard.append(["🔙 Orqaga"])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# Start command handler
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    
    # Initialize user in alerts dictionary if not exists
    if user_id not in user_alerts:
        user_alerts[user_id] = {}
        save_alerts()
    
    # Initialize user in initial prices dictionary if not exists
    if user_id not in initial_prices:
        initial_prices[user_id] = {}
        save_initial_prices()
    
    await update.message.reply_text(
        f"👋 Salom, {update.effective_user.first_name}!\n\n"
        "💹 Valyuta narxlarini ko'rish va signal qo'yish uchun tugmalardan foydalaning:",
        reply_markup=get_main_keyboard()
    )
    return ConversationHandler.END

# Handle text messages
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = str(update.effective_user.id)
    
    # Check if message is about viewing prices
    if "BTCUSD" in text and "signal" not in text:
        await show_price(update, "BTCUSD")
    elif "XAUUSD" in text and "signal" not in text:
        await show_price(update, "XAUUSD")
    elif "GBPJPY" in text and "signal" not in text:
        await show_price(update, "GBPJPY")
    
    # Handle alert management
    elif "Mening signallarim" in text:
        await show_user_alerts(update, context)
    
    elif "Signal qo'shish" in text:
        await update.message.reply_text(
            "📊 Qaysi valyuta juftligi uchun signal qo'ymoqchisiz?",
            reply_markup=get_currency_keyboard()
        )
        return SELECTING_CURRENCY
    
    # Handle currency selection for alert
    elif "signal" in text and any(currency in text for currency in ["BTCUSD", "XAUUSD", "GBPJPY"]):
        if "BTCUSD" in text:
            symbol = "BTCUSD"
        elif "XAUUSD" in text:
            symbol = "XAUUSD"
        else:
            symbol = "GBPJPY"
        
        context.user_data["selected_symbol"] = symbol
        current_price = await get_price(symbol)
        
        await update.message.reply_text(
            f"📊 {symbol} uchun signal qo'shish\n\n"
            f"📈 Joriy narx: ${current_price:,.2f}\n\n"
            f"⚠️ Iltimos, signal narxini kiriting (masalan: 3100):"
        )
        return ENTERING_PRICE
    
    # Handle back button
    elif "Orqaga" in text:
        await update.message.reply_text(
            "Asosiy menyuga qaytdingiz:",
            reply_markup=get_main_keyboard()
        )
        return ConversationHandler.END
    
    # Handle delete alert selection
    elif text.startswith("🗑️"):
        parts = text.split(":")
        if len(parts) >= 2:
            symbol_part = parts[0].replace("🗑️", "").strip()
            price_part = parts[1].strip()
            
            try:
                target_price = float(price_part)
                
                # Find and delete the alert
                if user_id in user_alerts and symbol_part in user_alerts[user_id]:
                    for i, alert in enumerate(user_alerts[user_id][symbol_part]):
                        if abs(alert["target_price"] - target_price) < 0.01:  # Allow small difference due to formatting
                            user_alerts[user_id][symbol_part].pop(i)
                            
                            # Remove empty lists
                            if not user_alerts[user_id][symbol_part]:
                                del user_alerts[user_id][symbol_part]
                            
                            save_alerts()
                            
                            await update.message.reply_text(
                                f"✅ Signal muvaffaqiyatli o'chirildi:\n"
                                f"{symbol_part}: {target_price:,.2f}",
                                reply_markup=get_main_keyboard()
                            )
                            return ConversationHandler.END
            except ValueError:
                pass
            
            await update.message.reply_text(
                "⚠️ Signal topilmadi yoki allaqachon o'chirilgan.",
                reply_markup=get_main_keyboard()
            )
            return ConversationHandler.END
    
    return ConversationHandler.END

# Show price for a symbol with image
async def show_price(update: Update, symbol):
    user_id = str(update.effective_user.id)
    price = await get_price(symbol)
    
    if price:
        # Format price based on symbol
        if symbol == "BTCUSD":
            formatted_price = f"${price:,.2f}"
        elif symbol == "XAUUSD":
            formatted_price = f"${price:,.2f}"
        else:  # GBPJPY
            formatted_price = f"¥{price:,.2f}"
        
        # Check if this is the first time checking this symbol
        is_first_check = False
        if user_id not in initial_prices or symbol not in initial_prices[user_id]:
            if user_id not in initial_prices:
                initial_prices[user_id] = {}
            initial_prices[user_id][symbol] = price
            save_initial_prices()
            is_first_check = True
        
        # Determine which image to send
        image_path = "img/start.jpg"  # Default image
        message_text = f"💰 {symbol} joriy narxi: {formatted_price}\n📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        if not is_first_check:
            initial_price = initial_prices[user_id][symbol]
            price_diff = price - initial_price
            
            if price_diff < 0:
                # Price is lower than initial
                image_path = "img/start.jpg"
                message_text += f"\n\n📉 Dastlabki narxdan {abs(price_diff):.2f} past"
            elif price_diff >= 2:
                # Price is higher by 2 or more
                if symbol == "BTCUSD":
                    image_path = "img/BTCbuy.jpg"
                elif symbol == "XAUUSD":
                    image_path = "img/XUAbuy.jpg"
                elif symbol == "GBPJPY":
                    image_path = "img/GBPbuy.jpg"
                message_text += f"\n\n📈 Dastlabki narxdan {price_diff:.2f} yuqori"
            else:
                # Price is higher but less than 2
                image_path = "img/selbuy.jpg"
                message_text += f"\n\n📊 Dastlabki narxdan {price_diff:.2f} yuqori"
        
        # Send image with caption
        try:
            with open(image_path, 'rb') as photo:
                await update.message.reply_photo(
                    photo=photo,
                    caption=message_text + "\n\nSignal qo'yish uchun '➕ Signal qo'shish' tugmasini bosing",
                    reply_markup=get_main_keyboard()
                )
        except FileNotFoundError:
            # If image not found, send text message
            logger.error(f"Image not found: {image_path}")
            await update.message.reply_text(
                message_text + "\n\nSignal qo'yish uchun '➕ Signal qo'shish' tugmasini bosing",
                reply_markup=get_main_keyboard()
            )
    else:
        await update.message.reply_text(
            f"⚠️ {symbol} uchun ma'lumot olishda xatolik yuz berdi. Iltimos, keyinroq qayta urinib ko'ring.",
            reply_markup=get_main_keyboard()
        )

# Handle price input for alert
async def handle_price_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    text = update.message.text
    
    if "selected_symbol" not in context.user_data:
        await update.message.reply_text(
            "⚠️ Xatolik yuz berdi. Iltimos, qaytadan urinib ko'ring.",
            reply_markup=get_main_keyboard()
        )
        return ConversationHandler.END
    
    symbol = context.user_data["selected_symbol"]
    
    try:
        # Clean the input text from any non-numeric characters except decimal point
        clean_text = ''.join(c for c in text if c.isdigit() or c == '.')
        target_price = float(clean_text)
        
        # Add the alert
        if user_id not in user_alerts:
            user_alerts[user_id] = {}
        
        if symbol not in user_alerts[user_id]:
            user_alerts[user_id][symbol] = []
        
        # Add alert to user's alerts
        user_alerts[user_id][symbol].append({
            "target_price": target_price,
            "created_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "last_price": None
        })
        
        save_alerts()
        
        # Clear the user data
        del context.user_data["selected_symbol"]
        
        current_price = await get_price(symbol)
        direction = "ko'tarilganda" if target_price > current_price else "tushganda"
        
        await update.message.reply_text(
            f"✅ Signal muvaffaqiyatli qo'shildi!\n\n"
            f"🔔 {symbol} narxi {target_price:,.2f} ga {direction} xabar olasiz.\n"
            f"📈 Joriy narx: {current_price:,.2f}",
            reply_markup=get_main_keyboard()
        )
        
    except ValueError:
        await update.message.reply_text(
            "⚠️ Noto'g'ri format. Iltimos, raqam kiriting (masalan: 3100)",
            reply_markup=get_main_keyboard()
        )
    
    return ConversationHandler.END

# Show user's alerts
async def show_user_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    
    if user_id not in user_alerts or not user_alerts[user_id]:
        await update.message.reply_text(
            "🔔 Sizda hech qanday signal yo'q.\n\n"
            "Signal qo'shish uchun '➕ Signal qo'shish' tugmasini bosing.",
            reply_markup=get_main_keyboard()
        )
        return ConversationHandler.END
    
    message = "🔔 Sizning signallaringiz:\n\n"
    
    for symbol, alerts in user_alerts[user_id].items():
        if alerts:
            current_price = await get_price(symbol)
            message += f"📊 {symbol} - Joriy narx: {current_price:,.2f}\n"
            
            for i, alert in enumerate(alerts, 1):
                target = alert["target_price"]
                direction = "ko'tarilganda" if target > current_price else "tushganda"
                message += f"  {i}. {target:,.2f} ga {direction} ⏰\n"
            
            message += "\n"
    
    # Ask if user wants to delete alerts
    keyboard = [
        ["🗑️ Signalni o'chirish"],
        ["🔙 Orqaga"]
    ]
    
    await update.message.reply_text(
        message,
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    return DELETING_ALERT

# Handle delete alert request
async def handle_delete_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = str(update.effective_user.id)
    
    if "Signalni o'chirish" in text:
        if user_id in user_alerts and user_alerts[user_id]:
            await update.message.reply_text(
                "🗑️ O'chirmoqchi bo'lgan signalni tanlang:",
                reply_markup=get_delete_keyboard(user_id)
            )
            return DELETING_ALERT
        else:
            await update.message.reply_text(
                "🔔 Sizda hech qanday signal yo'q.",
                reply_markup=get_main_keyboard()
            )
            return ConversationHandler.END
    elif "Orqaga" in text:
        await update.message.reply_text(
            "Asosiy menyuga qaytdingiz:",
            reply_markup=get_main_keyboard()
        )
        return ConversationHandler.END
    
    return DELETING_ALERT

# Send enhanced alert notification with image
async def send_alert_notification(bot, user_id, symbol, target_price, current_price):
    # First message - Attention grabber
    await bot.send_message(
        chat_id=user_id,
        text="🚨 DIQQAT! 🚨 DIQQAT! 🚨 DIQQAT! 🚨",
        disable_notification=False  # Ensure notification sound plays
    )
    
    # Determine which image to send based on symbol and price movement
    image_path = "img/start.jpg"  # Default image
    
    if user_id in initial_prices and symbol in initial_prices[user_id]:
        initial_price = initial_prices[user_id][symbol]
        price_diff = current_price - initial_price
        
        if price_diff < 0:
            # Price is lower than initial
            image_path = "img/start.jpg"
        elif price_diff >= 2:
            # Price is higher by 2 or more
            if symbol == "BTCUSD":
                image_path = "img/BTCbuy.jpg"
            elif symbol == "XAUUSD":
                image_path = "img/XUAbuy.jpg"
            elif symbol == "GBPJPY":
                image_path = "img/GBPbuy.jpg"
        else:
            # Price is higher but less than 2
            image_path = "img/selbuy.jpg"
    
    # Alert details with eye-catching formatting
    alert_message = (
        f"🔔🔔🔔 SIGNAL ISHLADI! 🔔🔔🔔\n\n"
        f"💢💢💢 {symbol} 💢💢💢\n\n"
        f"🎯 Belgilangan narx: {target_price:,.2f}\n"
        f"📈 Joriy narx: {current_price:,.2f}\n"
        f"⏰ Vaqt: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        f"❗️❗️❗️ SIGNAL ISHLADI ❗️❗️❗️"
    )
    
    # Send image with caption
    try:
        with open(image_path, 'rb') as photo:
            await bot.send_photo(
                chat_id=user_id,
                photo=photo,
                caption=alert_message,
                disable_notification=False  # Ensure notification sound plays
            )
    except FileNotFoundError:
        # If image not found, send text message
        logger.error(f"Image not found: {image_path}")
        await bot.send_message(
            chat_id=user_id,
            text=alert_message,
            disable_notification=False  # Ensure notification sound plays
        )
    
    # Third message - Final attention grabber
    await bot.send_message(
        chat_id=user_id,
        text="🔊 SIGNAL! 🔊 SIGNAL! 🔊 SIGNAL! 🔊",
        disable_notification=False  # Ensure notification sound plays
    )

# Check alerts periodically
async def check_alerts(context: ContextTypes.DEFAULT_TYPE):
    logger.info("Checking alerts...")
    for user_id, user_data in list(user_alerts.items()):
        for symbol, alerts in list(user_data.items()):
            current_price = await get_price(symbol)
            
            if current_price is None:
                logger.warning(f"Could not get price for {symbol}")
                continue
            
            logger.info(f"Checking {len(alerts)} alerts for {symbol}. Current price: {current_price}")
            
            for alert_index, alert in enumerate(alerts[:]):
                target_price = alert["target_price"]
                last_price = alert.get("last_price")
                
                # First time checking this alert
                if last_price is None:
                    alert["last_price"] = current_price
                    continue
                
                logger.info(f"Alert {alert_index}: target={target_price}, last={last_price}, current={current_price}")
                
                # Check if price has crossed the target
                if ((target_price >= last_price and target_price <= current_price) or
                    (target_price <= last_price and target_price >= current_price)):
                    
                    logger.info(f"Alert triggered for user {user_id}: {symbol} at {target_price}")
                    
                    # Send enhanced notification
                    try:
                        await send_alert_notification(
                            context.bot, 
                            user_id, 
                            symbol, 
                            target_price, 
                            current_price
                        )
                        
                        # Remove the alert after triggering
                        if alert_index < len(user_alerts[user_id][symbol]):
                            user_alerts[user_id][symbol].pop(alert_index)
                            
                            # Remove empty lists
                            if not user_alerts[user_id][symbol]:
                                del user_alerts[user_id][symbol]
                            
                            save_alerts()
                        
                    except Exception as e:
                        logger.error(f"Error sending alert to {user_id}: {e}")
                
                # Update last price
                if alert_index < len(alerts):
                    alerts[alert_index]["last_price"] = current_price

# Main function
def main():
    # Check if token is available
    if not TOKEN:
        logger.error("No bot token found in environment variables. Please set TELEGRAM_BOT_TOKEN in .env file.")
        return
    
    # Create application
    application = Application.builder().token(TOKEN).build()
    
    # Add conversation handler
    conv_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
        ],
        states={
            SELECTING_CURRENCY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
            ],
            ENTERING_PRICE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_price_input)
            ],
            DELETING_ALERT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_delete_request)
            ]
        },
        fallbacks=[CommandHandler("start", start)]
    )
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(conv_handler)
    
    # Add job to check alerts every minute
    job_queue = application.job_queue
    job_queue.run_repeating(check_alerts, interval=60, first=10)
    
    # Start the bot
    print("✅ Bot ishga tushdi!")
    application.run_polling()

if __name__ == "__main__":
    main()