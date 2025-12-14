from fastapi import FastAPI, HTTPException, Body
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from fastapi.middleware.cors import CORSMiddleware
from qdrant_client import QdrantClient
from langchain_qdrant import QdrantVectorStore, FastEmbedSparse, RetrievalMode
from langchain_community.embeddings.fastembed import FastEmbedEmbeddings
from groq import Groq
from dotenv import load_dotenv
from docxtpl import DocxTemplate
from io import BytesIO
from typing import List, Optional, Dict, Any
import os
import re
import uvicorn
import json
import threading

load_dotenv()

# ================= CONFIGURATION =================
QDRANT_URL = os.environ.get("QDRANT_URL")
QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
COLLECTION_NAME = "demo_collection_railway_v2"

# 📂 ตั้งค่า Template Path
TEMPLATE_DIR = "templates"
TEMPLATE_MAP = {
    "RO.01": os.path.join(TEMPLATE_DIR, "RO-01_General_Request.docx"),
    "RO.03": os.path.join(TEMPLATE_DIR, "RO-03_Guardian.docx"),
    "RO.12": os.path.join(TEMPLATE_DIR, "RO-12_Withdrawal.docx"),
    "RO.13": os.path.join(TEMPLATE_DIR, "RO-13_Resignation.docx"),
    "RO.16": os.path.join(TEMPLATE_DIR, "RO-16_Sick_Leave.docx"),
}

