from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters
)

BOT_TOKEN = "8768428239:AAHpNjXHdvtz8vybglg2R9tSvv0uiyQ_tNA"
ADMIN_CHAT_ID = 123456789  # <--- Yahan apni Chat ID daalein

TECH_CONTACTS = {
    "cctv": {"name": "CCTV Technician", "phone": "+91 9876543210"},
    "electrical": {"name": "Electrical Technician", "phone": "+91 9876543211"},
    "computer": {"name": "Computer/IT Technician", "phone": "+91 9876543212"},
    "general": {"name": "SS Enterprises Support", "phone": "+91 9876543200"}
}

ASK_PROBLEM, ASK_NAME, ASK_PHONE, ASK_ADDRESS, ASK_TIME = range(5)

async def start_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "Namaste! Thank you for choosing **SS Enterprises**.\n"
        "Abhi hum log available nahi hain, par hum aapki puri sahayta karenge.\n\n"
        "🛠️ **Hamari Services:**\n"
        "• Electrical\n"
        "• CCTV\n"
        "• Computer\n"
        "• Laptop\n"
        "• Printer\n"
        "• Intercom\n"
        "• Inverter\n"
        "• Biometric\n\n"
        "*(All types & all brands sales & service available)*\n\n"
        "👉 **Aap bataiye aapki kya problem hai?**"
    )
    await update.message.reply_text(welcome_text, parse_mode='Markdown')
    return ASK_PROBLEM

async def handle_problem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['problem'] = update.message.text
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
    
    assigned_techs = []
    if any(word in problem_lower for word in ['cctv', 'camera', 'dvr', 'nvr', 'security']):
        assigned_techs.append(TECH_CONTACTS['cctv'])
    if any(word in problem_lower for word in ['fan', 'light', 'wire', 'electrical', 'inverter', 'switch', 'board']):
        assigned_techs.append(TECH_CONTACTS['electrical'])
    if any(word in problem_lower for word in ['laptop', 'computer', 'pc', 'printer', 'biometric', 'windows']):
        assigned_techs.append(TECH_CONTACTS['computer'])
        
    if not assigned_techs:
        assigned_techs.append(TECH_CONTACTS['general'])

    tech_info = ""
    for tech in assigned_techs:
        tech_info += f"👤 **{tech['name']}**: `{tech['phone']}`\n"
        
    customer_reply = (
        "✅ **Aapki complaint register ho gayi hai!**\n\n"
        f"Aapki problem ke hisaab se hamare technician:\n{tech_info}\n"
        "Sir, aap in numbers par direct call kar sakte hain. Humne unhe aapki request forward kar di hai.\n\n"
        "Dhanyawad! **SS Enterprises**"
    )
    await update.message.reply_text(customer_reply, parse_mode='Markdown')

    admin_alert = (
        "🔔 **NEW SERVICE REQUEST / LEAD**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 **Customer:** {data['name']}\n"
        f"📞 **Phone:** {data['phone']}\n"
        f"📍 **Address:** {data['address']}\n"
        f"⏰ **Time:** {data['time']}\n"
        f"📝 **Problem:** {data['problem']}\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )
    try:
        await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=admin_alert, parse_mode='Markdown')
    except Exception as e:
        print(f"Admin alert error: {e}")

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
  
