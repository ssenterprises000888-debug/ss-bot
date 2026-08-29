import os
import re
import logging
from datetime import datetime
from typing import Dict, Any
from threading import Thread
from flask import Flask

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)
import aiohttp
from dotenv import load_dotenv

load_dotenv()

# --- Configuration (Read securely from Environment) ---
BOT_TOKEN = os.getenv('BOT_TOKEN', '').strip().strip('"').strip("'")
ADMIN_CHAT_ID = int(os.getenv('ADMIN_CHAT_ID', '1443007174'))
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '').strip().strip('"').strip("'")

# Logging Setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Render Port Binding Server
web_app = Flask(__name__)

@web_app.route('/')
@web_app.route('/health')
def home():
    return "SS Enterprises Bot is running live!"

def run_web_server():
    port = int(os.environ.get('PORT', 10000))
    web_app.run(host='0.0.0.0', port=port, use_reloader=False)

# In-memory Database
user_data_store = {}

SYSTEM_PROMPT = """You are Deepak, a helpful assistant at SS Enterprises - a service shop in India that provides CCTV installation, electrical work, computer/laptop repair, and intercom services. 
You speak in Hinglish (Hindi + English) and are polite and professional.
Your goal is to collect customer details: Name, Mobile Number, Address, and Preferred Time for service.
Always ask one question at a time and wait for the answer.
Start conversations with a warm greeting and ask for their name first.
If they ask about services, explain that we offer CCTV, Electrical, Computer/Laptop repair, and Intercom services.
Keep responses short and friendly."""

class DeepSeekBot:
    def __init__(self):
        self.gemini_endpoint = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
    
    async def ask_gemini(self, user_message: str, conversation_history: list = None) -> str:
        if not GEMINI_API_KEY:
            logger.error("GEMINI_API_KEY is not set in Environment Variables.")
            return "नमस्ते! मैं दीपक, SS Enterprises से। हम CCTV, Electrical, Computer/Laptop repair और Intercom की सर्विस देते हैं। आपका शुभ नाम क्या है?"
            
        url = f"{self.gemini_endpoint}?key={GEMINI_API_KEY}"
        headers = {"Content-Type": "application/json"}
        
        prompt_text = f"{SYSTEM_PROMPT}\n\nUser: {user_message}"
        if conversation_history:
            context = "\n".join([msg['parts'][0]['text'] for msg in conversation_history[-6:]])
            prompt_text = f"{SYSTEM_PROMPT}\n\nPrevious conversation:\n{context}\n\nUser: {user_message}"
        
        payload = {
            "contents": [
                {
                    "parts": [{"text": prompt_text}]
                }
            ]
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload, timeout=12) as response:
                    if response.status == 200:
                        data = await response.json()
                        candidates = data.get('candidates', [])
                        if candidates and 'content' in candidates[0]:
                            parts = candidates[0]['content'].get('parts', [])
                            if parts and 'text' in parts[0]:
                                return parts[0]['text'].strip()
                    else:
                        resp_error = await response.text()
                        logger.error(f"Gemini API Error {response.status}: {resp_error}")
        except Exception as e:
            logger.error(f"Gemini Connection Exception: {e}")
        
        return "नमस्ते! मैं दीपक, SS Enterprises से बात कर रहा हूँ। हम CCTV, Electrical, Computer/Laptop repair और Intercom की सर्विस देते हैं। आपका शुभ नाम क्या है?"
    
    async def extract_details(self, user_message: str) -> Dict[str, Any]:
        details = {}
        phone_match = re.search(r'\b\d{10}\b', user_message)
        if phone_match:
            details['phone'] = phone_match.group()
        if 'my name is' in user_message.lower():
            name_start = user_message.lower().find('my name is') + 10
            details['name'] = user_message[name_start:].strip()
        elif 'naam' in user_message.lower() or 'name' in user_message.lower():
            words = user_message.split()
            if len(words) <= 4:
                details['name'] = user_message.strip()
        elif len(user_message.split()) <= 2 and not any(char.isdigit() for char in user_message):
            details['name'] = user_message.strip()
        return details
    
    async def generate_lead_ticket(self, user_id: int, details: Dict, username: str = None) -> str:
        ticket = f"""
📋 *NEW LEAD - SS Enterprises*
━━━━━━━━━━━━━━━━━━
👤 *Customer:* {details.get('name', 'Not provided')}
📱 *Phone:* {details.get('phone', 'Not provided')}
📍 *Address:* {details.get('address', 'Not provided')}
⏰ *Preferred Time:* {details.get('time', 'Not provided')}
📅 *Date:* {datetime.now().strftime('%d-%m-%Y %H:%M')}
🆔 *User ID:* {user_id}
👤 *Username:* @{username or 'Not set'}
━━━━━━━━━━━━━━━━━━
📌 *Status:* New Lead - Ready for assignment
👨‍🔧 *Technician Assigned:* Pending
"""
        return ticket