# ✅ 1. ฐานข้อมูลฟอร์ม
FORM_MASTER_DATA = [
    {"id": "RO.01", "name": "คำร้องทั่วไป (General Request)", "url": "https://regis.kmutt.ac.th/service/form/RO-01.pdf", "keywords": ["คำร้องทั่วไป", "ro01", "ro.01", "general", "อื่นๆ", "เรื่องทั่วไป", "สทน.01"]},
    {"id": "RO.03", "name": "หนังสือรับรองของผู้ปกครอง", "url": "https://regis.kmutt.ac.th/service/form/RO-03.pdf", "keywords": ["ผู้ปกครอง", "ro03", "ro.03", "หนังสือรับรอง", "ยินยอม", "parent", "สทน.03"]},
    {"id": "RO.04", "name": "ใบมอบฉันทะ", "url": "https://regis.kmutt.ac.th/service/form/RO-04.pdf", "keywords": ["มอบฉันทะ", "ro04", "ro.04", "แทน", "คนอื่นรับแทน", "authorization", "สทน.04"]},
    {"id": "RO.08", "name": "คำร้องขอคืนเงินค่าลงทะเบียน", "url": "https://regis.kmutt.ac.th/service/form/RO-08.pdf", "keywords": ["คืนเงิน", "ro08", "ro.08", "refund", "ค่าลงทะเบียน", "จ่ายเกิน", "ขอคืนเงิน", "สทน.08"]},
    {"id": "กค.18", "name": "ใบแจ้งความจำนงโอนเงิน", "url": "https://regis.kmutt.ac.th/service/form/18.pdf", "keywords": ["กค18", "กค.18", "โอนเงินเข้าบัญชี", "รับเงินโอน"]},
    {"id": "RO.11", "name": "คำร้องขอเลื่อนรับพระราชทานปริญญาบัตร", "url": "https://regis.kmutt.ac.th/service/form/RO-11.pdf", "keywords": ["รับปริญญา", "ro11", "ro.11", "เลื่อนรับ", "ไม่รับปริญญา", "สทน.11"]},
    {"id": "RO.12", "name": "คำร้องขอลาพักการศึกษา", "url": "https://regis.kmutt.ac.th/service/form/RO-12Updated.pdf", "keywords": ["ลาพัก", "ro12", "ro.12", "ดรอปเรียน", "drop", "พักการเรียน", "รักษาสถานภาพ", "สทน.12"]},
    {"id": "RO.13", "name": "คำร้องขอลาออก", "url": "https://regis.kmutt.ac.th/service/form/RO-13Updated.pdf", "keywords": ["ลาออก", "ro13", "ro.13", "resignation", "ออก", "quit", "สทน.13"]},
    {"id": "RO.14", "name": "คำร้องขอเปลี่ยนแปลงข้อมูลประวัติ", "url": "https://regis.kmutt.ac.th/service/form/RO-14.pdf", "keywords": ["เปลี่ยนชื่อ", "ro14", "ro.14", "เปลี่ยนนามสกุล", "แก้ประวัติ", "ที่อยู่ผิด", "คำนำหน้า", "สทน.14"]},
    {"id": "RO.15", "name": "คำร้องขอทำบัตรนักศึกษาใหม่", "url": "https://regis.kmutt.ac.th/service/form/RO-15_160718.pdf", "keywords": ["บัตรหาย", "ro15", "ro.15", "บัตรนักศึกษา", "ทำบัตรใหม่", "บัตรชำรุด", "สทน.15"]},
    {"id": "RO.16", "name": "คำร้องขอลาป่วย/ลากิจ", "url": "https://regis.kmutt.ac.th/service/form/RO-16.pdf", "keywords": ["ลาป่วย", "ro16", "ro.16", "ลากิจ", "ป่วย", "ใบรับรองแพทย์", "หยุดเรียน", "sick", "สทน.16"]},
    {"id": "RO.18", "name": "คำร้องลงทะเบียนต่ำกว่า/เกินกว่าหน่วยกิต", "url": "https://regis.kmutt.ac.th/service/form/RO-18Updated.pdf", "keywords": ["หน่วยกิตเกิน", "ro18", "ro.18", "หน่วยกิตต่ำ", "ลงเกิน", "ลงน้อย", "credits", "สทน.18"]},
    {"id": "RO.19", "name": "คำร้องลงทะเบียนวิชาสอบซ้อน", "url": "https://regis.kmutt.ac.th/service/form/RO-19.pdf", "keywords": ["สอบซ้อน", "ro19", "ro.19", "เวลาสอบชน", "exam conflict", "สทน.19"]},
    {"id": "RO.20", "name": "คำร้องลงทะเบียนวิชานอกหลักสูตร", "url": "https://regis.kmutt.ac.th/service/form/RO-20.pdf", "keywords": ["นอกหลักสูตร", "ro20", "ro.20", "วิชาเลือกเสรี", "free elective", "สทน.20"]},
    {"id": "RO.21", "name": "คำร้องลงทะเบียนเรียนแบบบุคคลภายนอก", "url": "https://regis.kmutt.ac.th/service/form/RO-21.pdf", "keywords": ["บุคคลภายนอก", "ro21", "ro.21", "visitor", "คนนอก", "สทน.21"]},
    {"id": "RO.22", "name": "คำร้องขอสมัครสอบโดยไม่ต้องเข้าเรียน / ผ่อนผัน", "url": "https://regis.kmutt.ac.th/service/form/RO-22.pdf", "keywords": ["ขาดเรียน", "ro22", "ro.22", "ผ่อนผัน", "ไม่ได้เข้าเรียน", "สมัครสอบ", "สทน.22"]},
    {"id": "RO.23", "name": "คำร้องขอเปลี่ยน/เทียบรายวิชา", "url": "https://regis.kmutt.ac.th/service/form/RO-23.pdf", "keywords": ["เทียบวิชา", "ro23", "ro.23", "เปลี่ยนวิชา", "transfer", "เทียบโอน", "สทน.23"]},
    {"id": "RO.25", "name": "ใบลงทะเบียนเรียน", "url": "https://regis.kmutt.ac.th/service/form/RO-25.pdf", "keywords": ["ใบลงทะเบียน", "ro25", "ro.25", "register", "regis", "สทน.25"]},
    {"id": "RO.26", "name": "ใบเพิ่ม-ลด-ถอน-เปลี่ยนกลุ่ม", "url": "https://regis.kmutt.ac.th/service/form/RO-26Updated.pdf", "keywords": ["เพิ่มวิชา", "ro26", "ro.26", "ถอนวิชา", "เปลี่ยนเซค", "เปลี่ยน sec", "add/drop", "ลดวิชา", "ถอน w", "ติด w", "สทน.26"]},
]

# สร้าง FORM_DB สำหรับค้นหา URL ให้รวดเร็วขึ้น
FORM_DB = {}
for item in FORM_MASTER_DATA:
    FORM_DB[item["id"]] = item["url"]
    FORM_DB[item["name"]] = item["url"]
    FORM_DB[item["id"].replace(".", "")] = item["url"]   # ตัวอย่าง: "RO01"
    FORM_DB[item["id"].replace(".", ". ")] = item["url"] # ตัวอย่าง: "RO. 01"
    
    for kw in item["keywords"]:
        FORM_DB[kw] = item["url"]

