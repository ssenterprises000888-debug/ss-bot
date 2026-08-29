import os
import re
import logging
from datetime import datetime
from typing import Dict, Any, List
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
import uvicorn
import aiohttp
from dotenv import load_dotenv

load_dotenv()

# Configurations
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '').strip().strip('"').strip("'")
ADMIN_SECRET_KEY = os.getenv('ADMIN_SECRET_KEY', 'admin123')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SS_WebApp")

app = FastAPI(title="SS Enterprises Assistant")

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

    # Fallback response
    if 'name' not in lead_data:
        return "नमस्ते! मैं दीपक, SS Enterprises से बात कर रहा हूँ। हम CCTV, Electrical, Computer Repair और Intercom सर्विस देते हैं। आपका शुभ नाम क्या है?"
    elif 'phone' not in lead_data:
        return f"धन्यवाद {lead_data['name']} जी! कृपया अपना 10 अंकों का मोबाइल नंबर बताएं ताकि हमारे टेक्नीशियन आपसे संपर्क कर सकें।"
    elif 'address' not in lead_data:
        return "कृपया अपना पता (Location / Address) बताएं जहां काम करवाना है।"
    elif 'time' not in lead_data:
        return "सर्विस के लिए आपको किस समय या दिन सुविधा रहेगी?"
    else:
        return "आपकी बुकिंग रिक्वेस्ट दर्ज हो गई है! हमारे सीनियर टेक्नीशियन जल्द ही आपसे संपर्क करेंगे।"

HTML_CONTENT = """<!DOCTYPE html>
<html lang="hi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SS Enterprises - Service Assistant</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
</head>
<body class="bg-gray-100 h-screen flex justify-center items-center p-0 sm:p-4">
    <div class="w-full max-w-md bg-white h-full sm:h-[90vh] sm:rounded-2xl shadow-xl flex flex-col overflow-hidden border border-gray-200">
        <div class="bg-blue-600 p-4 text-white flex items-center justify-between shadow">
            <div class="flex items-center space-x-3">
                <div class="w-10 h-10 rounded-full bg-white text-blue-600 font-bold flex items-center justify-center text-lg shadow">SS</div>
                <div>
                    <h1 class="font-semibold leading-tight">SS Enterprises</h1>
                    <p class="text-xs text-blue-100 flex items-center gap-1">
                        <span class="w-2 h-2 rounded-full bg-green-400 inline-block"></span> दीपक (AI Assistant)
                    </p>
                </div>
            </div>
            <a href="tel:919999999999" class="text-white p-2 rounded-full hover:bg-blue-700">
                <i class="fas fa-phone-alt"></i>
            </a>
        </div>
        <div class="bg-blue-50 px-3 py-2 text-xs text-blue-800 flex justify-around border-b font-medium">
            <span>📷 CCTV</span>
            <span>⚡ Electrical</span>
            <span>💻 Laptop/PC</span>
            <span>📞 Intercom</span>
        </div>
        <div id="chat-box" class="flex-1 p-4 overflow-y-auto space-y-3 bg-slate-50">
            <div class="flex items-start space-x-2">
                <div class="w-7 h-7 rounded-full bg-blue-600 text-white text-xs flex items-center justify-center font-bold">D</div>
                <div class="bg-white p-3 rounded-2xl rounded-tl-none shadow-sm border text-gray-800 text-sm max-w-[80%]">
                    नमस्ते! मैं <b>दीपक</b>, SS Enterprises से बात कर रहा हूँ।<br>कृपया अपना <b>शुभ नाम</b> बताएं?
                </div>
            </div>
        </div>
        <div class="p-3 bg-white border-t flex items-center space-x-2">
            <input type="text" id="user-input" placeholder="Type your message..." 
                class="flex-1 border rounded-full px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-gray-50"
                onkeypress="if(event.key === 'Enter') sendMessage()">
            <button onclick="sendMessage()" class="bg-blue-600 text-white w-10 h-10 rounded-full flex items-center justify-center hover:bg-blue-700 transition">
                <i class="fas fa-paper-plane text-sm"></i>
            </button>
        </div>
    </div>
    <script>
        let leadData = {};
        let chatHistory = [];
        async function sendMessage() {
            const input = document.getElementById('user-input');
            const message = input.value.trim();
            if (!message) return;
            appendMessage(message, 'user');
            input.value = '';
            const loadingId = appendLoading();
            try {
                const res = await fetch('/api/chat', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        session_id: 'guest',
                        message: message,
                        history: chatHistory,
                        lead_data: leadData
                    })
                });
                const data = await res.json();
                removeLoading(loadingId);
                leadData = data.lead_data;
                chatHistory.push({role: 'Customer', text: message});
                chatHistory.push({role: 'Deepak', text: data.reply});
                appendMessage(data.reply, 'bot');
            } catch (err) {
                removeLoading(loadingId);
                appendMessage("माफ़ करें, सर्वर से कनेक्ट करने में समस्या आ रही है।", 'bot');
            }
        }
        function appendMessage(text, sender) {
            const box = document.getElementById('chat-box');
            const div = document.createElement('div');
            if (sender === 'user') {
                div.className = "flex justify-end";
                div.innerHTML = `<div class="bg-blue-600 text-white p-3 rounded-2xl rounded-tr-none shadow-sm text-sm max-w-[80%]">${text}</div>`;
            } else {
                div.className = "flex items-start space-x-2";
                div.innerHTML = `<div class="w-7 h-7 rounded-full bg-blue-600 text-white text-xs flex items-center justify-center font-bold">D</div>
                <div class="bg-white p-3 rounded-2xl rounded-tl-none shadow-sm border text-gray-800 text-sm max-w-[80%]">${text}</div>`;
            }
            box.appendChild(div);
            box.scrollTop = box.scrollHeight;
        }
        function appendLoading() {
            const box = document.getElementById('chat-box');
            const id = 'loading-' + Date.now();
            const div = document.createElement('div');
            div.id = id;
            div.className = "flex items-start space-x-2";
            div.innerHTML = `<div class="w-7 h-7 rounded-full bg-blue-600 text-white text-xs flex items-center justify-center font-bold">D</div>
            <div class="bg-white p-3 rounded-2xl rounded-tl-none shadow-sm border text-gray-400 text-xs italic">दीपक टाइप कर रहा है...</div>`;
            box.appendChild(div);
            box.scrollTop = box.scrollHeight;
            return id;
        }
        function removeLoading(id) {
            const el = document.getElementById(id);
            if (el) el.remove();
        }
    </script>
</body>
</html>"""

@app.get("/", response_class=HTMLResponse)
async def chat_ui():
    return HTMLResponse(content=HTML_CONTENT)

@app.get("/health")
async def health():
    return {"status": "healthy"}

@app.post("/api/chat")
async def handle_chat(req: ChatRequest):
    updated_lead = extract_lead_info(req.message, req.lead_data)
    ai_reply = await call_gemini(req.message, req.history, updated_lead)
    
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

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    uvicorn.run("app:app", host="0.0.0.0", port=port)
    
