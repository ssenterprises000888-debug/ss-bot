import json
import logging
import aiohttp
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

# ==================== CONFIGURATION (SS ENTERPRISES) ====================
BOT_TOKEN = "8768428239:AAHpNjXHdvtz8vybglg2R9tSvv0uiyQ_tNA"
ADMIN_CHAT_ID = 1443007174  # Satish Prasad Ji (Admin Telegram ID)

# Verified Google Gemini API Key
GEMINI_API_KEY = "AQ.Ab8RN6JJr7_sEO6g9V11fkUgBCmm12MWuGZVkU74vcQy6WPY8g"

# Business Information & Contacts
BUSINESS_CONTEXT = {
    "shop_name": "SS Enterprises",
    "address": "Shop no 35, Sai Prasad enclave CHS, sector 07, Kamothe, Navi Mumbai",
    "maps_link": "https://g.co/kgs/dMDiCvT",
    "timing": "10:00 AM - 10:00 PM (Everyday)",
    "upi_id": "ssenterprises@upi",
    "technicians": {
        "cctv": "+91 8424959631 / 9372000280",
        "electrical": "+91 8424959631 / 9372000280",
        "computer_laptop_printer": "+91 8591919083",
        "intercom_biometric": "+91 8424959631 / 8591919083",
        "boss_helpline": "+91 8424959631"
    }
}

# In-Memory Customer History and Leads
CHAT_HISTORIES = {}
CUSTOMER_LEADS = set()

def get_system_prompt():
    return f"""
    You are the Senior AI Business Assistant for 'SS Enterprises' managed by Satish Prasad.
    
    Services Offered:
    1. Electrical & Inverter Solutions (Fan, Wiring, Inverter, Switchboard, Motor)
    2. CCTV Camera Setup & Repair (Hikvision, CP Plus, Dahua, IP Camera, DVR/NVR)
    3. Computer, Laptop & Printer Repair/Sales (Windows, Formatting, Hardware, Cartridge)
    4. Intercom & Biometric Attendance Systems

    Shop Details:
    - Address: {BUSINESS_CONTEXT['address']}
    - Timing: {BUSINESS_CONTEXT['timing']}
    - Technician Contacts: {json.dumps(BUSINESS_CONTEXT['technicians'])}

    ROLES & INSTRUCTIONS:
    1. FOR CUSTOMERS:
       - Talk in respectful, natural Hindi/Hinglish (Sir/Ma'am).
       - When a customer mentions a problem (e.g. camera lagwana hai, fan kharab hai), acknowledge politely.
       - Politely ask for missing details: Name, Mobile Number, Address/Location, and Preferred Visit Time (ask step-by-step or together).
       - When you give the technician number, or once customer provides full details (Name, Phone, Address, Time, Issue), append strictly this hidden tag at the VERY END:
         <!--LEAD_JSON: {{"name": "...", "phone": "...", "address": "...", "time": "...", "issue": "..."}}-->

    2. FOR EMPLOYEES / TECHNICIANS:
       - If a technician gives a task or site update (e.g. "Kamothe site complete, payment 1500"), acknowledge and append:
         <!--STAFF_UPDATE: {{"staff_msg": "..."}}-->
    """

