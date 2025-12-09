from fastapi import FastAPI, HTTPException, Body
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from qdrant_client import QdrantClient
from langchain_qdrant import QdrantVectorStore, FastEmbedSparse, RetrievalMode
from langchain_community.embeddings.fastembed import FastEmbedEmbeddings
from groq import Groq
from dotenv import load_dotenv
from docxtpl import DocxTemplate
from io import BytesIO
import os
import re
import uvicorn
import json

load_dotenv()

# ================= CONFIGURATION =================
QDRANT_URL = os.environ.get("QDRANT_URL")
QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
COLLECTION_NAME = "demo_collection_railway_v2"

# 📂 ตั้งค่า Template (ต้องสร้างโฟลเดอร์ templates และใส่ไฟล์ .docx ไว้ข้างใน)
TEMPLATE_DIR = "templates"
TEMPLATE_MAP = {
    "RO.01": os.path.join(TEMPLATE_DIR, "RO-01_General_Request.docx"),
    "RO.03": os.path.join(TEMPLATE_DIR, "RO-03_Guardian.docx"),
    "RO.12": os.path.join(TEMPLATE_DIR, "RO-12_Withdrawal.docx"), # (เดาชื่อจากรูป ถ้าไม่ใช่ให้แก้ตามจริง)
    "RO.13": os.path.join(TEMPLATE_DIR, "RO-13_Resignation.docx"),
    "RO.16": os.path.join(TEMPLATE_DIR, "RO-16_Sick_Leave.docx"),
}

