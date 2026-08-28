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

# Google Gemini API Key
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

USER_STATES = {}
CUSTOMER_LEADS = set()

def get_system_prompt():
    return f"""
    You are the Senior AI Business Assistant for 'SS Enterprises' managed by Satish Prasad.
    
    Services:
    1. Electrical & Inverter Solutions
    2. CCTV Camera Setup & Repair
    3. Computer, Laptop & Printer Repair/Sales
    4. Intercom & Biometric Attendance

    Location: {BUSINESS_CONTEXT['address']}
    Timing: {BUSINESS_CONTEXT['timing']}
    Contacts: {json.dumps(BUSINESS_CONTEXT['technicians'])}

    INSTRUCTIONS:
    - Talk in respectful Hindi/Hinglish (Sir/Ma'am).
    - If customer tells any problem, acknowledge and politely ask for Name, Phone Number, Address, and Preferred Time.
    - When details are provided, share technician number and strictly end reply with:
      <!--LEAD_JSON: {{"name": "...", "phone": "...", "address": "...", "time": "...", "issue": "..."}}-->
    """

# Gemini API Caller (With Headers for AQ. Keys)
async def call_gemini(user_id: int, user_text: str) -> str:
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": GEMINI_API_KEY
    }
    payload = {
        "system_instruction": {"parts": [{"text": get_system_prompt()}]},
        "contents": [{"role": "user", "parts": [{"text": user_text}]}],
        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 600}
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload, timeout=8) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data['candidates'][0]['content']['parts'][0]['text']
    except Exception as e:
        print(f"Gemini API Exception: {e}")
    return ""

# Smart Fallback Engine (Runs if AI is offline)
def smart_fallback(user_id: int, text: str):
    if user_id not in USER_STATES:
        USER_STATES[user_id] = {"step": 1, "data": {}}
    
    st = USER_STATES[user_id]
    step = st["step"]
    txt = text.strip()

    if step == 1:
        st["data"]["issue"] = txt
        st["step"] = 2
        return "Theek hai sir. Kripya apna **Pura Naam (Name)** batayein:"
    elif step == 2:
        st["data"]["name"] = txt
        st["step"] = 3
        return "Apna **Mobile Number** share karein:"
    elif step == 3:
        st["data"]["phone"] = txt
        st["step"] = 4
        return "Apna **Pura Pata (Address/Location)** batayein:"
    elif step == 4:
        st["data"]["address"] = txt
        st["step"] = 5
        return "Technician visit ke liye **Subhidhajanak Samay (Date & Time)** batayein:"
    elif step == 5:
        st["data"]["time"] = txt
        st["step"] = 1
        d = st["data"]
        
        # Dept Routing
        issue_l = d.get("issue", "").lower()
        if any(w in issue_l for w in ["cctv", "camera", "dvr", "nvr"]):
            num = BUSINESS_CONTEXT["technicians"]["cctv"]
        elif any(w in issue_l for w in ["laptop", "computer", "pc", "printer"]):
            num = BUSINESS_CONTEXT["technicians"]["computer_laptop_printer"]
        else:
            num = BUSINESS_CONTEXT["technicians"]["electrical"]

        lead_json = json.dumps(d)
        reply = (
            "✅ **Aapki complaint / booking register ho gayi hai!**\n\n"
            f"📞 **Senior Technician Contact:** `{num}`\n"
            "Humne aapki request forward kar di hai.\n\n"
            f"<!--LEAD_JSON: {lead_json}-->"
        )
        return reply

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    USER_STATES[user_id] = {"step": 1, "data": {}}
    CUSTOMER_LEADS.add(user_id)
    
    if user_id == ADMIN_CHAT_ID:
        await update.message.reply_text(
            "👑 **Namaste Satish Ji (Admin Active)**\n\n"
            "AI System 100% live hai.\n"
            "• `/broadcast <message>` - Sabhi customers ko offer bhejne ke liye.",
            parse_mode='Markdown'
        )
    else:
        welcome_text = (
            f"Namaste! Welcome to **{BUSINESS_CONTEXT['shop_name']}** 🙏\n\n"
            "🛠️ **Hamari Services:**\n"
            "• CCTV Camera Setup & Repair\n"
            "• Electrical & Inverter Solutions\n"
            "• Computer, Laptop & Printer Repair/Sales\n"
            "• Intercom & Biometric Attendance\n\n"
            "👉 *Aap bataiye aapki kya problem ya requirement hai?*"
        )
        await update.message.reply_text(welcome_text, parse_mode='Markdown')

async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_CHAT_ID:
        return
    msg = " ".join(context.args)
    if not msg:
        await update.message.reply_text("Usage: `/broadcast Aapka Message`", parse_mode='Markdown')
        return
    for uid in CUSTOMER_LEADS:
        try:
            await context.bot.send_message(chat_id=uid, text=f"📢 **SS Enterprises Update:**\n\n{msg}", parse_mode='Markdown')
        except:
            pass
    await update.message.reply_text("✅ Broadcast bhej diya gaya.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_text = update.message.text
    CUSTOMER_LEADS.add(user_id)

    # 1. Try Gemini AI
    bot_reply = await call_gemini(user_id, user_text)

    # 2. If AI didn't respond, run Smart Fallback
    if not bot_reply:
        bot_reply = smart_fallback(user_id, user_text)

    # 3. Process Lead JSON
    if "<!--LEAD_JSON:" in bot_reply:
        parts = bot_reply.split("<!--LEAD_JSON:")
        clean_reply = parts[0].strip()
        lead_json_str = parts[1].split("-->")[0].strip()
        await update.message.reply_text(clean_reply, parse_mode='Markdown')

        try:
            lead_data = json.loads(lead_json_str)
            alert = (
                "🔔 **NEW CUSTOMER LEAD / COMPLAINT**\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"👤 **Name:** {lead_data.get('name')}\n"
                f"📞 **Phone:** {lead_data.get('phone')}\n"
                f"📍 **Address:** {lead_data.get('address')}\n"
                f"⏰ **Time:** {lead_data.get('time')}\n"
                f"📝 **Problem:** {lead_data.get('issue')}\n"
                "━━━━━━━━━━━━━━━━━━━━"
            )
            await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=alert, parse_mode='Markdown')
        except Exception as e:
            print(f"JSON Alert error: {e}")
    else:
        await update.message.reply_text(bot_reply, parse_mode='Markdown')

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("broadcast", broadcast_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("SS Enterprises Bot Running...")
    app.run_polling()

if __name__ == '__main__':
    main()
    
