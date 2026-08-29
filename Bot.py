import os
import json
import logging
import re
from datetime import datetime
from typing import Dict, Any, Optional

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

# Load environment variables
load_dotenv()

# Configuration
BOT_TOKEN = os.getenv('BOT_TOKEN', '8768428239:AAHpNjXHdvtz8vybglg2R9tSvv0uiyQ_tNA')
ADMIN_CHAT_ID = int(os.getenv('ADMIN_CHAT_ID', '1443007174'))
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', 'AQ.Ab8RN6JJr7_sEO6g9V11fkUgBCmm12MWuGZVkU74vcQy6WPY8g')

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Database (in-memory)
user_data_store = {}

# AI System Prompt
SYSTEM_PROMPT = """You are Deepak, a helpful assistant at SS Enterprises - a service shop in India that provides CCTV installation, electrical work, computer/laptop repair, and intercom services. 
You speak in Hinglish (Hindi + English) and are polite and professional.
Your goal is to collect customer details: Name, Mobile Number, Address, and Preferred Time for service.
Always ask one question at a time and wait for the answer.
Start conversations with a warm greeting and ask for their name first.
If they ask about services, explain that we offer CCTV, Electrical, Computer/Laptop repair, and Intercom services.
Keep responses short and friendly."""

class DeepSeekBot:
    def __init__(self):
        self.gemini_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
    
    async def ask_gemini(self, user_message: str, conversation_history: list = None) -> str:
        """Send message to Gemini AI and get response"""
        headers = {
            "x-goog-api-key": GEMINI_API_KEY,
            "Content-Type": "application/json"
        }
        
        messages = [{"role": "user", "parts": [{"text": SYSTEM_PROMPT + "\n\nUser: " + user_message}]}]
        
        if conversation_history:
            context = "\n".join([msg['parts'][0]['text'] for msg in conversation_history[-6:]])
            messages[0]['parts'][0]['text'] = SYSTEM_PROMPT + "\n\nPrevious conversation:\n" + context + "\n\nUser: " + user_message
        
        payload = {"contents": messages}
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.gemini_url, headers=headers, json=payload) as response:
                    if response.status == 200:
                        data = await response.json()
                        if 'candidates' in data and data['candidates']:
                            return data['candidates'][0]['content']['parts'][0]['text']
                        else:
                            return "माफ़ करें, मुझे समझ नहीं आया। कृपया दोबारा बताएं।"
                    else:
                        logger.error(f"Gemini API error: {response.status}")
                        return "क्षमा करें, मुझे कुछ तकनीकी समस्या हो रही है। कृपया थोड़ी देर बाद प्रयास करें।"
        except Exception as e:
            logger.error(f"Error calling Gemini API: {e}")
            return "क्षमा करें, मुझे कुछ तकनीकी समस्या हो रही है। कृपया थोड़ी देर बाद प्रयास करें।"
    
    async def extract_details(self, user_message: str) -> Dict[str, Any]:
        """Extract customer details from conversation"""
        details = {}
        
        # Check for mobile number (10 digits)
        phone_match = re.search(r'\b\d{10}\b', user_message)
        if phone_match:
            details['phone'] = phone_match.group()
        
        # Check for name
        if 'my name is' in user_message.lower():
            name_start = user_message.lower().find('my name is') + 10
            details['name'] = user_message[name_start:].strip()
        elif 'name' in user_message.lower() and len(user_message.split()) < 5:
            details['name'] = user_message.strip()
        
        return details
    
    async def generate_lead_ticket(self, user_id: int, details: Dict, username: str = None) -> str:
        """Generate formatted lead ticket for admin"""
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

# Initialize bot
deepseek = DeepSeekBot()