deepseek = DeepSeekBot()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or "User"
    
    if user_id == ADMIN_CHAT_ID:
        keyboard = [
            [InlineKeyboardButton("📢 Broadcast Message", callback_data='broadcast')],
            [InlineKeyboardButton("📊 View Leads", callback_data='view_leads')],
            [InlineKeyboardButton("📝 View All Customers", callback_data='view_customers')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"👋 *Welcome Admin!*\n\n"
            f"Hello {username}, आप SS Enterprises के Admin Panel में हैं।\n\n"
            f"📌 *Available Actions:*\n"
            f"• Broadcast message to all customers\n"
            f"• View all leads\n"
            f"• Manage customers\n\n"
            f"किसी भी option को चुनें।",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    else:
        user_data_store[user_id] = {
            'role': 'customer',
            'conversation': [],
            'stage': 'greeting',
            'details': {},
            'username': username
        }
        
        greeting = await deepseek.ask_gemini(
            "Start a new conversation with a customer. Greet them warmly and ask for their name.",
            []
        )
        
        await update.message.reply_text(
            f"👋 {greeting}\n\n"
            f"*SS Enterprises*\n"
            f"🏢 CCTV | ⚡ Electrical | 💻 Computer/Laptop | 📞 Intercom",
            parse_mode='Markdown'
        )

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id != ADMIN_CHAT_ID:
        await update.message.reply_text("⛔ आपके पास इस command का access नहीं है।")
        return
    
    if not context.args:
        await update.message.reply_text(
            "📢 *Broadcast Command*\n\n"
            "Usage: `/broadcast <message>`\n\n"
            "Example: `/broadcast आज नई सर्विस पर विशेष छूट उपलब्ध है!`",
            parse_mode='Markdown'
        )
        return
    
    message = ' '.join(context.args)
    customers = [uid for uid in user_data_store.keys() if uid != ADMIN_CHAT_ID]
    
    if not customers:
        await update.message.reply_text("❌ कोई customer data उपलब्ध नहीं है।")
        return
    
    success_count = 0
    for cust_id in customers:
        try:
            await context.bot.send_message(
                chat_id=cust_id,
                text=f"📢 *SS Enterprises Update*\n\n{message}\n\n_Automated Broadcast_",
                parse_mode='Markdown'
            )
            success_count += 1
        except Exception as e:
            logger.error(f"Failed to send broadcast to {cust_id}: {e}")
    
    await update.message.reply_text(
        f"✅ Broadcast sent successfully!\n"
        f"📤 Sent to: {success_count} customers\n"
        f"📝 Message: {message}"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_message = update.message.text
    
    if user_id == ADMIN_CHAT_ID:
        if user_message.startswith('/broadcast'):
            return
        if user_message.startswith('/'):
            await update.message.reply_text("⚠️ Please use /start to see available options.")
            return
    
    if user_id not in user_data_store:
        user_data_store[user_id] = {
            'role': 'customer',
            'conversation': [],
            'stage': 'greeting',
            'details': {},
            'username': update.effective_user.username
        }
    
    user_data = user_data_store[user_id]
    conversation_history = user_data['conversation']
    ai_response = await deepseek.ask_gemini(user_message, conversation_history)
    
    conversation_history.append({"role": "user", "parts": [{"text": user_message}]})
    conversation_history.append({"role": "assistant", "parts": [{"text": ai_response}]})
    
    extracted = await deepseek.extract_details(user_message)
    if extracted:
        user_data['details'].update(extracted)
    
    msg_low = user_message.lower()
    if any(k in msg_low for k in ['address', 'gali', 'road', 'colony', 'nagar', 'house', 'ward', 'near', 'chawk', 'bihar', 'siwan']):
        user_data['details']['address'] = user_message.strip()
    if any(k in msg_low for k in ['time', 'baje', 'am', 'pm', 'morning', 'evening', 'kal', 'aaj', 'dopahar']):
        user_data['details']['time'] = user_message.strip()
    
    required_fields = ['name', 'phone', 'address', 'time']
    if all(field in user_data['details'] for field in required_fields):
        ticket = await deepseek.generate_lead_ticket(
            user_id, 
            user_data['details'],
            user_data.get('username')
        )
        
        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=ticket,
            parse_mode='Markdown'
        )
        
        await update.message.reply_text(
            f"✅ *धन्यवाद!* आपकी details सफलतापूर्वक दर्ज कर ली गई हैं।\n\n"
            f"📞 *Technician Support:* +91-XXXXXXXXXX\n"
            f"⏰ हमारे technician निर्धारित समय पर संपर्क करेंगे।\n\n"
            f"*SS Enterprises*\n"
            f"सेवा का अवसर देने के लिए धन्यवाद! 🙏",
            parse_mode='Markdown'
        )
        
        user_data['stage'] = 'completed'
        user_data['details'] = {}
        user_data['conversation'] = []
        return
    
    await update.message.reply_text(ai_response)

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id != ADMIN_CHAT_ID:
        await query.edit_message_text("⛔ Access denied.")
        return
    
    if query.data == 'broadcast':
        await query.edit_message_text(
            "📢 *Broadcast Tool*\n\n"
            "Send message using:\n"
            "`/broadcast <your message>`\n\n"
            "Example:\n"
            "`/broadcast Happy Diwali to all customers!`",
            parse_mode='Markdown'
        )
    elif query.data == 'view_leads':
        await query.edit_message_text(
            f"📊 *Leads Dashboard*\n\n"
            f"Total Customers in memory: {len(user_data_store)}\n\n"
            "📌 Use /start for main menu"
        )
    elif query.data == 'view_customers':
        customers = [uid for uid in user_data_store.keys() if uid != ADMIN_CHAT_ID]
        await query.edit_message_text(
            f"👥 *Customers List*\n\n"
            f"Total Active Users: {len(customers)}\n\n"
            "📌 Use /start for main menu"
        )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}")

def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN is missing! Please configure it in Environment Variables.")
        return

    server_thread = Thread(target=run_web_server, daemon=True)
    server_thread.start()
    
    application = Application.builder().token(BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("broadcast", broadcast_command))
    application.add_handler(CallbackQueryHandler(callback_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_error_handler(error_handler)
    
    print("🤖 SS Enterprises Bot is starting...")
    print(f"🔑 Admin ID: {ADMIN_CHAT_ID}")
    print("✅ Bot is ready!")
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
    