# ✅ 1. ฐานข้อมูลฟอร์มฉบับสมบูรณ์ (Master Data)
# รวมรหัส, ชื่อไทย, และลิงก์ไว้ในที่เดียว เพื่อง่ายต่อการจัดการ
FORM_MASTER_DATA = [
    {
        "id": "RO.01", 
        "name": "คำร้องทั่วไป (General Request)", 
        "url": "https://regis.kmutt.ac.th/service/form/RO-01.pdf",
        "keywords": ["คำร้องทั่วไป", "ro01", "ro.01", "general", "อื่นๆ", "เรื่องทั่วไป", "สทน.01"]
    },
    {
        "id": "RO.03", 
        "name": "หนังสือรับรองของผู้ปกครอง", 
        "url": "https://regis.kmutt.ac.th/service/form/RO-03.pdf",
        "keywords": ["ผู้ปกครอง", "ro03", "ro.03", "หนังสือรับรอง", "ยินยอม", "parent", "สทน.03"]
    },
    {
        "id": "RO.04", 
        "name": "ใบมอบฉันทะ", 
        "url": "https://regis.kmutt.ac.th/service/form/RO-04.pdf",
        "keywords": ["มอบฉันทะ", "ro04", "ro.04", "แทน", "คนอื่นรับแทน", "authorization", "สทน.04"]
    },
    {
        "id": "RO.08", 
        "name": "คำร้องขอคืนเงินค่าลงทะเบียน", 
        "url": "https://regis.kmutt.ac.th/service/form/RO-08.pdf",
        "keywords": ["คืนเงิน", "ro08", "ro.08", "refund", "ค่าลงทะเบียน", "จ่ายเกิน", "ขอคืนเงิน", "สทน.08"]
    },
    {
        "id": "กค.18", 
        "name": "ใบแจ้งความจำนงโอนเงิน", 
        "url": "https://regis.kmutt.ac.th/service/form/18.pdf",
        "keywords": ["กค18", "กค.18", "โอนเงินเข้าบัญชี", "รับเงินโอน"]
    },
    {
        "id": "RO.11", 
        "name": "คำร้องขอเลื่อนรับพระราชทานปริญญาบัตร", 
        "url": "https://regis.kmutt.ac.th/service/form/RO-11.pdf",
        "keywords": ["รับปริญญา", "ro11", "ro.11", "เลื่อนรับ", "ไม่รับปริญญา", "สทน.11"]
    },
    {
        "id": "RO.12", 
        "name": "คำร้องขอลาพักการศึกษา", 
        "url": "https://regis.kmutt.ac.th/service/form/RO-12Updated.pdf",
        "keywords": ["ลาพัก", "ro12", "ro.12", "ดรอปเรียน", "drop", "พักการเรียน", "รักษาสถานภาพ", "สทน.12"]
    },
    {
        "id": "RO.13", 
        "name": "คำร้องขอลาออก", 
        "url": "https://regis.kmutt.ac.th/service/form/RO-13Updated.pdf",
        "keywords": ["ลาออก", "ro13", "ro.13", "resignation", "ออก", "quit", "สทน.13"]
    },
    {
        "id": "RO.14", 
        "name": "คำร้องขอเปลี่ยนแปลงข้อมูลประวัติ", 
        "url": "https://regis.kmutt.ac.th/service/form/RO-14.pdf",
        "keywords": ["เปลี่ยนชื่อ", "ro14", "ro.14", "เปลี่ยนนามสกุล", "แก้ประวัติ", "ที่อยู่ผิด", "คำนำหน้า", "สทน.14"]
    },
    {
        "id": "RO.15", 
        "name": "คำร้องขอทำบัตรนักศึกษาใหม่", 
        "url": "https://regis.kmutt.ac.th/service/form/RO-15_160718.pdf",
        "keywords": ["บัตรหาย", "ro15", "ro.15", "บัตรนักศึกษา", "ทำบัตรใหม่", "บัตรชำรุด", "สทน.15"]
    },
    {
        "id": "RO.16", 
        "name": "คำร้องขอลาป่วย/ลากิจ", 
        "url": "https://regis.kmutt.ac.th/service/form/RO-16.pdf",
        "keywords": ["ลาป่วย", "ro16", "ro.16", "ลากิจ", "ป่วย", "ใบรับรองแพทย์", "หยุดเรียน", "sick", "สทน.16"]
    },
    {
        "id": "RO.18", 
        "name": "คำร้องลงทะเบียนต่ำกว่า/เกินกว่าหน่วยกิต", 
        "url": "https://regis.kmutt.ac.th/service/form/RO-18Updated.pdf",
        "keywords": ["หน่วยกิตเกิน", "ro18", "ro.18", "หน่วยกิตต่ำ", "ลงเกิน", "ลงน้อย", "credits", "สทน.18"]
    },
    {
        "id": "RO.19", 
        "name": "คำร้องลงทะเบียนวิชาสอบซ้อน", 
        "url": "https://regis.kmutt.ac.th/service/form/RO-19.pdf",
        "keywords": ["สอบซ้อน", "ro19", "ro.19", "เวลาสอบชน", "exam conflict", "สทน.19"]
    },
    {
        "id": "RO.20", 
        "name": "คำร้องลงทะเบียนวิชานอกหลักสูตร", 
        "url": "https://regis.kmutt.ac.th/service/form/RO-20.pdf",
        "keywords": ["นอกหลักสูตร", "ro20", "ro.20", "วิชาเลือกเสรี", "free elective", "สทน.20"]
    },
    {
        "id": "RO.21", 
        "name": "คำร้องลงทะเบียนเรียนแบบบุคคลภายนอก", 
        "url": "https://regis.kmutt.ac.th/service/form/RO-21.pdf",
        "keywords": ["บุคคลภายนอก", "ro21", "ro.21", "visitor", "คนนอก", "สทน.21"]
    },
    {
        "id": "RO.22", 
        "name": "คำร้องขอสมัครสอบโดยไม่ต้องเข้าเรียน / ผ่อนผัน", 
        "url": "https://regis.kmutt.ac.th/service/form/RO-22.pdf",
        "keywords": ["ขาดเรียน", "ro22", "ro.22", "ผ่อนผัน", "ไม่ได้เข้าเรียน", "สมัครสอบ", "สทน.22"]
    },
    {
        "id": "RO.23", 
        "name": "คำร้องขอเปลี่ยน/เทียบรายวิชา", 
        "url": "https://regis.kmutt.ac.th/service/form/RO-23.pdf",
        "keywords": ["เทียบวิชา", "ro23", "ro.23", "เปลี่ยนวิชา", "transfer", "เทียบโอน", "สทน.23"]
    },
    {
        "id": "RO.25", 
        "name": "ใบลงทะเบียนเรียน", 
        "url": "https://regis.kmutt.ac.th/service/form/RO-25.pdf",
        "keywords": ["ใบลงทะเบียน", "ro25", "ro.25", "register", "regis", "สทน.25"]  
    },
    {
        "id": "RO.26", 
        "name": "ใบเพิ่ม-ลด-ถอน-เปลี่ยนกลุ่ม", 
        "url": "https://regis.kmutt.ac.th/service/form/RO-26Updated.pdf",
        "keywords": ["เพิ่มวิชา", "ro26", "ro.26", "ถอนวิชา", "เปลี่ยนเซค", "เปลี่ยน sec", "add/drop", "ลดวิชา", "ถอน w", "ติด w", "สทน.26"]
    },
]

