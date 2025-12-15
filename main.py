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
from typing import List, Optional
import os
import re
import uvicorn

load_dotenv()

# ================= CONFIGURATION =================
QDRANT_URL = os.environ.get("QDRANT_URL")
QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
COLLECTION_NAME = "demo_collection_railway_v2"

# 📂 ตั้งค่า Template
TEMPLATE_DIR = "templates"
TEMPLATE_MAP = {
    "RO.01": os.path.join(TEMPLATE_DIR, "RO-01_General_Request.docx"),
    "RO.03": os.path.join(TEMPLATE_DIR, "RO-03_Guardian.docx"),
    "RO.12": os.path.join(TEMPLATE_DIR, "RO-12_Withdrawal.docx"),
    "RO.13": os.path.join(TEMPLATE_DIR, "RO-13_Resignation.docx"),
    "RO.16": os.path.join(TEMPLATE_DIR, "RO-16_Sick_Leave.docx"),
}

# ✅ ยังคงเก็บ FORM_MASTER_DATA ไว้แค่เพื่อ extract URL จาก chunks (ไม่ใช้ keyword matching)
FORM_MASTER_DATA = [
    {"id": "RO.01", "name": "คำร้องทั่วไป (General Request)", "url": "https://regis.kmutt.ac.th/service/form/RO-01.pdf"},
    {"id": "RO.03", "name": "หนังสือรับรองของผู้ปกครอง", "url": "https://regis.kmutt.ac.th/service/form/RO-03.pdf"},
    {"id": "RO.04", "name": "ใบมอบฉันทะ", "url": "https://regis.kmutt.ac.th/service/form/RO-04.pdf"},
    {"id": "RO.08", "name": "คำร้องขอคืนเงินค่าลงทะเบียน", "url": "https://regis.kmutt.ac.th/service/form/RO-08.pdf"},
    {"id": "กค.18", "name": "ใบแจ้งความจำนงโอนเงิน", "url": "https://regis.kmutt.ac.th/service/form/18.pdf"},
    {"id": "RO.11", "name": "คำร้องขอเลื่อนรับพระราชทานปริญญาบัตร", "url": "https://regis.kmutt.ac.th/service/form/RO-11.pdf"},
    {"id": "RO.12", "name": "คำร้องขอลาพักการศึกษา", "url": "https://regis.kmutt.ac.th/service/form/RO-12Updated.pdf"},
    {"id": "RO.13", "name": "คำร้องขอลาออก", "url": "https://regis.kmutt.ac.th/service/form/RO-13Updated.pdf"},
    {"id": "RO.14", "name": "คำร้องขอเปลี่ยนแปลงข้อมูลประวัติ", "url": "https://regis.kmutt.ac.th/service/form/RO-14.pdf"},
    {"id": "RO.15", "name": "คำร้องขอทำบัตรนักศึกษาใหม่", "url": "https://regis.kmutt.ac.th/service/form/RO-15_160718.pdf"},
    {"id": "RO.16", "name": "คำร้องขอลาป่วย/ลากิจ", "url": "https://regis.kmutt.ac.th/service/form/RO-16.pdf"},
    {"id": "RO.18", "name": "คำร้องลงทะเบียนต่ำกว่า/เกินกว่าหน่วยกิต", "url": "https://regis.kmutt.ac.th/service/form/RO-18Updated.pdf"},
    {"id": "RO.19", "name": "คำร้องลงทะเบียนวิชาสอบซ้อน", "url": "https://regis.kmutt.ac.th/service/form/RO-19.pdf"},
    {"id": "RO.20", "name": "คำร้องลงทะเบียนวิชานอกหลักสูตร", "url": "https://regis.kmutt.ac.th/service/form/RO-20.pdf"},
    {"id": "RO.21", "name": "คำร้องลงทะเบียนเรียนแบบบุคคลภายนอก", "url": "https://regis.kmutt.ac.th/service/form/RO-21.pdf"},
    {"id": "RO.22", "name": "คำร้องขอสมัครสอบโดยไม่ต้องเข้าเรียน / ผ่อนผัน", "url": "https://regis.kmutt.ac.th/service/form/RO-22.pdf"},
    {"id": "RO.23", "name": "คำร้องขอเปลี่ยน/เทียบรายวิชา", "url": "https://regis.kmutt.ac.th/service/form/RO-23.pdf"},
    {"id": "RO.25", "name": "ใบลงทะเบียนเรียน", "url": "https://regis.kmutt.ac.th/service/form/RO-25.pdf"},
    {"id": "RO.26", "name": "ใบเพิ่ม-ลด-ถอน-เปลี่ยนกลุ่ม", "url": "https://regis.kmutt.ac.th/service/form/RO-26Updated.pdf"},
]

