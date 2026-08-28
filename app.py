import json
import logging
import aiohttp
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters
)

# ==================== CONFIGURATION (SS ENTERPRISES) ====================
BOT_TOKEN = "8768428239:AAHpNjXHdvtz8vybglg2R9tSvv0uiyQ_tNA"
ADMIN_CHAT_ID = 1443007174  # Satish Prasad Ji (Admin Telegram ID)
GEMINI_API_KEY = "AQ.Ab8RN6JJr7_sEO6g9V11fkUgBCmm12MWuGZVkU74vcQy6WPY8g"

# Business Information & Contacts
BUSINESS_CONTEXT = {
    "shop_name": "SS Enterprises",
    "address": "Shop no 35, Sai Prasad enclave CHS, sector 07, Kamothe, Navi Mumbai",
    "maps_link": "https://g.co/kgs/dMDiCvT",
    "timing": "10:00 AM - 10:00 PM (Everyday)",
    "upi_id": "ssenterprises@upi",
    "technicians": {
        "cctv": {
            "title": "📹 CCTV Senior Technician",
            "phone": "+91 8424959631 / 9372000280"
        },
        "electrical": {
            "title": "⚡ Electrical & Inverter Senior Technician",
            "phone": "+91 8424959631 / 9372000280"
        },
        "computer": {
            "title": "💻 Computer, Laptop & Printer Senior Support",
            "phone": "+91 8591919083"
        },
        "intercom": {
            "title": "📞 Intercom & Biometric Senior Tech",
            "phone": "+91 8424959631 / 8591919083"
        },
        "owner": {
            "title": "👔 Senior Management / Satish Ji Desk",
            "phone": "+91 8424959631"
        }
    }
}

CUSTOMER_LEADS = set()

# Conversation Steps
ASK_PROBLEM, ASK_NAME, ASK_PHONE, ASK_ADDRESS, ASK_TIME = range(5)

# Google Gemini Native Engine
async def get_ai_solution(query: str) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": [{"text": f"User asked regarding repair/service: '{query}'. Give a very short 1-line polite acknowledgment in Hindi/Hinglish."}]}]
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload, timeout=5) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data['candidates'][0]['content']['parts'][0]['text'].strip()
    except Exception:
        pass
    return "Ji bilkul sir, hum isme aapki poori madad karenge."

# ==================== CONVERSATION FLOW ====================

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    CUSTOMER_LEADS.add(user_id)

    if user_id == ADMIN_CHAT_ID:
        await update.message.reply_text(
            "👑 **Namaste Satish Ji (Admin Panel Active)**\n\n"
            "Bot teeno roles ke sath live hai:\n"
            "1. **Customer:** Automatic lead logging\n"
            "2. **Technician:** Field contact routing\n"
            "3. **Broadcast:** `/broadcast <message>` sabhi ko offer bhejne ke liye.",
            parse_mode='Markdown'
        )
        return ConversationHandler.END

    welcome_text = (
        f"Namaste! Welcome to **{BUSINESS_CONTEXT['shop_name']}** 🙏\n\n"
        "🛠️ **Hamari Services:**\n"
        "• CCTV Camera Setup & Repair\n"
        "• Electrical & Inverter Solutions\n"
        "• Computer, Laptop & Printer Repair/Sales\n"
        "• Intercom & Biometric Attendance\n\n"
        "👉 **Aap bataiye aapki kya problem ya requirement hai?**\n"
        "*(Jaise: CCTV kharab hai / Laptop issue / Shop location / Payment)*"
    )
    await update.message.reply_text(welcome_text, parse_mode='Markdown')
    return ASK_PROBLEM

async def handle_problem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_msg = update.message.text
    context.user_data['problem'] = user_msg
    msg_l = user_msg.lower()

    # Shop Location Query
    if any(k in msg_l for k in ['address', 'location', 'dukan', 'shop', 'kaha hai', 'pata']):
        info = (
            f"📍 **Shop Address:** {BUSINESS_CONTEXT['address']}\n"
            f"⏰ **Timing:** {BUSINESS_CONTEXT['timing']}\n"
            f"🗺️ **Maps:** {BUSINESS_CONTEXT['maps_link']}\n\n"
            f"Service booking ke liye apni requirement likhein."
        )
        await update.message.reply_text(info, parse_mode='Markdown')
        return ASK_PROBLEM

    # Payment Query
    if any(k in msg_l for k in ['payment', 'bill', 'qr', 'upi', 'paisa']):
        pay = (
            f"💳 **Payment Details:**\n"
            f"• UPI ID: `{BUSINESS_CONTEXT['upi_id']}`\n"
            f"• Desk: `{BUSINESS_CONTEXT['technicians']['owner']['phone']}`"
        )
        await update.message.reply_text(pay, parse_mode='Markdown')
        return ASK_PROBLEM

    # AI Acknowledgement + Step 1
    ai_ack = await get_ai_solution(user_msg)
    await update.message.reply_text(f"{ai_ack}\n\nKripya apna **Pura Naam (Name)** batayein:")
    return ASK_NAME

