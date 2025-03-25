import os
import json
import logging
from firebase_admin import credentials, firestore, initialize_app
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, CallbackContext

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Load Environment Variables
try:
    BOT_TOKEN = os.environ["BOT_TOKEN"]
    WEB_URL = os.environ["WEB_URL"]
    FIREBASE_CREDENTIALS = os.environ["FIREBASE_CREDENTIALS"]
    
    # Initialize Firebase
    firebase_creds_dict = json.loads(FIREBASE_CREDENTIALS)
    cred = credentials.Certificate(firebase_creds_dict)
    firebase_app = initialize_app(cred)
    db = firestore.client()
    logger.info("Firebase initialized successfully")
except Exception as e:
    logger.error(f"Initialization failed: {str(e)}")
    raise

# Temporary storage for user data before saving
pending_users = {}

async def start(update: Update, context: CallbackContext) -> None:
    """Handles the /start command."""
    user = update.message.from_user
    user_id = str(user.id)

    # Check if user exists in Firestore
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
        await send_access(update, user_data.to_dict(), new_registration=False)

async def phone_number(update: Update, context: CallbackContext) -> None:
    """Handles the phone number input from the user."""
    user_id = str(update.message.from_user.id)
    phone_number = update.message.text

    if user_id in pending_users:
        user_info = pending_users.pop(user_id)
        user_info.update({
            "user_id": user_id,
            "phone_number": phone_number,
            "email": "",
            "referred_by": "",
            "transactions": [],
        })

        # Save to Firestore
        db.collection("users").document(user_id).set(user_info)
        logger.info(f"New user registered: {user_id}")
        await send_access(update, user_info, new_registration=True)

async def send_access(update: Update, user_info: dict, new_registration: bool) -> None:
    """Sends main menu with inline buttons."""
    role = user_info.get("role", "user")
    welcome_text = f"✅ Registration successful, {user_info['first_name']}!" if new_registration else "🔹 Welcome back!"

    keyboard = [
        [InlineKeyboardButton("🚀 Open VeltraWave", web_app=WebAppInfo(url=WEB_URL))],
        [InlineKeyboardButton("💰 Check Balance", callback_data="check_balance")],
    ]

    if role == "admin":
        keyboard.append([InlineKeyboardButton("🔧 Admin Panel", callback_data="admin_panel")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"{welcome_text}\n💰 **Balance:** ₦{user_info['balance']:.2f}", 
        reply_markup=reply_markup
    )

async def button_click(update: Update, context: CallbackContext) -> None:
    """Handles button clicks inside Telegram."""
    query = update.callback_query
    await query.answer()  # Fixed: Added await here
    
    user_id = str(query.from_user.id)
    user_ref = db.collection("users").document(user_id)
    user_data = user_ref.get()
    
    if not user_data.exists:
        await query.message.reply_text("🚨 User data not found. Please restart with /start")
        return

    user_info = user_data.to_dict()

    if query.data == "check_balance":
        await query.edit_message_text(f"💰 **Your Balance:** ₦{user_info['balance']:.2f}")
    elif query.data == "admin_panel":
        await query.edit_message_text("🔧 Welcome to the Admin Panel!")

def main() -> None:
    """Run the bot."""
    try:
        app = Application.builder().token(BOT_TOKEN).build()
        
        # Add handlers
        app.add_handler(CommandHandler("start", start))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, phone_number))
        app.add_handler(CallbackQueryHandler(button_click))

        logger.info("Bot starting...")
        app.run_polling()
    except Exception as e:
        logger.error(f"Bot failed: {str(e)}")
        raise

if __name__ == "__main__":
    # Suppress port warning for Render
    os.environ['PYTHONWARNINGS'] = 'ignore::RuntimeWarning'
    main()
