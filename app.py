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

CUSTOMER_LEADS = set()
ai_client = genai.Client(api_key=GEMINI_API_KEY)

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

    ROLES & BEHAVIOR:
    1. FOR CUSTOMERS:
       - Talk in respectful, polite Hindi/Hinglish (Sir/Ma'am).
       - Understand what is damaged or required.
       - Politely collect: Name, Mobile Number, Address/Location, and Preferred Visit Time.
       - Share the correct department technician/senior number.
       - Once complete details (Name, Phone, Address, Time, Issue) are provided, append strictly this hidden tag at the END of response:
         <!--LEAD_JSON: {{"name": "...", "phone": "...", "address": "...", "time": "...", "issue": "..."}}-->

    2. FOR EMPLOYEES / TECHNICIANS:
       - If a technician gives a task or site update (e.g. "Kamothe site complete, payment ₹1500 done"), acknowledge politely and append:
         <!--STAFF_UPDATE: {{"staff_msg": "..."}}-->
    """

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id == ADMIN_CHAT_ID:
        await update.message.reply_text(
            "👑 **Namaste Satish Ji (AI Admin Desk Active)**\n\n"
            "Gemini AI active hai aur teeno roles handle karega:\n"
            "1. **Customer:** Inquiries & Auto-Leads\n"
            "2. **Employee:** Work & payment updates\n"
            "3. **Admin/Broadcast:** `/broadcast <message>` se sabhi customers ko offer bhejein.",
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
            "• Intercom & Biometric Attendance Machine\n\n"
            "👉 *Aap bataiye aapki kya problem ya requirement hai?*"
        )
        await update.message.reply_text(welcome_text, parse_mode='Markdown')

# Role 1: Admin Broadcast Feature
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
            await context.bot.send_message(chat_id=uid, text=f"📢 **Special Offer - SS Enterprises**\n\n{msg}", parse_mode='Markdown')
            count += 1
        except Exception:
            pass
    await update.message.reply_text(f"✅ Broadcast {count} customers ko successfully bhej diya gaya.")

# Core AI Message Handler
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_text = update.message.text
    CUSTOMER_LEADS.add(user_id)

    try:
        response = ai_client.models.generate_content(
            model="gemini-1.5-flash",
            contents=user_text,
            config=types.GenerateContentConfig(
                system_instruction=get_system_prompt(),
                temperature=0.7
            )
        )
        bot_reply = response.text

        # Role 2: Customer Lead Extraction & Instant Admin Alert
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
                print(f"Lead JSON Parse Error: {e}")

        # Role 3: Employee/Technician Work Report Alert
        elif "<!--STAFF_UPDATE:" in bot_reply:
            parts = bot_reply.split("<!--STAFF_UPDATE:")
            clean_reply = parts[0].strip()
            staff_str = parts[1].split("-->")[0].strip()
            await update.message.reply_text(clean_reply)
            await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=f"👷 **STAFF WORK UPDATE:**\n{staff_str}")
        else:
            await update.message.reply_text(bot_reply, parse_mode='Markdown')

    except Exception as e:
        print(f"Gemini API Call Error: {e}")
        await update.message.reply_text(
            "Namaste sir, aapki request note kar li gayi hai. Hamare senior technician jaldi hi aapse direct baat karenge.\n"
            f"Emergency Helpline: `{BUSINESS_CONTEXT['technicians']['boss_helpline']}`",
            parse_mode='Markdown'
        )

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("broadcast", broadcast_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Gemini AI SS Enterprises Bot is Active & Running...")
    app.run_polling()

if __name__ == '__main__':
    main()
    
