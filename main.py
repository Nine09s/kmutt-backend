from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from qdrant_client import QdrantClient
from langchain_qdrant import QdrantVectorStore, FastEmbedSparse, RetrievalMode
from langchain_community.embeddings.fastembed import FastEmbedEmbeddings
from groq import Groq
from dotenv import load_dotenv
import os
import re
import uvicorn

load_dotenv()  # Load environment variables from .env file

# ================= CONFIGURATION =================
# 💡 แนะนำ: ในระยะยาวควรย้ายไปเก็บใน .env
QDRANT_URL = "https://214fea29-22e9-4e38-902c-8fd9db5abff9.europe-west3-0.gcp.cloud.qdrant.io:6333" 
QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
COLLECTION_NAME = "demo_collection_HYBRID" 

FORM_DB = {
    # กลุ่มคำร้องทั่วไป / ทะเบียนประวัติ
    "RO.01": "https://regis.kmutt.ac.th/service/form/RO-01.pdf", # คำร้องทั่วไป
    "สทน. 01": "https://regis.kmutt.ac.th/service/form/RO-01.pdf",

    "RO.03": "https://regis.kmutt.ac.th/service/form/RO-03.pdf", # หนังสือรับรองของผู้ปกครอง
    "สทน. 03": "https://regis.kmutt.ac.th/service/form/RO-03.pdf",

    "RO.04": "https://regis.kmutt.ac.th/service/form/RO-04.pdf", # ใบมอบฉันทะ
    "สทน. 04": "https://regis.kmutt.ac.th/service/form/RO-04.pdf",
    
    "RO.08": "https://regis.kmutt.ac.th/service/form/RO-08.pdf", # ใบแจ้งความจำนงโอนเงินเข้าบัญชีเงินฝาก
    "สทน.08": "https://regis.kmutt.ac.th/service/form/RO-08.pdf",
    "สทน. 08": "https://regis.kmutt.ac.th/service/form/RO-08.pdf",

    "กค. 18": "https://regis.kmutt.ac.th/service/form/18.pdf", # ใบแจ้งความจำนงโอนเงินเข้าบัญชีเงินฝาก
    "กค.18": "https://regis.kmutt.ac.th/service/form/18.pdf",
    "แบบ กค.": "https://regis.kmutt.ac.th/service/form/18.pdf",

    "RO.11": "https://regis.kmutt.ac.th/service/form/RO-11.pdf", # คำร้องขอเลื่อนรับพระราชทานปริญญาบัตร
    "สทน. 11": "https://regis.kmutt.ac.th/service/form/RO-11.pdf",

    "RO.12": "https://regis.kmutt.ac.th/service/form/RO-12Updated.pdf", # คำร้องขอลาพักการศึกษา
    "สทน. 12": "https://regis.kmutt.ac.th/service/form/RO-12Updated.pdf",

    "RO.13": "https://regis.kmutt.ac.th/service/form/RO-13Updated.pdf", # คำร้องขอลาออก
    "สทน. 13": "https://regis.kmutt.ac.th/service/form/RO-13Updated.pdf",

    "RO.14": "https://regis.kmutt.ac.th/service/form/RO-14.pdf", # คำร้องขอเปลี่ยนแปลงข้อมูลในทะเบียนประวัติ
    "สทน. 14": "https://regis.kmutt.ac.th/service/form/RO-14.pdf",

    "RO.15": "https://regis.kmutt.ac.th/service/form/RO-15_160718.pdf", # คำร้องขอทำบัตรนักศึกษา มจธ.-ธนาคารกรุงเทพ
    "สทน. 15": "https://regis.kmutt.ac.th/service/form/RO-15_160718.pdf",

    "RO.16": "https://regis.kmutt.ac.th/service/form/RO-16.pdf", # คำร้องขอลาป่วย/ลากิจ
    "สทน. 16": "https://regis.kmutt.ac.th/service/form/RO-16.pdf",

    "RO.18": "https://regis.kmutt.ac.th/service/form/RO-18Updated.pdf", # คำร้องขอลงทะเบียนต่ำกว่า/เกินกว่าหน่วยกิตที่กำหนด
    "สทน.18": "https://regis.kmutt.ac.th/service/form/RO-18Updated.pdf",
    "สทน. 18": "https://regis.kmutt.ac.th/service/form/RO-18Updated.pdf",

    "RO.19": "https://regis.kmutt.ac.th/service/form/RO-19.pdf", # คำร้องขอลงทะเบียนต่ำกว่า/เกินกว่าหน่วยกิตที่กำหนด
    "สทน. 19": "https://regis.kmutt.ac.th/service/form/RO-19.pdf",

    "RO.20": "https://regis.kmutt.ac.th/service/form/RO-20.pdf", # คำร้องขอลงทะเบียนรายวิชานอกหลักสูตร
    "สทน. 20": "https://regis.kmutt.ac.th/service/form/RO-20.pdf",

    "RO.21": "https://regis.kmutt.ac.th/service/form/RO-21.pdf", # คำร้องขอลงทะเบียนเรียนแบบบุคคลภายนอก
    "สทน. 21": "https://regis.kmutt.ac.th/service/form/RO-21.pdf",

    "RO.22": "https://regis.kmutt.ac.th/service/form/RO-22.pdf", # คำร้องขอสมัครสอบโดยไม่ต้องเข้าเรียน
    "สทน. 22": "https://regis.kmutt.ac.th/service/form/RO-22.pdf",

    "RO.23": "https://regis.kmutt.ac.th/service/form/RO-23.pdf", # คำร้องขอเปลี่ยน/เทียบรายวิชาเรียน
    "สทน. 23": "https://regis.kmutt.ac.th/service/form/RO-23.pdf",

    "RO.25": "https://regis.kmutt.ac.th/service/form/RO-25.pdf", # ใบลงทะเบียนเรียน
    "สทน. 25": "https://regis.kmutt.ac.th/service/form/RO-25.pdf",

    "RO.26": "https://regis.kmutt.ac.th/service/form/RO-26Updated.pdf", # ใบลงทะเบียนเพิ่ม-ลด-ถอน-เปลี่ยนกลุ่มเรียน
    "สทน. 26": "https://regis.kmutt.ac.th/service/form/RO-26Updated.pdf",
}

