import os
import json
import logging
import sys
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, CallbackContext
from telegram.error import Conflict
from firebase_admin import credentials, firestore, initialize_app, auth
from datetime import datetime

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

async def create_firebase_user(telegram_id: str, phone: str):
    """Create Firebase auth user with Telegram ID as UID"""
    try:
        user = auth.create_user(
            uid=str(telegram_id),
            phone_number=phone
        )
        logger.info(f"Firebase user created: {user.uid}")
        return user
    except Exception as e:
        logger.error(f"Error creating Firebase user: {str(e)}")
        raise

async def start(update: Update, context: CallbackContext) -> None:
    """Handle /start command with proper auth"""
    user = update.message.from_user
    user_id = str(user.id)
    
    user_ref = db.collection("users").document(user_id)
    user_data = await user_ref.get()

    if not user_data.exists:
        pending_users[user_id] = {
            "telegram_id": user_id,
            "first_name": user.first_name,
            "last_name": user.last_name or "",
            "balance": 0.00,
            "role": "user",
            "vtu_id": user_id[:6],
            "created_at": datetime.utcnow()
        }
        await update.message.reply_text("📞 Please send your phone number (e.g., +2347067479043).")
    else:
        await send_access(update, user_data.to_dict())

async def phone_number(update: Update, context: CallbackContext) -> None:
    """Handle phone number with validation"""
    user_id = str(update.message.from_user.id)
    phone = update.message.text
    
    # Basic phone number validation
    if not phone.startswith('+'):
        await update.message.reply_text("❌ Please include country code (e.g., +2347067479043)")
        return
    
    if user_id in pending_users:
        try:
            # Create Firebase auth user
            await create_firebase_user(user_id, phone)
            
            # Complete user profile
            user_info = pending_users.pop(user_id)
            user_info.update({
                "phone_number": phone,
                "email": "",
                "transactions": [],
                "updated_at": datetime.utcnow()
            })
            
            # Save to Firestore with security rules compliance
            await db.collection("users").document(user_id).set(user_info)
            await send_access(update, user_info, new_user=True)
            
        except Exception as e:
            await update.message.reply_text("🚨 Registration failed. Please try /start again.")
            logger.error(f"Registration error: {str(e)}")

async def send_access(update: Update, user_info: dict, new_user=False) -> None:
    """Send main menu with proper access controls"""
    welcome = "✅ Registration successful!" if new_user else "🔹 Welcome back!"
    text = f"{welcome}\n💰 Balance: ₦{user_info['balance']:.2f}"
    
    buttons = [
        [InlineKeyboardButton("🚀 Open App", web_app=WebAppInfo(url=WEB_URL))],
        [InlineKeyboardButton("💰 Check Balance", callback_data="balance")]
    ]
    
    # Only show admin button if user is admin
    if user_info.get("role") == "admin":
        buttons.append([InlineKeyboardButton("🔧 Admin Panel", callback_data="admin_panel")])
    
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))

async def handle_button(update: Update, context: CallbackContext) -> None:
    """Handle inline buttons with security checks"""
    query = update.callback_query
    await query.answer()
    
    user_id = str(query.from_user.id)
    user_ref = db.collection("users").document(user_id)
    user_data = await user_ref.get()
    
    if not user_data.exists:
        await query.edit_message_text("🚨 User not found. Please /start again.")
        return
    
    user_info = user_data.to_dict()
    
    if query.data == "balance":
        await query.edit_message_text(f"💰 Your Balance: ₦{user_info.get('balance', 0):.2f}")
    elif query.data == "admin_panel" and user_info.get("role") == "admin":
        await query.edit_message_text("🛠️ Admin Panel Activated")

async def add_transaction(user_id: str, amount: float, tx_type: str):
    """Securely add transaction with validation"""
    tx_ref = db.collection("users").document(user_id).collection("transactions").document()
    await tx_ref.set({
        "amount": amount,
        "type": tx_type,
        "timestamp": datetime.utcnow(),
        "status": "completed"
    })
    logger.info(f"Transaction added for {user_id}")

def create_app():
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Register handlers with proper filters
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.Regex(r'^\+\d+$'), 
        phone_number
    ))
    app.add_handler(CallbackQueryHandler(handle_button))
    
    return app

async def run_bot():
    app = create_app()
    
    try:
        # Clean start - delete any existing webhook
        await app.bot.delete_webhook(drop_pending_updates=True)
        
        # Start polling with conflict prevention
        await app.initialize()
        await app.start()
        await app.updater.start_polling(
            poll_interval=5.0,
            timeout=20,
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES
        )
        logger.info("Bot is now running in secure polling mode")
        
        # Keep alive with error handling
        while True:
            await asyncio.sleep(3600)
            
    except Conflict:
        logger.error("Another bot instance detected. Shutting down...")
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")
    finally:
        if app.running:
            await app.updater.stop()
            await app.stop()
        sys.exit(0)

if __name__ == "__main__":
    # Configure environment
    os.environ['PYTHONWARNINGS'] = 'ignore::RuntimeWarning'
    
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
        sys.exit(0)