# ✅ 2. สร้างตัวแปรช่วยค้นหา (Lookup & Prompt Generation)
FORM_DB = {}
FORM_LIST_TEXT = "" # ตัวแปรนี้จะถูกส่งให้ AI อ่านเป็น "โพย"

for item in FORM_MASTER_DATA:
    # สร้าง Dictionary สำหรับค้นหา URL เร็วๆ
    FORM_DB[item["id"]] = item["url"]      # ค้นด้วยรหัส (เช่น "RO.01")
    FORM_DB[item["name"]] = item["url"]    # ค้นด้วยชื่อ (เช่น "คำร้องทั่วไป")
    
    # เพิ่มรูปแบบย่อยๆ เผื่อ AI หรือ User พิมพ์ผิด
    FORM_DB[item["id"].replace(".", "")] = item["url"]   # "RO01"
    FORM_DB[item["id"].replace(".", ". ")] = item["url"] # "RO. 01"
    
    # สร้างข้อความสำหรับใส่ใน System Prompt
    FORM_LIST_TEXT += f"- {item['name']} ใช้ฟอร์มรหัส: {item['id']}\n"

    if "keywords" in item:
        for kw in item["keywords"]:
            FORM_DB[kw] = item["url"]

# ================= GLOBAL VARIABLES (LAZY LOAD) =================
# We declare them as None so they don't take up memory at startup
vector_store_instance = None
groq_client_instance = None

def get_rag_system():
    """
    This function loads the models ONLY when they are needed.
    It prevents the server from crashing during startup.
    """
    global vector_store_instance, groq_client_instance
    
    if vector_store_instance is None:
        print("⏳ Lazy Loading: Initializing AI Models...")
        
        # 1. Setup Embeddings
        embeddings = FastEmbedEmbeddings(model_name="BAAI/bge-small-en-v1.5")
        sparse_embeddings = FastEmbedSparse(model_name="Qdrant/bm25")

        # 2. Connect Qdrant
        client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)

        # 3. Setup Vector Store
        vector_store_instance = QdrantVectorStore(
            client=client,
            collection_name=COLLECTION_NAME,
            embedding=embeddings,
            sparse_embedding=sparse_embeddings,
            retrieval_mode=RetrievalMode.HYBRID,
            vector_name="dense_vector",
            sparse_vector_name="sparse_vector",
        )
        
        # 4. Setup Groq
        groq_client_instance = Groq(api_key=GROQ_API_KEY)
        
        print("✅ Lazy Loading: Models are ready!")
        
    return vector_store_instance, groq_client_instance

# ================= API SERVER =================
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

class UserRequest(BaseModel):
    message: str

