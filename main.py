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

# 📂 ตั้งค่า Template
TEMPLATE_DIR = "templates"
TEMPLATE_MAP = {
    "RO.01": os.path.join(TEMPLATE_DIR, "RO-01_General_Request.docx"),
    "RO.03": os.path.join(TEMPLATE_DIR, "RO-03_Guardian.docx"),
    "RO.12": os.path.join(TEMPLATE_DIR, "RO-12_Withdrawal.docx"),
    "RO.13": os.path.join(TEMPLATE_DIR, "RO-13_Resignation.docx"),
    "RO.16": os.path.join(TEMPLATE_DIR, "RO-16_Sick_Leave.docx"),
}

# ✅ 1. ฐานข้อมูลฟอร์มฉบับสมบูรณ์ (ใช้ของคุณ - ครอบคลุมกว่า)
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

FORM_DB = {}
FORM_LIST_TEXT = "" 
for item in FORM_MASTER_DATA:
    FORM_DB[item["id"]] = item["url"]
    FORM_DB[item["name"]] = item["url"]
    FORM_LIST_TEXT += f"- {item['name']} ใช้ฟอร์มรหัส: {item['id']}\n"
    if "keywords" in item:
        for kw in item["keywords"]:
            FORM_DB[kw] = item["url"]

# ================= GLOBAL VARIABLES =================
vector_store_instance = None
groq_client_instance = None

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
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

class UserRequest(BaseModel):
    message: str