async def handle_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['name'] = update.message.text
    await update.message.reply_text("Apna **Mobile Number** share karein:")
    return ASK_PHONE

async def handle_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['phone'] = update.message.text
    await update.message.reply_text("Apna **Pura Pata (Address/Location)** batayein:")
    return ASK_ADDRESS

async def handle_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['address'] = update.message.text
    await update.message.reply_text("Technician visit ke liye **Subhidhajanak Samay (Preferred Date & Time)** batayein:")
    return ASK_TIME

async def finish_and_assign(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['time'] = update.message.text
    d = context.user_data
    prob = d.get('problem', '').lower()

    # Route to Senior Technician
    if any(w in prob for w in ['cctv', 'camera', 'dvr', 'nvr', 'security']):
        tech = BUSINESS_CONTEXT['technicians']['cctv']
    elif any(w in prob for w in ['laptop', 'computer', 'pc', 'printer', 'windows']):
        tech = BUSINESS_CONTEXT['technicians']['computer']
    elif any(w in prob for w in ['intercom', 'biometric', 'attendance']):
        tech = BUSINESS_CONTEXT['technicians']['intercom']
    elif any(w in prob for w in ['boss', 'owner', 'manager', 'satish']):
        tech = BUSINESS_CONTEXT['technicians']['owner']
    else:
        tech = BUSINESS_CONTEXT['technicians']['electrical']

    customer_msg = (
        "✅ **Aapki complaint register ho gayi hai!**\n\n"
        f"Aapki problem ke hisaab se hamare technician:\n"
        f"👤 **{tech['title']}**: `{tech['phone']}`\n\n"
        "Sir, aap in numbers par direct call kar sakte hain. Humne unhe aapki request forward kar di hai.\n\n"
        "Dhanyawad! **SS Enterprises**"
    )
    await update.message.reply_text(customer_msg, parse_mode='Markdown')

    # Instant Ticket to Satish Ji
    admin_ticket = (
        "🔔 **NEW CUSTOMER CALL LOG / LEAD**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 **Customer Name:** {d.get('name')}\n"
        f"📞 **Phone Number:** {d.get('phone')}\n"
        f"📍 **Address:** {d.get('address')}\n"
        f"⏰ **Preferred Time:** {d.get('time')}\n"
        f"📝 **Problem:** {d.get('problem')}\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )
    try:
        await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=admin_ticket, parse_mode='Markdown')
    except Exception as e:
        print(f"Admin Ticket Error: {e}")

    return ConversationHandler.END

# Broadcast Command
async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_CHAT_ID:
        return
    msg = " ".join(context.args)
    if not msg:
        await update.message.reply_text("Usage: `/broadcast Aapka Offer Message`", parse_mode='Markdown')
        return
    count = 0
    for uid in CUSTOMER_LEADS:
        try:
            await context.bot.send_message(chat_id=uid, text=f"📢 **Special Offer from SS Enterprises**\n\n{msg}", parse_mode='Markdown')
            count += 1
        except Exception:
            pass
    await update.message.reply_text(f"✅ Broadcast {count} logo ko successfully bhej diya gaya.")

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start_cmd),
            MessageHandler(filters.TEXT & ~filters.COMMAND, start_cmd)
        ],
        states={
            ASK_PROBLEM: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_problem)],
            ASK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_name)],
            ASK_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_phone)],
            ASK_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_address)],
            ASK_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, finish_and_assign)],
        },
        fallbacks=[CommandHandler("start", start_cmd)]
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("broadcast", broadcast_cmd))

    print("SS Enterprises 3-Role Bot is Running...")
    app.run_polling()

if __name__ == '__main__':
    main()
