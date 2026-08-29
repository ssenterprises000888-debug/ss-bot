import os
import re
import json
import logging
import sqlite3
from datetime import datetime
from typing import Dict, Any, List, Optional
from contextlib import contextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn
import aiohttp
from dotenv import load_dotenv

# ==================== CONFIGURATION ====================
load_dotenv()

GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '').strip()
ADMIN_SECRET_KEY = os.getenv('ADMIN_SECRET_KEY', 'admin123')
DATABASE_FILE = os.getenv('DATABASE_FILE', 'leads.db')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("SS_Enterprises")

# ==================== DATABASE ====================
class Database:
    def __init__(self, db_file: str):
        self.db_file = db_file
        self.init_db()
    
    @contextmanager
    def get_connection(self):
        conn = sqlite3.connect(self.db_file)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
    
    def init_db(self):
        with self.get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS leads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT,
                    phone TEXT,
                    address TEXT,
                    time TEXT,
                    session_id TEXT,
                    timestamp TEXT,
                    status TEXT DEFAULT 'pending'
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT UNIQUE,
                    lead_data TEXT,
                    history TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
            """)
            conn.commit()
    
    def save_lead(self, lead_data: Dict[str, Any], session_id: str) -> int:
        with self.get_connection() as conn:
            cursor = conn.execute("""
                INSERT INTO leads (name, phone, address, time, session_id, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                lead_data.get('name', ''),
                lead_data.get('phone', ''),
                lead_data.get('address', ''),
                lead_data.get('time', ''),
                session_id,
                datetime.now().strftime('%d-%m-%Y %I:%M %p')
            ))
            conn.commit()
            return cursor.lastrowid
    
    def get_all_leads(self, limit: int = 100) -> List[Dict]:
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM leads ORDER BY id DESC LIMIT ?",
                (limit,)
            )
            return [dict(row) for row in cursor.fetchall()]
    
    def update_lead_status(self, lead_id: int, status: str):
        with self.get_connection() as conn:
            conn.execute(
                "UPDATE leads SET status = ? WHERE id = ?",
                (status, lead_id)
            )
            conn.commit()
    
    def get_lead_by_id(self, lead_id: int) -> Optional[Dict]:
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM leads WHERE id = ?",
                (lead_id,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_stats(self) -> Dict:
        with self.get_connection() as conn:
            total = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
            pending = conn.execute("SELECT COUNT(*) FROM leads WHERE status = 'pending'").fetchone()[0]
            completed = conn.execute("SELECT COUNT(*) FROM leads WHERE status = 'completed'").fetchone()[0]
            return {
                'total': total,
                'pending': pending,
                'completed': completed
            }

db = Database(DATABASE_FILE)

# ==================== PYDANTIC MODELS ====================
class ChatRequest(BaseModel):
    session_id: str
    message: str
    history: List[Dict[str, str]] = []
    lead_data: Dict[str, str] = {}

class LeadUpdate(BaseModel):
    lead_id: int
    status: str

# ==================== AI SYSTEM PROMPT ====================
SYSTEM_PROMPT = """You are Deepak, an intelligent and polite assistant at SS Enterprises - a professional service shop providing:
1. CCTV Camera Setup & Repair
2. Electrical Works
3. Computer & Laptop Repair
4. Intercom System Services

Your objective:
- Speak in natural, friendly Hinglish (Hindi + English).
- Collect the customer's: Name, 10-digit Phone Number, Address/Location, and Preferred Time.
- Ask one clear question at a time.
- Keep responses short, concise, and helpful.

IMPORTANT RULES:
1. Always be polite and professional
2. If customer asks about services, explain briefly
3. Never ask for payment or sensitive information
4. Keep responses under 3 sentences
5. Use emojis occasionally for friendliness"""

# ==================== LEAD EXTRACTION ====================
class LeadExtractor:
    @staticmethod
    def extract(data: Dict[str, str], message: str) -> Dict[str, str]:
        """Extract lead information from message"""
        result = data.copy()
        message_lower = message.lower()
        
        # Extract Phone Number (10 digits, starts with 6-9)
        phone_match = re.search(r'\b[6-9]\d{9}\b', message)
        if phone_match and not result.get('phone'):
            result['phone'] = phone_match.group()
        
        # Extract Name
        name_patterns = [
            r'(?:mera naam |my name is |name is |naam |nam )([A-Za-z\s]{2,30})',
            r'^([A-Za-z\s]{2,30})$'
        ]
        if not result.get('name'):
            for pattern in name_patterns:
                match = re.search(pattern, message, re.IGNORECASE)
                if match:
                    name = match.group(1).strip()
                    if len(name.split()) <= 4 and not any(c.isdigit() for c in name):
                        result['name'] = name.title()
                        break
        
        # Extract Address
        address_keywords = ['colony', 'gali', 'road', 'chowk', 'ward', 'nagar', 'siwan', 'bihar', 
                           'house', 'near', 'address', 'पता', 'गली', 'रोड', 'चौक', 'मोहल्ला']
        if not result.get('address'):
            if any(k in message_lower for k in address_keywords):
                result['address'] = message.strip()
        
        # Extract Time
        time_keywords = ['baje', 'am', 'pm', 'kal', 'aaj', 'morning', 'evening', 'time', 
                        'दोपहर', 'शाम', 'सुबह', 'रात']
        if not result.get('time'):
            if any(k in message_lower for k in time_keywords):
                result['time'] = message.strip()
        
        return result

extractor = LeadExtractor()

# ==================== GEMINI API ====================
async def call_gemini(message: str, history: List[Dict], lead_data: Dict) -> str:
    """Call Gemini API with fallback responses"""
    
    # Check if all details collected
    required = ['name', 'phone', 'address', 'time']
    has_all = all(k in lead_data for k in required)
    
    if has_all:
        return "✅ *बहुत अच्छा!* आपकी सारी जानकारी मिल गई है।\n\n" \
               "📞 हमारे *सीनियर टेक्नीशियन* जल्द ही आपसे संपर्क करेंगे।\n\n" \
               "🙏 *SS Enterprises* - आपकी सेवा में! 😊"
    
    if GEMINI_API_KEY and GEMINI_API_KEY.startswith("AIza"):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
        headers = {"Content-Type": "application/json"}
        
        # Build prompt with context
        hist_text = "\n".join([f"{h['role']}: {h['text']}" for h in history[-6:]])
        current_data = {k: v for k, v in lead_data.items() if v}
        
        prompt = f"""{SYSTEM_PROMPT}

Current Collected Data:
{json.dumps(current_data, indent=2)}

Recent Conversation:
{hist_text}

Customer: {message}

Deepak:"""
        
        payload = {
            "contents": [{
                "parts": [{"text": prompt}]
            }],
            "generationConfig": {
                "temperature": 0.7,
                "maxOutputTokens": 150
            }
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload, timeout=10) as resp:
                    if resp.status == 200:
                        res_json = await resp.json()
                        reply = res_json['candidates'][0]['content']['parts'][0]['text'].strip()
                        if reply:
                            return reply
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
    
    # ==================== FALLBACK RESPONSES ====================
    if 'name' not in lead_data:
        return "👋 नमस्ते! मैं **दीपक**, SS Enterprises का AI असिस्टेंट हूँ।\n\n" \
               "हम ये सर्विसेज़ देते हैं:\n" \
               "📷 CCTV कैमरा\n⚡ Electrical Work\n💻 Computer/Laptop Repair\n📞 Intercom System\n\n" \
               "**आपका शुभ नाम क्या है?** 😊"
    
    if 'phone' not in lead_data:
        return f"🙏 धन्यवाद {lead_data['name']} जी!\n\n" \
               "📱 कृपया अपना **10 अंकों का मोबाइल नंबर** बताएं\n" \
               "(हमारे टेक्नीशियन आपसे इसी पर संपर्क करेंगे)"
    
    if 'address' not in lead_data:
        return f"📍 कृपया अपना **पता** बताएं\n" \
               "(जहाँ पर सर्विस करवानी है)\n\n" \
               "जैसे: गली/मोहल्ला, चौक, शहर, Bihar"
    
    if 'time' not in lead_data:
        return f"⏰ किस **समय** या **दिन** पर सर्विस चाहिए?\n" \
               "जैसे: कल सुबह 10 बजे, आज शाम 4 बजे, या जल्द से जल्द"
    
    return "मुझे कुछ समझ नहीं आया। कृपया दोबारा बताएं।"

# ==================== FASTAPI APP ====================
app = FastAPI(
    title="SS Enterprises AI Assistant",
    description="AI-powered service booking assistant for SS Enterprises",
    version="2.0.0"
)

# ==================== HTML UI ====================
HTML_CONTENT = """<!DOCTYPE html>
<html lang="hi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SS Enterprises - AI Assistant</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
    <style>
        .chat-bubble-user {
            background: linear-gradient(135deg, #2563eb, #1d4ed8);
            color: white;
            border-radius: 18px 18px 4px 18px;
            padding: 10px 16px;
            max-width: 80%;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .chat-bubble-bot {
            background: white;
            color: #1f2937;
            border-radius: 18px 18px 18px 4px;
            padding: 10px 16px;
            max-width: 80%;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
            border: 1px solid #e5e7eb;
        }
        .typing-indicator {
            display: inline-block;
            background: white;
            padding: 10px 16px;
            border-radius: 18px 18px 18px 4px;
            border: 1px solid #e5e7eb;
        }
        .typing-dot {
            display: inline-block;
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: #9ca3af;
            margin: 0 2px;
            animation: typing 1.4s infinite both;
        }
        .typing-dot:nth-child(1) { animation-delay: 0s; }
        .typing-dot:nth-child(2) { animation-delay: 0.2s; }
        .typing-dot:nth-child(3) { animation-delay: 0.4s; }
        @keyframes typing {
            0%, 60%, 100% { transform: translateY(0); opacity: 0.4; }
            30% { transform: translateY(-6px); opacity: 1; }
        }
        .service-tag {
            background: #dbeafe;
            color: #1d4ed8;
            padding: 2px 10px;
            border-radius: 12px;
            font-size: 10px;
            font-weight: 600;
        }
        ::-webkit-scrollbar {
            width: 4px;
        }
        ::-webkit-scrollbar-track {
            background: #f1f1f1;
        }
        ::-webkit-scrollbar-thumb {
            background: #94a3b8;
            border-radius: 4px;
        }
    </style>
</head>
<body class="bg-gray-100 h-screen flex justify-center items-center p-2 sm:p-4 font-sans">
    <div class="w-full max-w-md bg-white h-full sm:h-[95vh] sm:rounded-2xl shadow-2xl flex flex-col overflow-hidden border border-gray-200">
        <!-- Header -->
        <div class="bg-gradient-to-r from-blue-600 to-blue-700 p-4 text-white flex items-center justify-between shadow-lg">
            <div class="flex items-center space-x-3">
                <div class="w-11 h-11 rounded-full bg-white text-blue-600 font-bold flex items-center justify-center text-lg shadow-md">
                    SS
                </div>
                <div>
                    <h1 class="font-bold text-lg leading-tight">SS Enterprises</h1>
                    <p class="text-xs text-blue-100 flex items-center gap-1">
                        <span class="w-2 h-2 rounded-full bg-green-400 inline-block animate-pulse"></span>
                        Deepak (AI Assistant)
                    </p>
                </div>
            </div>
            <div class="flex gap-2">
                <a href="tel:919999999999" class="text-white p-2 rounded-full hover:bg-blue-500 transition">
                    <i class="fas fa-phone-alt text-sm"></i>
                </a>
                <button onclick="location.reload()" class="text-white p-2 rounded-full hover:bg-blue-500 transition">
                    <i class="fas fa-redo text-sm"></i>
                </button>
            </div>
        </div>
        
        <!-- Services Bar -->
        <div class="bg-blue-50 px-3 py-2 text-xs text-blue-800 flex justify-around border-b font-medium">
            <span>📷 CCTV</span>
            <span>⚡ Electrical</span>
            <span>💻 Laptop/PC</span>
            <span>📞 Intercom</span>
        </div>
        
        <!-- Chat Box -->
        <div id="chat-box" class="flex-1 p-4 overflow-y-auto space-y-3 bg-gray-50">
            <div class="flex items-start space-x-2">
                <div class="w-8 h-8 rounded-full bg-blue-600 text-white text-xs flex items-center justify-center font-bold flex-shrink-0">D</div>
                <div class="chat-bubble-bot">
                    👋 नमस्ते! मैं <b>दीपक</b>, SS Enterprises का AI असिस्टेंट हूँ।<br><br>
                    हम ये सर्विसेज़ देते हैं:<br>
                    📷 CCTV कैमरा &nbsp;⚡ Electrical &nbsp;💻 Laptop/PC &nbsp;📞 Intercom<br><br>
                    <b>कृपया अपना शुभ नाम बताएं?</b> 😊
                </div>
            </div>
        </div>
        
        <!-- Input Area -->
        <div class="p-3 bg-white border-t border-gray-200 flex items-center gap-2">
            <input type="text" id="user-input" placeholder="Type your message..." 
                class="flex-1 border border-gray-300 rounded-full px-5 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-gray-50"
                onkeypress="if(event.key === 'Enter') sendMessage()"
                autocomplete="off">
            <button onclick="sendMessage()" id="send-btn" 
                class="bg-blue-600 text-white w-11 h-11 rounded-full flex items-center justify-center hover:bg-blue-700 transition shadow-md hover:shadow-lg">
                <i class="fas fa-paper-plane text-sm"></i>
            </button>
        </div>
    </div>

    <script>
        let leadData = {};
        let chatHistory = [];
        let isLoading = false;
        let messageCount = 0;

        function appendMessage(text, sender) {
            const box = document.getElementById('chat-box');
            const div = document.createElement('div');
            
            if (sender === 'user') {
                div.className = "flex justify-end";
                div.innerHTML = `<div class="chat-bubble-user">${text}</div>`;
            } else {
                div.className = "flex items-start space-x-2";
                div.innerHTML = `
                    <div class="w-8 h-8 rounded-full bg-blue-600 text-white text-xs flex items-center justify-center font-bold flex-shrink-0">D</div>
                    <div class="chat-bubble-bot">${text}</div>
                `;
            }
            box.appendChild(div);
            box.scrollTop = box.scrollHeight;
        }

        function showTyping() {
            const box = document.getElementById('chat-box');
            const id = 'typing-' + Date.now();
            const div = document.createElement('div');
            div.id = id;
            div.className = "flex items-start space-x-2";
            div.innerHTML = `
                <div class="w-8 h-8 rounded-full bg-blue-600 text-white text-xs flex items-center justify-center font-bold flex-shrink-0">D</div>
                <div class="typing-indicator">
                    <span class="typing-dot"></span>
                    <span class="typing-dot"></span>
                    <span class="typing-dot"></span>
                </div>
            `;
            box.appendChild(div);
            box.scrollTop = box.scrollHeight;
            return id;
        }

        function removeTyping(id) {
            const el = document.getElementById(id);
            if (el) el.remove();
        }

        async function sendMessage() {
            if (isLoading) return;
            
            const input = document.getElementById('user-input');
            const message = input.value.trim();
            if (!message) return;
            
            // Append user message
            appendMessage(message, 'user');
            input.value = '';
            isLoading = true;
            document.getElementById('send-btn').disabled = true;
            
            // Show typing indicator
            const typingId = showTyping();
            
            try {
                const response = await fetch('/api/chat', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        session_id: 'guest_' + Date.now(),
                        message: message,
                        history: chatHistory,
                        lead_data: leadData
                    })
                });
                
                const data = await response.json();
                removeTyping(typingId);
                
                // Update data
                leadData = data.lead_data || {};
                chatHistory.push({role: 'Customer', text: message});
                chatHistory.push({role: 'Deepak', text: data.reply});
                
                // Show bot response
                appendMessage(data.reply, 'bot');
                
                // If lead complete, show success message
                if (data.is_completed) {
                    setTimeout(() => {
                        appendMessage('✅ आपकी बुकिंग हो गई है! हमारे टेक्नीशियन जल्द ही आपसे संपर्क करेंगे। 🙏', 'bot');
                    }, 1000);
                }
                
            } catch (error) {
                removeTyping(typingId);
                appendMessage('❌ क्षमा करें, सर्वर से कनेक्ट करने में समस्या आ रही है। कृपया कुछ देर बाद प्रयास करें।', 'bot');
                console.error('Error:', error);
            }
            
            isLoading = false;
            document.getElementById('send-btn').disabled = false;
            input.focus();
        }

        // Auto-focus on load
        document.addEventListener('DOMContentLoaded', () => {
            document.getElementById('user-input').focus();
        });
    </script>
</body>
</html>"""

# ==================== API ROUTES ====================
@app.get("/", response_class=HTMLResponse)
async def chat_ui():
    return HTMLResponse(content=HTML_CONTENT)

@app.get("/health")
async def health_check():
    stats = db.get_stats()
    return JSONResponse({
        "status": "healthy",
        "leads_count": stats['total'],
        "timestamp": datetime.now().isoformat()
    })

@app.post("/api/chat")
async def handle_chat(req: ChatRequest):
    """Main chat endpoint"""
    try:
        # Extract lead info
        updated_lead = extractor.extract(req.lead_data, req.message)
        
        # Get AI response
        ai_reply = await call_gemini(req.message, req.history, updated_lead)
        
        # Check if all fields collected
        required = ['name', 'phone', 'address', 'time']
        is_completed = all(k in updated_lead for k in required)
        
        # Save lead if complete and not saved
        if is_completed and not req.lead_data.get('_saved'):
            updated_lead['_saved'] = 'yes'
            lead_id = db.save_lead(updated_lead, req.session_id)
            logger.info(f"New lead saved: ID {lead_id} - {updated_lead.get('name')}")
        
        return JSONResponse({
            "reply": ai_reply,
            "lead_data": updated_lead,
            "is_completed": is_completed
        })
        
    except Exception as e:
        logger.error(f"Chat error: {e}")
        return JSONResponse({
            "reply": "❌ क्षमा करें, कुछ तकनीकी समस्या आ गई। कृपया कुछ देर बाद प्रयास करें।",
            "lead_data": req.lead_data,
            "is_completed": False
        })

# ==================== ADMIN ROUTES ====================
@app.get("/admin")
async def admin_panel():
    """Admin dashboard HTML"""
    return HTMLResponse("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>SS Enterprises - Admin Panel</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
    </head>
    <body class="bg-gray-100 p-4">
        <div class="max-w-4xl mx-auto">
            <div class="bg-white rounded-xl shadow-lg p-6">
                <h1 class="text-2xl font-bold text-blue-600 mb-4">
                    <i class="fas fa-shield-alt"></i> Admin Panel - SS Enterprises
                </h1>
                <div class="mb-4">
                    <label class="block text-sm font-medium text-gray-700">Admin Key</label>
                    <input type="password" id="adminKey" class="mt-1 block w-full border rounded-lg px-3 py-2" placeholder="Enter admin key">
                    <button onclick="loadLeads()" class="mt-2 bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700">
                        <i class="fas fa-sync"></i> Load Leads
                    </button>
                </div>
                <div id="leadsContainer" class="mt-4">
                    <p class="text-gray-500 text-center">Enter admin key to view leads</p>
                </div>
            </div>
        </div>
        <script>
        async function loadLeads() {
            const key = document.getElementById('adminKey').value;
            if (!key) {
                alert('Please enter admin key');
                return;
            }
            try {
                const res = await fetch(`/admin/leads?key=${key}`);
                const data = await res.json();
                const container = document.getElementById('leadsContainer');
                if (data.error) {
                    container.innerHTML = `<div class="bg-red-100 text-red-700 p-4 rounded-lg">${data.error}</div>`;
                    return;
                }
                let html = `<div class="bg-green-100 text-green-700 p-4 rounded-lg mb-4">
                    <b>Total Leads:</b> ${data.total_leads}
                </div>`;
                data.leads.forEach((lead, index) => {
                    html += `
                        <div class="border rounded-lg p-4 mb-3 hover:shadow-md transition">
                            <div class="flex justify-between items-start">
                                <div>
                                    <b class="text-lg">${lead.name || 'N/A'}</b>
                                    <span class="ml-2 px-2 py-1 text-xs rounded-full ${
                                        lead.status === 'pending' ? 'bg-yellow-100 text-yellow-800' : 'bg-green-100 text-green-800'
                                    }">${lead.status || 'pending'}</span>
                                </div>
                                <div class="text-sm text-gray-500">${lead.timestamp}</div>
                            </div>
                            <div class="grid grid-cols-2 gap-2 mt-2 text-sm">
                                <div><i class="fas fa-phone"></i> ${lead.phone || 'N/A'}</div>
                                <div><i class="fas fa-map-marker-alt"></i> ${lead.address || 'N/A'}</div>
                                <div><i class="fas fa-clock"></i> ${lead.time || 'N/A'}</div>
                                <div><i class="fas fa-id"></i> #${lead.id}</div>
                            </div>
                        </div>
                    `;
                });
                container.innerHTML = html;
            } catch (error) {
                alert('Error loading leads');
            }
        }
        </script>
    </body>
    </html>
    """)