# Command Handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user_id = update.effective_user.id
    username = update.effective_user.username or "User"
    
    # Check if admin
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
            f"किसी भी command या button का उपयोग करें।",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    else:
        # Initialize customer session
        if user_id not in user_data_store:
            user_data_store[user_id] = {
                'role': 'customer',
                'conversation': [],
                'stage': 'greeting',
                'details': {},
                'username': username
            }
        
        # Get AI greeting
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
    """Handle broadcast command (admin only)"""
    user_id = update.effective_user.id
    
    if user_id != ADMIN_CHAT_ID:
        await update.message.reply_text("⛔ आपके पास इस command का access नहीं है।")
        return
    
    if not context.args:
        await update.message.reply_text(
            "📢 *Broadcast Command*\n\n"
            "Usage: `/broadcast <message>`\n\n"
            "Example: `/broadcast आज शाम 7 बजे से new offers available हैं!`",
            parse_mode='Markdown'
        )
        return
    
    message = ' '.join(context.args)
    
    # Get all customers (excluding admin)
    customers = [uid for uid in user_data_store.keys() if uid != ADMIN_CHAT_ID]
    
    if not customers:
        await update.message.reply_text("❌ कोई customer नहीं मिला।")
        return
    
    success_count = 0
    for cust_id in customers:
        try:
            await context.bot.send_message(
                chat_id=cust_id,
                text=f"📢 *SS Enterprises Update*\n\n{message}\n\n_This is an automated broadcast._",
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
    """Handle all incoming messages"""
    user_id = update.effective_user.id
    user_message = update.message.text
    
    # Handle admin commands
    if user_id == ADMIN_CHAT_ID:
        if user_message.startswith('/broadcast'):
            return
        if user_message.startswith('/'):
            await update.message.reply_text(
                "⚠️ Unknown command. Please use /start to see available options."
            )
            return
    
    # Initialize user data if not exists
    if user_id not in user_data_store:
        user_data_store[user_id] = {
            'role': 'customer',
            'conversation': [],
            'stage': 'greeting',
            'details': {},
            'username': update.effective_user.username
        }
    
    user_data = user_data_store[user_id]
    
    # Get AI response
    conversation_history = user_data['conversation']
    ai_response = await deepseek.ask_gemini(user_message, conversation_history)
    
    # Store conversation
    conversation_history.append({"role": "user", "parts": [{"text": user_message}]})
    conversation_history.append({"role": "assistant", "parts": [{"text": ai_response}]})
    
    # Extract details
    extracted = await deepseek.extract_details(user_message)
    
    # Update customer details
    if extracted:
        user_data['details'].update(extracted)
    
    # Check for address and time in message
    if 'address' in user_message.lower() or 'house' in user_message.lower() or 'street' in user_message.lower():
        user_data['details']['address'] = user_message.strip()
    if 'time' in user_message.lower() or 'am' in user_message.lower() or 'pm' in user_message.lower() or 'clock' in user_message.lower():
        user_data['details']['time'] = user_message.strip()
    
    # Check if all details are collected
    required_fields = ['name', 'phone', 'address', 'time']
    if all(field in user_data['details'] for field in required_fields):
        # Generate lead ticket
        ticket = await deepseek.generate_lead_ticket(
            user_id, 
            user_data['details'],
            user_data.get('username')
        )
        
        # Send to admin
        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=ticket,
            parse_mode='Markdown'
        )
        
        # Send technician number to customer
        await update.message.reply_text(
            f"✅ *धन्यवाद!* आपकी details सफलतापूर्वक प्राप्त हो गईं।\n\n"
            f"📞 *Our Technician:* +91-XXXXXXXXXX\n"
            f"⏰ आपसे जल्द ही संपर्क किया जाएगा।\n\n"
            f"*SS Enterprises*\n"
            f"सेवा के लिए धन्यवाद! 🙏",
            parse_mode='Markdown'
        )
        
        # Reset conversation
        user_data['stage'] = 'completed'
        user_data['details'] = {}
        user_data['conversation'] = []
        
        return
    
    # Send AI response
    await update.message.reply_text(ai_response)

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button callbacks"""
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
            "`/broadcast Happy New Year to all customers!`",
            parse_mode='Markdown'
        )
    
    elif query.data == 'view_leads':
        await query.edit_message_text(
            "📊 *Leads Dashboard*\n\n"
            f"Total Customers: {len(user_data_store)}\n"
            f"Active Users: {len([u for u in user_data_store.values() if u.get('stage') != 'completed'])}\n\n"
            "📌 Use /start for main menu"
        )
    
    elif query.data == 'view_customers':
        customers = [uid for uid in user_data_store.keys() if uid != ADMIN_CHAT_ID]
        await query.edit_message_text(
            f"👥 *Customers List*\n\n"
            f"Total Customers: {len(customers)}\n"
            f"Active Users: {len(user_data_store)}\n\n"
            "📌 Use /start for main menu"
        )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Log errors"""
    logger.error(f"Update {update} caused error {context.error}")

def main():
    """Start the bot"""
    application = Application.builder().token(BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("broadcast", broadcast_command))
    application.add_handler(CallbackQueryHandler(callback_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_error_handler(error_handler)
    
    print("🤖 DeepSeek Bot is starting...")
    print(f"🔑 Admin ID: {ADMIN_CHAT_ID}")
    print("✅ Bot is ready!")
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