# ================= DATA MODELS =================
class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    message: str
    history: List[ChatMessage] = Field(default_factory=list)

# ================= PROMPT (UPDATED to Prevent Repetition) =================
SYSTEM_PROMPT_TEXT = f'''
คุณคือผู้ช่วยอัจฉริยะด้านคำร้องและเอกสารของ มจธ. (KMUTT)
ตอบให้กระชับ ชัดเจน เป็นขั้นตอน ใช้ภาษาไทยที่เป็นมิตรกับนักศึกษา ให้คิดวิเคราะห์ก่อนตอบ หากถามกำกวมให้ถามเพื่อขอข้อมูลเพิ่มเติม
ถ้ามีแบบฟอร์มหรือลิงก์ต้องใส่ให้ครบ โดยต้องมีความถูกต้อง แม่นยำ และอ้างอิงจากเอกสารที่ได้รับมอบหมาย (Source Documents) เท่านั้น

📚 **ข้อมูลอ้างอิง (Source of Truth):**
        {FORM_LIST_TEXT}
**ตรวจจากข้อมูลอ้างอิงให้ถี่ถ้วนก่อนนำข้อมูลไปใช้**

Core Directives (กฎเหล็ก):
1. Zero Hallucination: ห้ามคิดเอง ห้ามเดาขั้นตอน หรือนำความรู้ภายนอกมาตอบ หากข้อมูลไม่มีในเอกสาร ให้ตอบว่า "ไม่มีข้อมูลในเอกสารอ้างอิง" เท่านั้น
2. Strict Citation: ทุกประโยคที่เป็นข้อเท็จจริง (ชื่อฟอร์ม, ขั้นตอน, ผู้ลงนาม, ช่องทาง) ต้องอ้างอิงจากเอกสารเสมอ
3. Language: ตอบกลับเป็นภาษาไทยที่สุภาพ เป็นทางการ และเข้าใจง่าย
4. Data Extraction: หากผู้ใช้ให้ข้อมูลส่วนตัวหรือสั่งให้ร่างเอกสาร ต้องดึงข้อมูลเหล่านั้นออกมาเป็น JSON เสมอ

Instruction for Handling Queries (ขั้นตอนการคิดก่อนตอบ):

Step 1: Intent Analysis & Disambiguation (วิเคราะห์เจตนา)
  1. หากคำถามกว้างหรือกำกวม ห้ามสรุปเอาเอง ให้ตอบแบบ "Scenario-Based" (แยกกรณี)
  2. หากผู้ใช้ระบุความต้องการชัดเจน (เช่น "ปวดหัว ขอลากิจหน่อย ผมชื่อ...") ให้ข้ามไป Step 4

Step 2: Information Retrieval (ค้นหาและจับคู่)
  1. ค้นหาข้อมูลจาก Source โดยดูที่ Keywords: ชื่อฟอร์ม (RO.xx), ช่องทางการยื่น (Online/Paper)
  2. แยกแยะให้ชัดเจนระหว่าง "การยื่นออนไลน์ (New ACIS)" กับ "การยื่นเอกสาร (Paper/PDF)"

Step 3: Response Structure (โครงสร้างคำตอบ - กรณีถามข้อมูล)
  1. สรุปเบื้องต้น: ทวนคำถามและบอกว่ามีกี่กรณี
  2. รายละเอียดแต่ละกรณี (Bullet Points): ชื่อกรณี, แบบฟอร์ม, ช่องทาง, ขั้นตอน, การอนุมัติ
  3. จบด้วยคำถามเสนอความช่วยเหลือ: "ต้องการให้ผมช่วยร่างคำร้องนี้ให้เลยไหมครับ?"

Step 4: Drafting & Action (โครงสร้างคำตอบ - กรณีร่างเอกสาร/รับข้อมูล)
  *ใช้เมื่อผู้ใช้บอกข้อมูล (ชื่อ/คณะ/เหตุผล) หรือสั่งให้ร่าง*
  1. Action: แปลงเหตุผลภาษาพูดของผู้ใช้ เป็น "ภาษาเขียนทางการ"
  2. Response: แสดงข้อความที่ร่างให้
  3. JSON Output: แนบ Tag `[[FORM_DATA: {...}]]` ไว้ท้ายคำตอบเสมอ

---

JSON Output Rules (กฎการส่งข้อมูล):
ต้องส่ง Tag นี้ไว้ท้ายสุดเสมอเมื่อมีการร่างหรือแก้ไขข้อมูล:
[[FORM_DATA: {{
    "form_id": "RO.xx (รหัสฟอร์ม)",
    "name": "ดึงจากบริบท (ถ้ามี)",
    "faculty": "ดึงจากบริบท (ถ้ามี)",
    "department": "ดึงจากบริบท (ถ้ามี)",
    "draft_subject": "หัวข้อเรื่องแบบทางการ",
    "draft_reason": "เนื้อหาความจำเป็นที่เรียบเรียงเป็นภาษาทางการ"
}}]]
*หมายเหตุ: ห้ามส่ง key student_id (ระบบจะจัดการเอง)*

---

ตัวอย่างคำตอบที่ดี (กรณีถามข้อมูล):
"การลา มี 2 กรณีที่เกี่ยวข้อง
1. กรณีลาป่วย
 - แบบฟอร์ม: สทน. 16
 - ขั้นตอน: ยื่นต่ออาจารย์ที่ปรึกษา...
ต้องการให้ผมช่วยร่างคำร้องไหมครับ?"

ตัวอย่างคำตอบที่ดี (กรณีสั่งร่าง/ให้ข้อมูล):
"รับทราบครับคุณสมชาย หายไวๆ นะครับ ผมได้ร่างคำร้องให้เรียบร้อยแล้ว:

📝 **ข้อความร่าง:**
'เนื่องจากข้าพเจ้ามีอาการเจ็บป่วยกะทันหัน (อาการปวดศีรษะรุนแรง) จึงไม่สามารถเข้าเรียนได้...'

[[FORM_DATA: {{
    "form_id": "RO.16",
    "name": "นายสมชาย ใจดี",
    "faculty": "วิศวกรรมศาสตร์",
    "department": "วิศวกรรมคอมพิวเตอร์",
    "draft_subject": "ขอลาหยุดเรียนเนื่องจากอาการเจ็บป่วย",
    "draft_reason": "เนื่องจากข้าพเจ้ามีอาการเจ็บป่วยกะทันหัน (อาการปวดศีรษะรุนแรง)..."
}}]]"
'''