# 🧠 PROMPT ENGINEERING: The Smart Consultant (ผู้ช่วยที่ปรึกษา)
def get_ai_response(context, question, groq_client):
    system_prompt =f'''
       Role: คุณคือ "น้องผู้ช่วย มจธ." (KMUTT Assistant) ผู้เชี่ยวชาญด้านงานทะเบียนและที่ปรึกษาการเขียนคำร้อง
            Context: ข้อมูลอ้างอิงของคุณจำกัดอยู่เพียง: {FORM_LIST_TEXT} เท่านั้น
            
            Core Directives (กฎเหล็ก):
            Zero Hallucination: ห้ามตอบนอกเหนือจากเอกสารอ้างอิง หากไม่มีข้อมูลให้ตอบว่า "ไม่มีข้อมูลในเอกสาร"
            Intent & Disambiguation: หากคำถามกำกวม (เช่น "ลาพัก") ให้แยกตอบเป็นกรณี (Scenario-based) ห้ามสรุปเอาเอง
            Tone: ใช้ภาษาไทยที่สุภาพ เป็นทางการ เป็นมิตร และน่าเชื่อถือ
            Drafting: เมื่อผู้ใช้ต้องการร่างเอกสาร ต้องแปลงภาษาพูดเป็น "ภาษาเขียนทางการ" เสมอ
            JSON Output: ต้องส่ง [[FORM_DATA: {...}]] แนบท้ายเสมอเมื่อมีการร่างหรือแก้ไขเนื้อหา
            
            Workflow Logic (ขั้นตอนการคิดและตอบ):
            Phase 1: Information Retrieval (เมื่อผู้ใช้ถามข้อมูล/วิธีการ)
            วิเคราะห์: แยกแยะว่าเป็นระบบ Online (New ACIS) หรือ Paper-based
            ค้นหา: ดึงข้อมูลชื่อฟอร์ม (RO.xx), ผู้ลงนาม, และเงื่อนไข
            ตอบ: ใช้ Bullet Points
            สรุป: ชื่อกรณีที่เกี่ยวข้อง
            วิธีดำเนินการ: ชื่อฟอร์ม + ช่องทาง (Link/สถานที่)
            เงื่อนไข: เอกสารแนบ/ผู้มีอำนาจอนุมัติ
            Closing: จบด้วยการเสนอตัวเสมอ: "ต้องการให้ผมช่วยร่างข้อความในคำร้องนี้ให้ไหมครับ?"
            
            Phase 2: Drafting & Action (เมื่อผู้ใช้ขอให้ร่าง/ตกลง)
            Action: แปลงเหตุผลของผู้ใช้เป็นภาษาทางการ (Formal Thai)
            ตอบ:
                1.แสดงข้อความร่างที่แต่งให้
                2.แนบ JSON Data สำหรับนำไปใช้ในระบบ
            
            JSON Structure:
            
            [[FORM_DATA: {{
                "form_id": "RO.xx (ระบุรหัสถ้ามี)",
                "draft_subject": "หัวข้อเรื่องแบบทางการ",
                "draft_reason": "เนื้อหาความจำเป็นที่เรียบเรียงเป็นภาษาทางการ...",
                "student_id": "...", 
                "department": "..."
            }}]]
            
            
            Phase 3: Consultation (เมื่อผู้ใช้ถามแทรกขณะร่าง)
            Action: ตอบคำถามแทรกโดยอ้างอิง Context เดิม
            Consistency: ต้องแนบ [[FORM_DATA: ...]] (ข้อมูลชุดเดิม หรือชุดที่อัปเดตแล้ว) ท้ายคำตอบเสมอ เพื่อรักษา State ของแอปพลิเคชัน
            Example Scenarios:
            User: "ลาป่วยทำไง"
            AI: (แยกกรณี)
            กรณีลาไม่เกิน 15 วัน: ใช้ฟอร์ม RO.16 ยื่นต่ออาจารย์ที่ปรึกษา
            กรณีลาเกิน 15 วัน: ต้องได้รับอนุมัติจากคณบดี
            ต้องการให้ผมช่วยร่างคำร้องไหมครับ?
            User: "ร่างให้หน่อย ปวดท้องหนักมาก นอนโรงพยาบาล"
            AI: ขอให้หายไวๆ นะครับ ผมร่างข้อความทางการให้แล้วครับ:
            📝 ข้อความร่าง: "เนื่องจากข้าพเจ้ามีอาการเจ็บป่วยฉุกเฉิน (ปวดท้องรุนแรง) และแพทย์ลงความเห็นให้พักรักษาตัว..."
            [[FORM_DATA: {{"form_id": "RO.16", "draft_subject": "ขอลาหยุดเรียนเนื่องจากอาการเจ็บป่วย", "draft_reason": "เนื่องจากข้าพเจ้ามีอาการ..."}}]]

        ✨ **รูปแบบการส่งข้อมูล (JSON):**
        [[FORM_DATA: {{
            "student_id": "รหัสนักศึกษา เช่น 6807050xxxx", 
            "name": "ชื่อ เช่น นายสมจิตร ใจดี", 
            "faculty": "คณะ เช่น วิศวกรรมศาสตร์",
            "department": "สาขา เช่น วิสวกรรมคอมพิวเตอร์", 
            "year": "ปีการศึกษา เช่น ปี 1", 
            "form_id": "RO.xx",
            "draft_subject": "หัวข้อเรื่อง",
            "draft_reason": "ข้อความร่างภาษาทางการ..."
        }}]]

        ข้อควรระวัง:ใช้ key "department"
        Contact Info: หากเอกสารระบุเบอร์โทรหรือหน่วยงาน ให้ใส่ไว้ท้ายสุดของคำตอบเสมอ
    '''
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Context (จากระเบียบการ):\n{context}\n\nUser Question:\n{question}"}
    ]
    
    try:
        response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=messages,
            temperature=0.2 # คุมให้ไม่เพ้อเจ้อ เน้นความแม่นยำของข้อมูล
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
        
        # 1. Keyword Search (แม่นยำเรื่องชื่อฟอร์ม)
        found_in_master = False
        for item in FORM_MASTER_DATA:
            for kw in item["keywords"]:
                if kw in user_query: 
                    found_in_master = True
                    context_text += f"\n[ข้อมูลสำคัญ]: ผู้ใช้ถามถึง '{item['name']}' ({item['id']}). ลิงก์: {item['url']}\n"
                    if not any(s['url'] == item["url"] for s in sources):
                        sources.append({"doc": f"{item['id']} {item['name']}", "page": 1, "url": item["url"]})
                    break 

        # 2. Vector Search (แม่นยำเรื่องระเบียบการ/วิธีการ)
        # ใช้ k=5 เพื่อกวาดข้อมูลระเบียบการมาตอบคำถาม Consultation ได้ครบถ้วน
        k_val = 5
        search_results = vector_store.similarity_search(req.message, k=k_val)
        
        for doc in search_results:
            context_text += f"{doc.page_content}\n\n"
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

        # 3. AI Processing
        answer = get_ai_response(context_text, req.message, groq_client)
        return { "reply": answer, "sources": sources }
    
    except Exception as e:
        print(f"Error: {e}")
        return { "reply": "เกิดข้อผิดพลาดในระบบ", "sources": [] }

# ✅ API สร้างเอกสาร
@app.post("/generate-form")
async def generate_form_endpoint(data: dict = Body(...)):
    print(f"📝 กำลังสร้างฟอร์ม: {data}")
    
    form_type = data.get("formType") or data.get("form_type") or ""
    if form_type not in TEMPLATE_MAP:
        raise HTTPException(status_code=404, detail=f"ไม่พบแม่แบบเอกสารสำหรับ {form_type}")

    template_path = TEMPLATE_MAP[form_type]
    if not os.path.exists(template_path):
        raise HTTPException(status_code=500, detail=f"Server Missing File: {template_path}")

    try:
        doc = DocxTemplate(template_path)
        
        context = {
            "student_id": data.get("studentId") or data.get("student_id"),
            "student_name": data.get("name"),
            "faculty": data.get("faculty"),
            "department": data.get("department"),
            "year": data.get("year"),
            "semester": "2/2567",
            "phone": data.get("student_tel") or data.get("phone_mobile"),
            "reason": data.get("draft_reason"),
            "request_subject": data.get("draft_subject"),
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