# ================= GLOBAL VARIABLES =================
vector_store_instance = None
groq_client_instance = None

def get_rag_system():
    global vector_store_instance, groq_client_instance
    if vector_store_instance is None:
        print("⏳ Initializing AI Models...")
        embeddings = FastEmbedEmbeddings(model_name="BAAI/bge-small-en-v1.5")
        sparse_embeddings = FastEmbedSparse(model_name="Qdrant/bm25")
        client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
        vector_store_instance = QdrantVectorStore(
            client=client,
            collection_name=COLLECTION_NAME,
            embedding=embeddings,
            sparse_embedding=sparse_embeddings,
            retrieval_mode=RetrievalMode.HYBRID,
        )
        groq_client_instance = Groq(api_key=GROQ_API_KEY)
        print("✅ Models Ready!")
    return vector_store_instance, groq_client_instance

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    message: str
    history: List[ChatMessage] = Field(default_factory=list)

# ================= PROMPT (เน้น Pure RAG + Drafting) =================
SYSTEM_PROMPT = '''
คุณคือ "น้องผู้ช่วย มจธ." ผู้ช่วยด้านคำร้องและเอกสารทะเบียนนักศึกษา

กฎสำคัญ:
- ตอบจากข้อมูลใน Context (chunks จาก PDF และเอกสารจริง) เท่านั้น
- ห้ามใช้ความรู้ภายนอกหรือเดาขั้นตอนเอง
- ถ้าไม่มีข้อมูลใน Context ให้ตอบว่า "ไม่มีข้อมูลในเอกสารอ้างอิงค่ะ แนะนำให้ติดต่อสำนักงานทะเบียนโดยตรง"
- ตอบเป็นภาษาไทย สุภาพ กระชับ เข้าใจง่าย

ภารกิจหลัก:
1. ถ้าผู้ใช้ถามวิธีทำคำร้อง → ตอบขั้นตอน ช่องทาง ฟอร์ม ลิงก์ จาก Context
2. ถ้าผู้ใช้เล่าเหตุผลหรือขอความช่วยเหลือ → ช่วยร่างข้อความภาษาทางการ แล้วส่ง JSON ท้ายตอบ

รูปแบบการร่าง (Drafting):
- แปลงภาษาพูด → ภาษาทางการ (Rephrase & Expand)
- ตัวอย่าง:
  "ปวดหัวหนักมาก" → "เนื่องจากข้าพเจ้ามีอาการปวดศีรษะรุนแรงและเวียนศีรษะ จึงไม่สามารถเข้าเรียนได้..."
  "เรียนไม่ไหว" → "เนื่องจากข้าพเจ้ามีภาระการเรียนสูงและเกรงว่าจะส่งผลต่อผลการเรียน จึงขอถอนรายวิชา..."

รูปแบบ JSON (ส่งท้ายตอบเสมอเมื่อร่าง):
[[FORM_DATA: {
    "form_id": "RO.xx (ถ้ามีใน Context)",
    "name": "ชื่อจากผู้ใช้ (ถ้ามี)",
    "faculty": "คณะ (ถ้ามี)",
    "department": "สาขา (ถ้ามี)",
    "draft_subject": "หัวข้อเรื่องทางการ",
    "draft_reason": "เนื้อหาร่างภาษาทางการ"
}]]

ถ้าทักทาย ("สวัสดี") → ตอบมิตรภาพ เช่น "สวัสดีค่ะ! มีเรื่องคำร้องอะไรให้ช่วยไหมคะ?"
'''

