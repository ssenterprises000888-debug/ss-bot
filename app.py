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

# Satish Prasad Ji ki verified Admin ID
ADMIN_CHAT_ID = 1443007174  

# Department-wise Senior / Technician Contacts:
CONTACTS = {
    "cctv": {
        "title": "📹 CCTV Senior Technician",
        "name": "CCTV Dept",
        "phone": "+91 8424959631/9372000280"  # <-- CCTV technician ka number yahan badlein
    },
    "electrical": {
        "title": "⚡ Electrical & Inverter Senior Technician",
        "name": "Electrical Dept",
        "phone": "+91 8424959631/9372000280"  # <-- Electrical technician ka number yahan badlein
    },
    "computer": {
        "title": "💻 Computer, Laptop & Printer Senior Support",
        "name": "IT Dept",
        "phone": "+91 8591919083"  # <-- Computer/Laptop senior ka number yahan badlein
    },
    "intercom": {
        "title": "📞 Intercom & Biometric Senior Tech",
        "name": "Security Systems Dept",
        "phone": "+91 8424959631/8591919083"  # <-- Biometric senior ka number yahan badlein
    },
    "owner": {
        "title": "👔 Senior Management / Satish Ji Desk",
        "name": "SS Enterprises Management",
        "phone": "+91 8424959631"  # <-- Owner/Main Helpline number yahan badlein
    }
}

SHOP_INFO = {
    "address": "SS Enterprises, Shop no 35 Sai Prasad enclave CHS sector 07 Kamothe",
    "maps_link": "https://g.co/kgs/dWDiCwT",
    "timing": "10:00 AM - 10:00 PM (Everyday)",
    "upi_id": "ssenterprises@upi"
}
# ========================================================================

ASK_PROBLEM, ASK_NAME, ASK_PHONE, ASK_ADDRESS, ASK_TIME = range(5)

async def start_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "Namaste! Thank you for contacting **SS Enterprises**.\n"
        "Hum aapki poori sahayta karenge.\n\n"
        "🛠️ **Hamari Services:**\n"
        "• Electrical & Inverter Solutions\n"
        "• CCTV Camera Setup & Repair\n"
        "• Computer, Laptop & Printer Repair/Sales\n"
        "• Intercom & Biometric Attendance Machine\n\n"
        "*(All types & all brands sales & service available)*\n\n"
        "👉 **Aap bataiye aapki kya problem / requirement hai?**\n"
        "*(Jaise: CCTV lagana hai / Laptop issue / Shop location / Payment / Boss se baat karni hai)*"
    )
    await update.message.reply_text(welcome_text, parse_mode='Markdown')
    return ASK_PROBLEM

async def handle_problem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_msg = update.message.text
    context.user_data['problem'] = user_msg
    msg_lower = user_msg.lower()

    # Shop Location Query
    if any(k in msg_lower for k in ['address', 'location', 'dukan', 'shop', 'kaha hai', 'pata']):
        info_text = (
            f"📍 **Shop Address:** {SHOP_INFO['address']}\n"
            f"⏰ **Timing:** {SHOP_INFO['timing']}\n"
            f"🗺️ **Google Maps:** {SHOP_INFO['maps_link']}\n\n"
            f"Service booking ke liye aap problem likh kar bhej sakte hain."
        )
        await update.message.reply_text(info_text, parse_mode='Markdown')
        return ASK_PROBLEM

    # Payment / QR Query
    if any(k in msg_lower for k in ['payment', 'bill', 'qr', 'upi', 'paisa']):
        pay_text = (
            f"💳 **Payment / Billing Details:**\n"
            f"• UPI ID: `{SHOP_INFO['upi_id']}`\n"
            f"• Direct Desk: `{CONTACTS['owner']['phone']}`\n\n"
            f"Payment screenshot isi chat mein bhej sakte hain."
        )
        await update.message.reply_text(pay_text, parse_mode='Markdown')
        return ASK_PROBLEM

    await update.message.reply_text("Theek hai sir. Kripya apna **Pura Naam (Name)** batayein:")
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
    data = context.user_data
    problem_lower = data['problem'].lower()

    assigned_contacts = []

    # CCTV routing
    if any(word in problem_lower for word in ['cctv', 'camera', 'dvr', 'nvr', 'security', 'surveillance']):
        assigned_contacts.append(CONTACTS['cctv'])
    
    # Electrical routing
    if any(word in problem_lower for word in ['fan', 'light', 'wire', 'electrical', 'inverter', 'switch', 'board', 'motor']):
        assigned_contacts.append(CONTACTS['electrical'])
    
    # Computer / Laptop / Printer routing
    if any(word in problem_lower for word in ['laptop', 'computer', 'pc', 'printer', 'windows', 'keyboard', 'screen', 'format', 'ram', 'ssd']):
        assigned_contacts.append(CONTACTS['computer'])

    # Intercom / Biometric routing
    if any(word in problem_lower for word in ['intercom', 'biometric', 'attendance', 'epabx']):
        assigned_contacts.append(CONTACTS['intercom'])

    # Boss / Senior Management request routing
    if any(word in problem_lower for word in ['boss', 'owner', 'manager', 'senior', 'complaint', 'sikayat', 'satish']):
        assigned_contacts.append(CONTACTS['owner'])

    # Fallback to Owner Desk if no department matches
    if not assigned_contacts:
        assigned_contacts.append(CONTACTS['owner'])

    contact_info_text = ""
    for contact in assigned_contacts:
        contact_info_text += f"{contact['title']}: `{contact['phone']}`\n"

    customer_reply = (
        "✅ **Aapki complaint / request register ho gayi hai!**\n\n"
        f"Aapki requirement ke anusar contact details:\n{contact_info_text}\n"
        "Sir, aap in numbers par direct call kar sakte hain. Hamari team ko aapki request forward kar di gayi hai.\n\n"
        "Dhanyawad! **SS Enterprises**"
    )
    await update.message.reply_text(customer_reply, parse_mode='Markdown')

    # Instant Notification to Satish Prasad Ji (Admin)
    admin_alert = (
        "🔔 **NEW CUSTOMER CALL LOG / COMPLAINT**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 **Customer Name:** {data.get('name')}\n"
        f"📞 **Phone Number:** {data.get('phone')}\n"
        f"📍 **Address:** {data.get('address')}\n"
        f"⏰ **Preferred Time:** {data.get('time')}\n"
        f"📝 **Problem/Requirement:** {data.get('problem')}\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )
    try:
        await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=admin_alert, parse_mode='Markdown')
    except Exception as e:
        print(f"Admin alert delivery failed: {e}")

    return ConversationHandler.END

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start_conversation),
            MessageHandler(filters.TEXT & ~filters.COMMAND, start_conversation)
        ],
        states={
            ASK_PROBLEM: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_problem)],
            ASK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_name)],
            ASK_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_phone)],
            ASK_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_address)],
            ASK_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, finish_and_assign)],
        },
        fallbacks=[CommandHandler("start", start_conversation)]
    )

    app.add_handler(conv_handler)
    print("Bot is active and running...")
    app.run_polling()

if __name__ == '__main__':
    main()