# ================= GLOBAL VARIABLES =================
vector_store_instance = None
groq_client_instance = None

lock = threading.Lock()

def get_rag_system():
    global vector_store_instance, groq_client_instance
    if vector_store_instance is None:
        print("⏳ Lazy Loading: Initializing AI Models...")
        embeddings = FastEmbedEmbeddings(model_name="BAAI/bge-small-en-v1.5")
        sparse_embeddings = FastEmbedSparse(model_name="Qdrant/bm25")
        client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
        vector_store_instance = QdrantVectorStore(
            client=client,
            collection_name=COLLECTION_NAME,
            embedding=embeddings,
            sparse_embedding=sparse_embeddings,
            retrieval_mode=RetrievalMode.HYBRID,
            vector_name="dense_vector",
            sparse_vector_name="sparse_vector",
        )
        groq_client_instance = Groq(api_key=GROQ_API_KEY)
        print("✅ Lazy Loading: Models are ready!")
    return vector_store_instance, groq_client_instance

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 🧠 AI Function
def get_ai_response(rag_context_text: str, current_question: str, history: List[ChatMessage], groq_client: Groq):
    messages = [{"role": "system", "content": SYSTEM_PROMPT_TEXT}]
    for msg in history:
        messages.append({"role": msg.role, "content": msg.content})

    final_user_content = f"Reference Context (ข้อมูลอ้างอิง):\n{rag_context_text}\n\nUser Question (คำถามปัจจุบัน): {current_question}"
    messages.append({"role": "user", "content": final_user_content})
    
    try:
        response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=messages,
            temperature=0.1,
            max_tokens=1024,
            top_p=0.9
        )
        ai_response = response.choices[0].message.content
        # ตรวจสอบว่าคำตอบซ้ำกับข้อความใน history หรือไม่
        if ai_response.strip() in [msg.content.strip() for msg in history]:
            raise Exception("AI response detected as duplicate")
        return ai_response
    except Exception as e:
        print(f"Groq API Error: {e}")
        return f"ขออภัยครับ เกิดข้อผิดพลาดในการเชื่อมต่อกับ AI ({str(e)})"