def get_ai_response(context, question, groq_client):
    system_prompt =f'''
        คุณคือ "น้องผู้ช่วย มจธ." (KMUTT Assistant) ผู้เชี่ยวชาญด้านงานทะเบียนและเอกสารคำร้อง
        หน้าที่ของคุณคือ: ให้คำแนะนำที่ถูกต้อง กระชับ และเป็นมิตรกับนักศึกษา (เหมือนรุ่นพี่แนะนำรุ่นน้อง)

        📚 **คลังข้อมูลรหัสเอกสารที่คุณต้องใช้ (Knowledge Base):**
        {FORM_LIST_TEXT}

        ⚡ **กฎการตอบคำถาม (Strict Rules):**
        1. **ห้ามมั่วรหัส:** ต้องตอบรหัสเอกสาร (RO.xx) ให้ตรงกับบริบทเท่านั้น ห้ามเดาเอง
        2. **จับคู่คำศัพท์ (Keyword Mapping):** นักศึกษาอาจใช้คำพูดทั่วไป ให้แปลงเป็นรหัสเอกสารดังนี้:
           - "ดรอป", "ถอนวิชา", "ติด W" -> คือเรื่องการถอนรายวิชา (ใช้ RO.26 หรือระบบ New ACIS)
           - "พักการเรียน", "ดรอปเรียน (ทั้งเทอม)" -> คือการลาพักการศึกษา (ใช้ RO.12)
           - "ป่วย", "ไม่สบาย", "ลากิจ", "หยุดเรียน" -> ใช้ RO.16
           - "ลงเกิน", "หน่วยกิตไม่พอ", "ลงหน่วยกิตต่ำ" -> ใช้ RO.18
           - "สอบชน", "เวลาสอบทับกัน" -> ใช้ RO.19
           - "คืนเงิน", "จ่ายเงินเกิน" -> ใช้ RO.08 คู่กับ กค.18
        3. **ถ้าไม่แน่ใจ:** ให้ตอบว่า "ขออภัยครับ ข้อมูลไม่ชัดเจน แนะนำให้ติดต่อสำนักงานทะเบียนโดยตรง" (อย่าแต่งเรื่องเอง)

        ลายละเอียดที่สำคัญ:
        **ถ้าผู้ใช้ถามเรื่อง "กค.18", "RO.08" หรือ "คืนเงิน":**
        - ต้องระบุให้ชัดเจนว่า ต้องใช้ "กค.18" ร่วมกับ "RO.08" ในการขอคืนเงินค่าลงทะเบียน
        
        📝 **รูปแบบการตอบ (Response Format):**
        - เริ่มต้นด้วยคำตอบสั้นๆ ว่าต้องทำอะไร
        - บอกขั้นตอนเป็นข้อๆ 1, 2, 3
        - **สำคัญ:** ต้องปิดท้ายด้วยชื่อฟอร์มและลิงก์ดาวน์โหลดเสมอ (ถ้ามีในบริบท)

        ตัวอย่างการตอบที่ดี:
        "สำหรับการขอลาพักการศึกษา (Drop ทั้งเทอม) ต้องทำดังนี้ครับ:
        1. ยื่นเรื่องผ่านระบบ New ACIS
        2. ใช้แบบฟอร์ม **สทน. 12 (RO.12)** ประกอบการยื่น
        ⬇️ ดาวน์โหลดที่นี่: https://regis.kmutt.ac.th/service/form/RO-12Updated.pdf"

        ✨ ฟีเจอร์พิเศษ:
        1. หากผู้ใช้ระบุข้อมูลส่วนตัว ให้ดึงออกมาใส่ JSON
        2. ช่วย "ร่างข้อความ" สำหรับกรอกในใบคำร้อง (ช่อง draft_reason) ด้วยภาษาทางการ
        3. **สำคัญ:** ช่อง "form_id" ต้องใส่รหัสเอกสาร (เช่น RO.16) เท่านั้น

        รูปแบบ Tag JSON (บรรทัดสุดท้าย):
        [[FORM_DATA: {{
            "student_id": "เลขประจำตัวนักศึกษา... เช่น 68070501044", 
            "name": "ชื่อ-นามสกุล... เช่น นายสมชาย ใจดี", 
            "faculty": "คณะ... เช่น วิศวกรรมศาสตร์", 
            "year": "ปีการศึกษา... เช่น 4", 
            "form_id": "ใส่รหัสตรงนี้ (เช่น RO.16)",
            "draft_reason": "ข้อความร่างภาษาทางการ...",
            "draft_subject": "เรื่อง..."
        }}]]

    '''
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Context:\n{context}\n\nQuestion:\n{question}"}
    ]
    
    try:
        response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=messages,
            temperature=0.1
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"AI Error: {str(e)}"

@app.get("/")
def read_root():
    return {"status": "Server is running 🚀"}