# Direct Call to Google Gemini REST API
async def call_gemini_api(user_id: int, user_text: str) -> str:
    if user_id not in CHAT_HISTORIES:
        CHAT_HISTORIES[user_id] = []
    
    CHAT_HISTORIES[user_id].append({"role": "user", "parts": [{"text": user_text}]})
    
    # Keep last 10 messages for context memory
    if len(CHAT_HISTORIES[user_id]) > 10:
        CHAT_HISTORIES[user_id] = CHAT_HISTORIES[user_id][-10:]

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    
    payload = {
        "system_instruction": {
            "parts": [{"text": get_system_prompt()}]
        },
        "contents": CHAT_HISTORIES[user_id],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 800
        }
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as resp:
            if resp.status == 200:
                data = await resp.json()
                bot_reply = data['candidates'][0]['content']['parts'][0]['text']
                CHAT_HISTORIES[user_id].append({"role": "model", "parts": [{"text": bot_reply}]})
                return bot_reply
            else:
                error_body = await resp.text()
                print(f"Gemini API Error [{resp.status}]: {error_body}")
                return "Namaste sir, aapki request note ho gayi hai. Kripya apna Naam, Phone number aur Address share karein taaki hum technician bhej sakein."

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    CHAT_HISTORIES[user_id] = []  # Reset chat history
    
    if user_id == ADMIN_CHAT_ID:
        await update.message.reply_text(
            "👑 **Namaste Satish Ji (AI Admin Desk Active)**\n\n"
            "Gemini AI active hai aur teeno roles handle karega:\n"
            "1. **Customer:** Inquiries & Lead capture\n"
            "2. **Employee:** Work updates\n"
            "3. **Broadcast:** `/broadcast <message>`",
            parse_mode='Markdown'
        )
    else:
        CUSTOMER_LEADS.add(user_id)
        welcome_text = (
            f"Namaste! Welcome to **{BUSINESS_CONTEXT['shop_name']}** 🙏\n\n"
            "🛠️ **Hamari Services:**\n"
            "• CCTV Camera Setup & Repair\n"
            "• Electrical & Inverter Solutions\n"
            "• Computer, Laptop & Printer Repair/Sales\n"
            "• Intercom & Biometric Attendance\n\n"
            "👉 *Aap bataiye aapki kya requirement ya problem hai?*"
        )
        await update.message.reply_text(welcome_text, parse_mode='Markdown')

async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_CHAT_ID:
        return
    msg = " ".join(context.args)
    if not msg:
        await update.message.reply_text("Usage: `/broadcast Aapka Message`", parse_mode='Markdown')
        return
    
    count = 0
    for uid in CUSTOMER_LEADS:
        try:
            await context.bot.send_message(chat_id=uid, text=f"📢 **Special Update - SS Enterprises**\n\n{msg}", parse_mode='Markdown')
            count += 1
        except Exception:
            pass
    await update.message.reply_text(f"✅ Broadcast {count} customers ko successfully bhej diya gaya.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_text = update.message.text
    CUSTOMER_LEADS.add(user_id)

    bot_reply = await call_gemini_api(user_id, user_text)

    # 1. Check Lead JSON for Admin Alert Ticket
    if "<!--LEAD_JSON:" in bot_reply:
        parts = bot_reply.split("<!--LEAD_JSON:")
        clean_reply = parts[0].strip()
        lead_json_str = parts[1].split("-->")[0].strip()
        
        await update.message.reply_text(clean_reply, parse_mode='Markdown')
        try:
            lead_data = json.loads(lead_json_str)
            alert_text = (
                "🔔 **AI GENERATED CUSTOMER LEAD**\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"👤 **Name:** {lead_data.get('name', 'N/A')}\n"
                f"📞 **Phone:** {lead_data.get('phone', 'N/A')}\n"
                f"📍 **Address:** {lead_data.get('address', 'N/A')}\n"
                f"⏰ **Time:** {lead_data.get('time', 'N/A')}\n"
                f"📝 **Requirement:** {lead_data.get('issue', 'N/A')}\n"
                "━━━━━━━━━━━━━━━━━━━━"
            )
            await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=alert_text, parse_mode='Markdown')
        except Exception as e:
            print(f"JSON Parse Error: {e}")

    # 2. Check Staff Work Update
    elif "<!--STAFF_UPDATE:" in bot_reply:
        parts = bot_reply.split("<!--STAFF_UPDATE:")
        clean_reply = parts[0].strip()
        staff_str = parts[1].split("-->")[0].strip()
        await update.message.reply_text(clean_reply)
        await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=f"👷 **STAFF WORK UPDATE:**\n{staff_str}")
    else:
        await update.message.reply_text(bot_reply, parse_mode='Markdown')

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("broadcast", broadcast_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Gemini AI SS Enterprises Bot Active & Running...")
    app.run_polling()

if __name__ == '__main__':
    main()
    