def get_ai_response(rag_context: str, question: str, history: List[ChatMessage], groq_client: Groq):
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    for msg in history:
        messages.append({"role": msg.role, "content": msg.content})
    
    messages.append({
        "role": "user",
        "content": f"Context จากเอกสารจริง:\n{rag_context}\n\nคำถาม: {question}"
    })
    
    try:
        response = groq_client.chat.completions.create(
            model="llama-3.1-70b-versatile",  # แนะนำใช้ 70b เพื่อความแม่นยำ
            messages=messages,
            temperature=0.2,
            max_tokens=800
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"ขออภัยค่ะ เกิดข้อผิดพลาดในการเชื่อมต่อ AI ({str(e)})"

@app.get("/")
def read_root():
    return {"status": "Server is running 🚀"}

@app.post("/chat")
def chat_endpoint(req: ChatRequest):
    print(f"📩 Message: {req.message}")
    vector_store, groq_client = get_rag_system()
    
    try:
        context_text = ""
        sources = []
        
        # ✅ Pure RAG: ค้นหาเฉพาะจาก Vector DB (k=5)
        results = vector_store.similarity_search(req.message, k=5)
        
        for doc in results:
            context_text += f"{doc.page_content}\n\n"
            
            # ดึง URL จาก metadata หรือ content
            file_url = doc.metadata.get("file", "")
            display_name = os.path.basename(file_url) or "เอกสารอ้างอิง"
            doc_url = ""
            
            for item in FORM_MASTER_DATA:
                if item["url"] in file_url or item["id"] in doc.page_content:
                    doc_url = item["url"]
                    display_name = f"{item['id']} {item['name']}"
                    break
            
            if not doc_url:
                urls = re.findall(r'https?://[^\s\)]+', doc.page_content)
                if urls:
                    doc_url = urls[0]
            
            if doc_url and not any(s["url"] == doc_url for s in sources):
                sources.append({"doc": display_name, "page": 1, "url": doc_url})
        
        answer = get_ai_response(context_text, req.message, req.history, groq_client)
        
        return {"reply": answer, "sources": sources}
    
    except Exception as e:
        print(f"Error: {e}")
        return {"reply": "เกิดข้อผิดพลาดในระบบค่ะ", "sources": []}

# ================= GENERATE FORM =================
@app.post("/generate-form")
async def generate_form_endpoint(data: dict = Body(...)):
    form_type = (data.get("formType") or data.get("form_type") or data.get("form_id") or "").upper().replace("-", ".")
    if form_type not in TEMPLATE_MAP:
        form_type = "RO.01"  # fallback
    
    template_path = TEMPLATE_MAP.get(form_type)
    if not template_path or not os.path.exists(template_path):
        raise HTTPException(status_code=500, detail="ไม่พบไฟล์ template")
    
    try:
        doc = DocxTemplate(template_path)
        context = {
            "student_id": data.get("studentId") or data.get("student_id") or ".........",
            "student_name": data.get("name") or "....................................",
            "faculty": data.get("faculty") or "....................",
            "department": data.get("department") or "....................",
            "year": data.get("year") or "...",
            "semester": "2/2567",
            "phone": data.get("phone") or data.get("student_tel") or "....................",
            "reason": data.get("draft_reason") or "",
            "request_subject": data.get("draft_subject") or "",
            **data
        }
        doc.render(context)
        file_stream = BytesIO()
        doc.save(file_stream)
        file_stream.seek(0)
        
        filename = f"Filled_{form_type}_{context['student_id'] or 'Unknown'}.docx"
        return StreamingResponse(
            file_stream,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
