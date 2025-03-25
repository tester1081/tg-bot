import os
import json
from firebase_admin import credentials, firestore, initialize_app
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, CallbackContext

# Load Railway Environment Variables
BOT_TOKEN = os.environ["BOT_TOKEN"]
WEB_URL = os.environ["WEB_URL"]
FIREBASE_CREDENTIALS = os.environ["FIREBASE_CREDENTIALS"]  # Loaded as a string

# Convert JSON string back to dictionary
firebase_creds_dict = json.loads(FIREBASE_CREDENTIALS)

# Initialize Firebase
cred = credentials.Certificate(firebase_creds_dict)
firebase_app = initialize_app(cred)
db = firestore.client()

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
            "balance": 0.00,  # Default balance
            "role": "user",  # Default role
            "vtu_id": user_id[:6]  # Unique VTU ID based on Telegram ID
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
            "email": "",  # Can be updated later
            "referred_by": "",  # If referral system exists
            "transactions": [],  # Empty list for transaction history
        })

        # Save to Firestore
        db.collection("users").document(user_id).set(user_info)

        await send_access(update, user_info, new_registration=True)

async def send_access(update: Update, user_info: dict, new_registration: bool) -> None:
    """Sends main menu with inline buttons (opens web app inside Telegram)."""
    role = user_info.get("role", "user")

    # ✅ Show registration success message only ONCE
    welcome_text = f"✅ Registration successful, {user_info['first_name']}!" if new_registration else "🔹 Welcome back!"

    keyboard = [
        [InlineKeyboardButton("🚀 Open VeltraWave", web_app=WebAppInfo(url=WEB_URL))],  # Open inside Telegram
        [InlineKeyboardButton("💰 Check Balance", callback_data="check_balance")],
    ]

    if role == "admin":
        keyboard.append([InlineKeyboardButton("🔧 Admin Panel", callback_data="admin_panel")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(f"{welcome_text}\n💰 **Balance:** ₦{user_info['balance']:.2f}", reply_markup=reply_markup)

async def button_click(update: Update, context: CallbackContext) -> None:
    """Handles button clicks inside Telegram (for balance)."""
    query = update.callback_query
    query.answer()
    user_id = str(query.from_user.id)

    # Retrieve user data
    user_ref = db.collection("users").document(user_id)
    user_data = user_ref.get()
    
    if not user_data.exists:
        await query.message.reply_text("🚨 User data not found. Please restart with /start")
        return

    user_info = user_data.to_dict()

    if query.data == "check_balance":
        await query.edit_message_text(f"💰 **Your Balance:** ₦{user_info['balance']:.2f}")

    elif query.data == "admin_panel":
        await query.edit_message_text("🔧 Welcome to the Admin Panel!\n(No external links, just Telegram)")

# Initialize the bot
app = Application.builder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, phone_number))
app.add_handler(CallbackQueryHandler(button_click))

print("Bot is running...")
app.run_polling()
