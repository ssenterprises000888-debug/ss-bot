import os
import re
import logging
from datetime import datetime
from typing import Dict, Any, List
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import aiohttp
from dotenv import load_dotenv

load_dotenv()

# Configurations
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', 'AQ.Ab8RN6KIolxssfKWaHmstwr2peaas0sFmbThJdwfkJc9Xwp1JA').strip().strip('"').strip("'")
ADMIN_SECRET_KEY = os.getenv('ADMIN_SECRET_KEY', 'admin123')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SS_WebApp")

app = FastAPI(title="SS Enterprises Assistant")
templates = Jinja2Templates(directory="templates")

# Lead Storage (In-Memory Database)
leads_db: List[Dict[str, Any]] = []

SYSTEM_PROMPT = """You are Deepak, an intelligent and polite assistant at SS Enterprises - a professional service shop providing:
1. CCTV Camera Setup & Repair
2. Electrical Works
3. Computer & Laptop Repair
4. Intercom System Services

Your objective:
- Speak in natural, friendly Hinglish (Hindi + English).
- Collect the customer's: Name, 10-digit Phone Number, Address/Location, and Preferred Time.
- Ask one clear question at a time.
- Keep responses short, concise, and helpful."""

class ChatRequest(BaseModel):
    session_id: str
    message: str
    history: List[Dict[str, str]] = []
    lead_data: Dict[str, str] = {}

def extract_lead_info(text: str, current_data: Dict[str, str]) -> Dict[str, str]:
    data = current_data.copy()
    phone_match = re.search(r'\b[6-9]\d{9}\b', text)
    if phone_match:
        data['phone'] = phone_match.group()
    
    clean_text = text.strip()
    if 'naam' in clean_text.lower() or 'name' in clean_text.lower():
        extracted_name = re.sub(r'(?i)(mera\s+naam\s+is?|mera\s+nam\s+hai|my\s+name\s+is|naam|nam)', '', clean_text).strip()
        if extracted_name and len(extracted_name.split()) <= 4:
            data['name'] = extracted_name
    elif 'name' not in data and len(clean_text.split()) <= 2 and not any(char.isdigit() for char in clean_text):
        if not any(k in clean_text.lower() for k in ['hi', 'hello', 'cctv', 'kaam', 'kam', 'repair', 'help']):
            data['name'] = clean_text

    if any(k in clean_text.lower() for k in ['colony', 'gali', 'road', 'chowk', 'chawk', 'ward', 'nagar', 'siwan', 'bihar', 'house', 'near', 'address']):
        data['address'] = clean_text
    
    if any(k in clean_text.lower() for k in ['baje', 'am', 'pm', 'kal', 'aaj', 'morning', 'evening', 'time', 'dopahar']):
        data['time'] = clean_text

    return data

async def call_gemini(message: str, history: List[Dict[str, str]], lead_data: Dict[str, str]) -> str:
    if GEMINI_API_KEY and GEMINI_API_KEY.startswith("AIza"):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
        headers = {"Content-Type": "application/json"}
        
        hist_text = "\n".join([f"{h['role']}: {h['text']}" for h in history[-6:]])
        prompt = f"{SYSTEM_PROMPT}\n\nCurrent Captured Data: {lead_data}\n\nRecent History:\n{hist_text}\nCustomer: {message}\nDeepak:"
        
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload, timeout=8) as resp:
                    if resp.status == 200:
                        res_json = await resp.json()
                        return res_json['candidates'][0]['content']['parts'][0]['text'].strip()
        except Exception as e:
            logger.error(f"Gemini API exception: {e}")

    # Robust Fallback Logic
    if 'name' not in lead_data:
        return "नमस्ते! मैं दीपक, SS Enterprises से। हम CCTV, Electrical, Computer Repair और Intercom सर्विस देते हैं। आपका शुभ नाम क्या है?"
    elif 'phone' not in lead_data:
        return f"धन्यवाद {lead_data['name']} जी! कृपया अपना 10 अंकों का मोबाइल नंबर बताएं ताकि हमारे टेक्नीशियन आपसे बात कर सकें।"
    elif 'address' not in lead_data:
        return "कृपया अपना पता (Location / Address) शेयर करें जहां काम करवाना है।"
    elif 'time' not in lead_data:
        return "काम के लिए आपको किस समय या दिन सुविधा रहेगी?"
    else:
        return "आपकी बुकिंग रिक्वेस्ट दर्ज हो गई है! हमारे सीनियर टेक्नीशियन जल्द ही आपसे संपर्क करेंगे।"

# Routes
@app.get("/", response_class=HTMLResponse)
async def chat_ui(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/api/chat")
async def handle_chat(req: ChatRequest):
    updated_lead = extract_lead_info(req.message, req.lead_data)
    ai_reply = await call_gemini(req.message, req.history, updated_lead)
    
    # Check if complete lead is formed
    required = ['name', 'phone', 'address', 'time']
    is_completed = all(k in updated_lead for k in required)
    
    if is_completed and req.lead_data.get('_saved') != 'yes':
        updated_lead['_saved'] = 'yes'
        updated_lead['timestamp'] = datetime.now().strftime('%d-%m-%Y %I:%M %p')
        leads_db.append(updated_lead)
    
    return JSONResponse({
        "reply": ai_reply,
        "lead_data": updated_lead,
        "is_completed": is_completed
    })

@app.get("/admin/leads")
async def view_leads(key: str = ""):
    if key != ADMIN_SECRET_KEY:
        return JSONResponse({"error": "Unauthorized access"}, status_code=401)
    return JSONResponse({"total_leads": len(leads_db), "leads": leads_db[::-1]})
    