@app.post("/chat")
def chat_endpoint(req: UserRequest):
    print(f"📩 คำถาม: {req.message}")
    vector_store, groq_client = get_rag_system()
    user_query = req.message.lower()
    
    try:
        context_text = ""
        sources = []
        
        # ---------------------------------------------------------
        # ✅ ขั้นตอนที่ 1: "ค้นหาจาก Keywords" (แม่นยำ 100%)
        # ---------------------------------------------------------
        found_in_master = False
        
        for item in FORM_MASTER_DATA:
            # วนลูปเช็ค keyword ในลิสต์ของแต่ละฟอร์ม
            for kw in item["keywords"]:
                if kw in user_query: # ถ้าเจอคำนี้ในคำถาม (เช่น "ดรอป")
                    found_in_master = True
                    print(f"🎯 เจอ Keyword '{kw}' -> ตรงกับฟอร์ม: {item['id']}")
                    
                    # บังคับยัดข้อมูลที่ถูกต้องใส่ Context ให้ AI เลย
                    context_text += f"\n[ข้อมูลสำคัญจากระบบ]: ผู้ใช้กำลังถามถึง '{item['name']}' ซึ่งตรงกับคีย์เวิร์ด '{kw}' รหัสเอกสารคือ '{item['id']}'. ลิงก์ดาวน์โหลดคือ {item['url']}\n"
                    
                    # เพิ่มปุ่มดาวน์โหลดทันที
                    if not any(s['url'] == item["url"] for s in sources):
                        sources.append({
                            "doc": f"{item['id']} {item['name']}",
                            "page": 1,
                            "url": item["url"]
                        })
                    break # เจอแล้วหยุดเช็คฟอร์มนี้ ไปฟอร์มอื่นต่อ (เผื่อถามหลายเรื่อง)

        # ---------------------------------------------------------
        # ✅ ขั้นตอนที่ 2: ค้นหา Vector DB (Qdrant) เพิ่มเติม
        # ---------------------------------------------------------
        # ถ้าเจอ Keyword แล้ว ค้นน้อยลง (k=1)
        k_val = 1 if found_in_master else 3
        search_results = vector_store.similarity_search(req.message, k=k_val)
        
        for doc in search_results:
            context_text += f"{doc.page_content}\n\n"
            
            # (ส่วนหาลิงก์จาก PDF เหมือนเดิม เผื่อกรณี Keyword ไม่ครอบคลุม)
            file_path = doc.metadata.get("file", "เอกสารทั่วไป")
            doc_url = ""
            display_name = file_path.split("/")[-1]

            # พยายาม Match ลิงก์จาก FORM_MASTER_DATA
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
                    sources.append({
                        "doc": display_name,
                        "page": 1,
                        "url": doc_url
                    })

        answer = get_ai_response(context_text, req.message, groq_client)
        return { "reply": answer, "sources": sources }
    
    except Exception as e:
        print(f"Error: {e}")
        return { "reply": "เกิดข้อผิดพลาดในระบบ", "sources": [] }

# ✅ API ใหม่สำหรับสร้างเอกสาร Word (Fill Form)
@app.post("/generate-form")
async def generate_form_endpoint(data: dict = Body(...)):
    """
    รับข้อมูล JSON จาก Frontend แล้วสร้างไฟล์ Word กลับไป
    """
    print(f"📝 กำลังสร้างฟอร์ม: {data}")
    
    # 1. เช็คว่าขอฟอร์มไหน
    form_type = data.get("formType") or data.get("form_type") or ""
    
    # ถ้าไม่มีรหัส ให้ลองหาจากชื่อ
    if form_type not in TEMPLATE_MAP:
        # ลองแปลง RO.16 เป็น RO-16 หรือหา partial match
        print(f"⚠️ หา Template {form_type} ไม่เจอใน MAP")
        # Fallback หรือแจ้ง Error
        raise HTTPException(status_code=404, detail=f"ไม่พบแม่แบบเอกสารสำหรับ {form_type}")

    template_path = TEMPLATE_MAP[form_type]
    
    # เช็คว่ามีไฟล์จริงไหม
    if not os.path.exists(template_path):
        raise HTTPException(status_code=500, detail=f"Server Missing File: {template_path}")

    try:
        # 2. โหลด Template
        doc = DocxTemplate(template_path)
        
        # 3. เตรียมข้อมูล (Context)
        # Frontend ส่งมา key เป็น studentId แต่ Template อาจใช้ student_id
        # เราแปลงให้ครบทุกแบบเพื่อความชัวร์
        context = {
            "student_id": data.get("studentId"),
            "student_name": data.get("name"),
            "faculty": data.get("faculty"),
            "year": data.get("year"),
            "semester": "2/2567", # ตัวอย่างค่า Default
            "phone": data.get("student_tel") or data.get("phone_mobile"),
            # เอาทุกอย่างที่ Frontend ส่งมา ใส่เข้าไปใน Context ด้วย
            **data 
        }
        
        # 4. Render
        doc.render(context)
        
        # 5. Save ลง RAM (BytesIO)
        file_stream = BytesIO()
        doc.save(file_stream)
        file_stream.seek(0)
        
        filename = f"Filled_{form_type}_{context['student_id']}.docx"
        
        # 6. ส่งไฟล์กลับ
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