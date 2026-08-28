import json
import logging
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)
from google import genai
from google.genai import types

# ==================== CONFIGURATION (SS ENTERPRISES) ====================
BOT_TOKEN = "8768428239:AAHpNjXHdvtz8vybglg2R9tSvv0uiyQ_tNA"
ADMIN_CHAT_ID = 1443007174  # Satish Prasad Ji (Admin Telegram ID)

# Google AI Studio se copy ki hui poori API Key yahan paste karein:
GEMINI_API_KEY = "PASTE_YOUR_FULL_COPIED_KEY_HERE"

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

CUSTOMER_LEADS = set()
ai_client = genai.Client(api_key=GEMINI_API_KEY)

def get_system_prompt():
    return f"""
    You are the Senior AI Business Assistant for 'SS Enterprises' managed by Satish Prasad.
    
    Services Offered:
    1. Electrical & Inverter Repair/Installation
    2. CCTV Camera Sales, Setup & Service
    3. Computer, Laptop & Printer Repair & Sales
    4. Intercom & Biometric Attendance Systems

    Shop Details:
    - Address: {BUSINESS_CONTEXT['address']}
    - Timing: {BUSINESS_CONTEXT['timing']}
    - Technician Contacts: {json.dumps(BUSINESS_CONTEXT['technicians'])}

    ROLES & INSTRUCTIONS:
    1. FOR CUSTOMERS:
       - Reply in respectful, friendly Hindi/Hinglish (Sir/Ma'am).
       - Solve basic queries or understand what is damaged/needed.
       - Politely collect Name, Mobile Number, Address, and Preferred Time.
       - Provide the relevant technician/senior phone number.
       - Once complete details (Name, Phone, Address, Issue) are known, append strictly this hidden tag at the END of response:
         <!--LEAD_JSON: {{"name": "...", "phone": "...", "address": "...", "time": "...", "issue": "..."}}-->

    2. FOR EMPLOYEES:
       - If a technician gives a job update (e.g., "Kamothe site done, bill 1500"), acknowledge and append:
         <!--STAFF_UPDATE: {{"staff_msg": "..."}}-->
    """

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id == ADMIN_CHAT_ID:
        await update.message.reply_text(
            "👑 **Namaste Satish Ji (Gemini AI Admin Active)**\n\n"
            "AI ab customers ke sath natural baat karega aur details collect karke aapko instant ticket bhejega.\n"
            "• `/broadcast <message>` - Sabhi customers ko offer ya wish bhejne ke liye.",
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
    
    count = 0
    for uid in CUSTOMER_LEADS:
        try:
            await context.bot.send_message(chat_id=uid, text=f"📢 **Special Update - SS Enterprises**\n\n{msg}", parse_mode='Markdown')
            count += 1
        except Exception:
            pass
    await update.message.reply_text(f"✅ Broadcast {count} customers ko bhej diya gaya.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_text = update.message.text
    CUSTOMER_LEADS.add(user_id)

    try:
        response = ai_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=user_text,
            config=types.GenerateContentConfig(
                system_instruction=get_system_prompt(),
                temperature=0.6
            )
        )
        bot_reply = response.text

        # Hidden Lead JSON Parsing
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
                    f"👤 **Name:** {lead_data.get('name')}\n"
                    f"📞 **Phone:** {lead_data.get('phone')}\n"
                    f"📍 **Address:** {lead_data.get('address')}\n"
                    f"⏰ **Time:** {lead_data.get('time')}\n"
                    f"📝 **Requirement:** {lead_data.get('issue')}\n"
                    "━━━━━━━━━━━━━━━━━━━━"
                )
                await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=alert_text, parse_mode='Markdown')
            except Exception as e:
                print(f"Lead JSON Error: {e}")

        # Hidden Staff Update Parsing
        elif "<!--STAFF_UPDATE:" in bot_reply:
            parts = bot_reply.split("<!--STAFF_UPDATE:")
            clean_reply = parts[0].strip()
            staff_str = parts[1].split("-->")[0].strip()
            await update.message.reply_text(clean_reply)
            await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=f"👷 **STAFF WORK UPDATE:**\n{staff_str}")
        else:
            await update.message.reply_text(bot_reply, parse_mode='Markdown')

    except Exception as e:
        print(f"Gemini API Error: {e}")
        await update.message.reply_text("Namaste sir, aapki request note ho gayi hai. Hamari team jaldi aapse sampark karegi.")

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("broadcast", broadcast_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Google Gemini AI SS Enterprises Bot Running...")
    app.run_polling()

if __name__ == '__main__':
    main()
    