@app.get("/")
def read_root():
    return {"status": "Server is running 🚀"}

@app.post("/chat")
def chat_endpoint(req: ChatRequest):
    print(f"📩 Incoming Message: {req.message}")
    vector_store, groq_client = get_rag_system()
    user_query = req.message.lower()
    try:
        # ส่วน Text & Keyword Matching
        context_text = ""
        sources = []
        for keyword, url in FORM_DB.items():
            if keyword in user_query:
                context_text += f"พบฟอร์ม: {keyword} ({url})\n"
                sources.append({"keyword": keyword, "url": url})

        # หากไม่เจอใน FORM_DB ให้ใช้ Vector Search
        if not sources:
            search_results = vector_store.similarity_search(user_query, k=3)
            for doc in search_results:
                context_text += f"{doc.page_content}\n"
                sources.append({"url": doc.metadata.get("url", "")})

        # รับข้อมูลจาก AI
        answer = get_ai_response(context_text, req.message, groq_client)
        return {"reply": answer, "sources": sources}

    except Exception as e:
        print(f"Error: {e}")
        return {"reply": "เกิดข้อผิดพลาดในระบบ", "sources": []}

        # 2. Vector Search
        k_val = 5
        search_results = vector_store.similarity_search(req.message, k=k_val)
        
        for doc in search_results:
            context_text += f"{doc.page_content}\n\n"
            # Logic การดึง Source URL แบบเดิมของคุณ
            file_path = doc.metadata.get("file", "เอกสารทั่วไป")
            doc_url = ""
            display_name = file_path.split("/")[-1]
            for item in FORM_MASTER_DATA:
                if item["url"] in file_path or item["id"] in doc.page_content:
                    doc_url = item["url"]
                    display_name = f"{item['id']} {item['name']}"
                    break
            if not doc_url:
                found_urls = re.findall(r'(https?://[^\s\)]+)', doc.page_content)
                if found_urls: doc_url = found_urls[0]
            if doc_url:
                if not any(s['url'] == doc_url for s in sources):
                    sources.append({"doc": display_name, "page": 1, "url": doc_url})

        # 3. AI Processing with History
        answer = get_ai_response(context_text, req.message, req.history, groq_client)
        
        return { "reply": answer, "sources": sources }
    
    except Exception as e:
        print(f"Error: {e}")
        return { "reply": "เกิดข้อผิดพลาดในระบบ", "sources": [] }

# ✅ API สร้างเอกสาร
@app.post("/generate-form")
async def generate_form_endpoint(data: dict = Body(...)):
    print(f"📝 กำลังสร้างฟอร์ม: {data}")
    
    form_type = data.get("formType") or data.get("form_type") or data.get("form_id") or ""
    
    # ปรับจูนให้รองรับ input หลากหลาย เช่น "RO.16" หรือ "RO-16"
    form_type = form_type.replace("-", ".").upper() 

    if form_type not in TEMPLATE_MAP:
        # Fallback กรณีหาฟอร์มไม่เจอ ให้ใช้ General Request
        print(f"⚠️ ไม่พบ Template {form_type}, ใช้ RO.01 แทน")
        form_type = "RO.01"

    template_path = TEMPLATE_MAP.get(form_type)
    if not template_path or not os.path.exists(template_path):
        raise HTTPException(status_code=500, detail=f"Server Missing File: {template_path}")

    try:
        doc = DocxTemplate(template_path)
        
        # เตรียม Context สำหรับ Docxtpl
        context = {
            "student_id": data.get("studentId") or data.get("student_id") or ".........", # เผื่อกรณีไม่มีข้อมูล
            "student_name": data.get("name") or "..................................................",
            "faculty": data.get("faculty") or "....................",
            "department": data.get("department") or "....................",
            "year": data.get("year") or "...",
            "semester": "2/2567",
            "phone": data.get("student_tel") or data.get("phone_mobile") or "....................",
            "reason": data.get("draft_reason") or "",
            "request_subject": data.get("draft_subject") or "",
            **data 
        }
        
        doc.render(context)
        file_stream = BytesIO()
        doc.save(file_stream)
        file_stream.seek(0)
        
        filename = f"Filled_{form_type}_{context['student_id']}.docx"
        
        return StreamingResponse(
            file_stream, 
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

    except Exception as e:
        print(f"❌ Error Generating Doc: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
