import os
import json
import logging
import sys
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, CallbackContext
from telegram.error import Conflict, NetworkError
from firebase_admin import credentials, firestore, initialize_app

# --- Configuration ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Environment Validation ---
try:
    REQUIRED_ENV = ["BOT_TOKEN", "WEB_URL", "FIREBASE_CREDENTIALS"]
    for var in REQUIRED_ENV:
        if not os.environ.get(var):
            raise ValueError(f"Missing required environment variable: {var}")

    BOT_TOKEN = os.environ["BOT_TOKEN"]
    WEB_URL = os.environ["WEB_URL"]
    
    # Firebase Initialization
    firebase_creds = json.loads(os.environ["FIREBASE_CREDENTIALS"])
    cred = credentials.Certificate(firebase_creds)
    firebase_app = initialize_app(cred)
    db = firestore.client()
    logger.info("Firebase initialized successfully")

except Exception as e:
    logger.error(f"Initialization failed: {str(e)}")
    sys.exit(1)

# --- Bot Handlers ---
pending_users = {}

async def start(update: Update, context: CallbackContext) -> None:
    """Handle /start command"""
    user = update.message.from_user
    user_id = str(user.id)
    
    user_ref = db.collection("users").document(user_id)
    user_data = user_ref.get()

    if not user_data.exists:
        pending_users[user_id] = {
            "first_name": user.first_name,
            "last_name": user.last_name or "",
            "balance": 0.00,
            "role": "user",
            "vtu_id": user_id[:6]
        }
        await update.message.reply_text("📞 Please send your phone number.")
    else:
        await send_access(update, user_data.to_dict())

async def phone_number(update: Update, context: CallbackContext) -> None:
    """Handle phone number input"""
    user_id = str(update.message.from_user.id)
    
    if user_id in pending_users:
        user_info = pending_users.pop(user_id)
        user_info.update({
            "phone_number": update.message.text,
            "email": "",
            "transactions": []
        })
        
        db.collection("users").document(user_id).set(user_info)
        await send_access(update, user_info, new_user=True)

async def send_access(update: Update, user_info: dict, new_user=False) -> None:
    """Send main menu"""
    welcome = "✅ Registered!" if new_user else "🔹 Welcome back!"
    text = f"{welcome}\n💰 Balance: ₦{user_info['balance']:.2f}"
    
    buttons = [
        [InlineKeyboardButton("🚀 Open App", web_app=WebAppInfo(url=WEB_URL))],
        [InlineKeyboardButton("💰 Check Balance", callback_data="balance")]
    ]
    
    if user_info.get("role") == "admin":
        buttons.append([InlineKeyboardButton("🔧 Admin", callback_data="admin")])
    
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))

async def handle_button(update: Update, context: CallbackContext) -> None:
    """Handle inline buttons"""
    query = update.callback_query
    await query.answer()
    
    user_ref = db.collection("users").document(str(query.from_user.id))
    user_data = user_ref.get()
    
    if query.data == "balance":
        await query.edit_message_text(f"💰 Balance: ₦{user_data.get('balance'):.2f}")
    elif query.data == "admin":
        await query.edit_message_text("Admin panel")

def create_app():
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, phone_number))
    app.add_handler(CallbackQueryHandler(handle_button))
    
    return app

async def run_bot():
    app = create_app()
    
    if os.environ.get('RENDER'):
        # Free tier solution - use polling with keep-alive
        try:
            await app.initialize()
            await app.start()
            
            # Start polling with timeout handling
            await app.updater.start_polling(
                poll_interval=3.0,
                timeout=10,
                drop_pending_updates=True
            )
            
            logger.info("Bot running in polling mode (Render free tier)")
            
            # Keep the application running
            while True:
                await asyncio.sleep(3600)  # Sleep for 1 hour
                
        except Conflict:
            logger.error("Another instance is running. Exiting.")
            sys.exit(1)
        except Exception as e:
            logger.error(f"Bot failed: {str(e)}")
            sys.exit(1)
    else:
        # Local development - standard polling
        try:
            await app.initialize()
            await app.updater.start_polling()
            logger.info("Bot running in polling mode (local development)")
            await app.idle()
        except Exception as e:
            logger.error(f"Bot failed: {str(e)}")
            sys.exit(1)

if __name__ == "__main__":
    os.environ['PYTHONWARNINGS'] = 'ignore::RuntimeWarning'
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
        sys.exit(0)