# ================= SETUP RAG SYSTEM =================
print("⏳ กำลังโหลดโมเดล... (รอแป๊บ)")

# 1. Setup Embeddings
embeddings = FastEmbedEmbeddings(model_name="BAAI/bge-small-en-v1.5")
sparse_embeddings = FastEmbedSparse(model_name="Qdrant/bm25")

# 2. Connect Qdrant
client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)

# 3. Setup Vector Store
vector_store = QdrantVectorStore(
    client=client,
    collection_name=COLLECTION_NAME,
    embedding=embeddings,
    sparse_embedding=sparse_embeddings,
    retrieval_mode=RetrievalMode.HYBRID,
    vector_name="dense_vector",
    sparse_vector_name="sparse_vector",
)

# 4. Setup Groq
groq_client = Groq(api_key=GROQ_API_KEY)

print("✅ ระบบ RAG พร้อมใช้งานแล้ว!")

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

def get_ai_response(context, question):
    system_prompt ='''
        คุณคือผู้ช่วยอัจฉริยะด้านคำร้องและเอกสารของ มจธ. (KMUTT)
        ตอบให้กระชับ ชัดเจน เป็นขั้นตอน ใช้ภาษาไทยที่เป็นมิตรกับนักศึกษา
        ถ้ามีแบบฟอร์มหรือลิงก์ต้องใส่ให้ครบ

        รูปแบบการตอบที่ต้องการ:
        1. ตอบตรงประเด็นเลย (ไม่ต้องเกริ่นยาว)
        2. ใช้ bullet point หรือตัวเลข
        3. ถ้ามีแบบฟอร์ม → แนะนำชื่อฟอร์ม + ลิงก์
        4. ถ้ามีค่าธรรมเนียม → บอกชัดเจน
        5. ถ้ายื่นออนไลน์ได้ → บอกช่องทางก่อน

        ตัวอย่างคำตอบที่ดี:
        "ถอนวิชาแล้วเหลือ 4 หน่วยกิต (ป.ตรี) ต้องทำ 2 ขั้นตอนครับ
        1. ยื่นถอนวิชาใน New ACIS ก่อน
        2. ยื่นคำร้องเพิ่มเติม สทน.18 (RO.18) แบบไฟล์
        → ดาวน์โหลดที่นี่: https://regis.kmutt.ac.th/service/form/RO-18Updated.pdf"

    🚨 กฎการแยกแยะเอกสาร (สำคัญมาก):
    1. "สทน. 18" (RO.18) คือเรื่อง "หน่วยกิต" (ลงทะเบียนต่ำกว่า/เกินเกณฑ์) 
       ❌ ห้ามสับสนกับ กค.18 หรือ สทน.18 เด็ดขาด
    
    2. "สทน. 08" (RO.08) คือเรื่อง "ขอคืนเงินค่าลงทะเบียน"
       ✅ ต้องใช้คู่กับ "แบบ กค. 18" (ใบแจ้งความจำนงโอนเงิน) เสมอ
    
    3. ถ้าผู้ใช้ถามเรื่อง "กค. 18" ให้บอกว่าคือเอกสารการเงิน ใช้แนบพร้อม สทน. 08

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
    user_query = req.message.lower()
    
    try:
        # 1. ค้นหาข้อมูล (Retrieve)
        search_results = vector_store.similarity_search(req.message, k=3)
        
        # 2. เตรียม Context และดึง Sources (ส่วนที่เพิ่มมาใหม่) ✨
        context_text = ""
        sources = []
        injected_docs = [] # เก็บรายการที่ระบบแอบยัดใส่ให้
        
        # กรณี: ถามเรื่องคืนเงิน หรือ สทน.08 หรือ กค.18
        if any(x in user_query for x in ["08", "คืนเงิน", "กค.18", "กค. 18"]):
            injected_docs.append({
                "name": "แบบฟอร์ม สทน. 08 (ขอคืนเงิน)",
                "url": FORM_DB["RO.08"]
            })
            injected_docs.append({
                "name": "แบบ กค. 18 (ใบแจ้งโอนเงิน - ใช้คู่ สทน.08)",
                "url": FORM_DB["กค.18"]
            })
            
        # กรณี: ถามเรื่องหน่วยกิต หรือ สทน.18
        elif any(x in user_query for x in ["18", "หน่วยกิต", "ลงทะเบียนเกิน", "ลงทะเบียนต่ำ"]):
            # ต้องระวังไม่ให้ชนกับ กค.18
            if "กค" not in user_query:
                injected_docs.append({
                    "name": "แบบฟอร์ม สทน. 18 (เรื่องหน่วยกิต)",
                    "url": FORM_DB["RO.18"]
                })
        
        for doc in search_results:
            # รวมเนื้อหาเพื่อส่งให้ AI
            context_text += f"{doc.page_content}\n\n"
            
            # ดึงชื่อไฟล์และเลขหน้าจาก Metadata (เพื่อส่งกลับไปหน้าเว็บ)
            # .get("key", default_value) ป้องกัน error ถ้าไม่มีข้อมูล
            file_path = doc.metadata.get("file", "เอกสารทั่วไป")
            base_file_name = file_path.split("/")[-1] if "/" in file_path else file_path
            page_num = doc.metadata.get("page", 0) + 1

            if injected_docs:
                context_text += "\n--- ข้อมูลเพิ่มเติมจากระบบ ---\n"
                for item in injected_docs:
                    context_text += f"กรุณาแนะนำผู้ใช้ให้ดาวน์โหลด: {item['name']} ได้ที่ลิงก์ {item['url']}\n"
                    sources.append({
                        "doc": item['name'],
                        "page": 1,
                        "url": item['url']
                    })
                
            display_name = base_file_name
            doc_url = ""
    
            # ---------------------------------------------------------
            # 🚀 ตรวจจับชื่อฟอร์ม (สแกนหาจาก DB ที่เราเตรียมไว้)
            # ---------------------------------------------------------
            found_form = False
            for keyword, url in FORM_DB.items():
                # ใช้ .lower() เพื่อให้ RO.16 กับ ro.16 เจอเหมือนกัน
                if keyword.lower() in doc.page_content.lower() or keyword in base_file_name:
                    doc_url = url
                    display_name = f"ดาวน์โหลดแบบฟอร์ม {keyword}"
                    found_form = True
                    break
    
            # ถ้าไม่เจอ form ใน DB ให้ลองสกัดลิงก์จากเนื้อหา
            if not found_form:
                found_urls = re.findall(r'(https?://[^\s\)]+)', doc.page_content)
                if found_urls:
                    doc_url = found_urls[0]
            
            # 🔥 ยัดลิงก์ใส่ Context ให้ AI เห็นด้วย (AI จะได้พิมพ์ออกมาได้)
            content_with_link = doc.page_content
            if doc_url:
                content_with_link += f"\n[ข้อมูลเพิ่มเติม: แบบฟอร์มนี้สามารถดาวน์โหลดได้ที่ลิงก์นี้: {doc_url}]\n"
            
            context_text += f"{content_with_link}\n\n"
    
            # สร้าง Sources ส่งกลับไปหน้าเว็บ
            if doc_url: # ส่งเฉพาะอันที่มีประโยชน์
                sources.append({
                    "doc": display_name,
                    "page": page_num,
                    "url": doc_url
                })
    
        # ลบแหล่งที่ซ้ำกัน
        unique_sources = []
        seen_urls = set()
        for s in sources:
            if s['url'] not in seen_urls:
                unique_sources.append(s)
                seen_urls.add(s['url'])
    
        answer = get_ai_response(context_text, req.message)
        
        return { "reply": answer, "sources": unique_sources }
    
    except Exception as e:
        print(f"Error: {e}")
        return { "reply": "เกิดข้อผิดพลาดในระบบ", "sources": [] }
    
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)