import os
from dotenv import load_dotenv
from qdrant_client import QdrantClient, models
from langchain_qdrant import QdrantVectorStore, FastEmbedSparse, RetrievalMode
from langchain_community.embeddings.fastembed import FastEmbedEmbeddings
from langchain_community.document_loaders import PyMuPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

# Load keys
load_dotenv()

# --- CONFIGURATION (MUST MATCH MAIN.PY) ---
COLLECTION_NAME = "demo_collection_railway_v2"  # <--- Make sure this matches main.py!
QDRANT_URL = os.environ.get("QDRANT_URL")
QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY")

# URL list from your project
PDF_URLS = [
    "https://regis.kmutt.ac.th/service/form/RO-01.pdf", # RO.01
    "https://regis.kmutt.ac.th/service/form/RO-03.pdf", # RO.03
    "https://regis.kmutt.ac.th/service/form/RO-04.pdf", # RO.04
    "https://regis.kmutt.ac.th/service/form/RO-08.pdf", # RO.08
    "https://regis.kmutt.ac.th/service/form/18.pdf",    # กค.18
    "https://regis.kmutt.ac.th/service/form/RO-11.pdf", # RO.11
    "https://regis.kmutt.ac.th/service/form/RO-12Updated.pdf", # RO.12
    "https://regis.kmutt.ac.th/service/form/RO-13Updated.pdf", # RO.13
    "https://regis.kmutt.ac.th/service/form/RO-14.pdf", # RO.14
    "https://regis.kmutt.ac.th/service/form/RO-15_160718.pdf", # RO.15
    "https://regis.kmutt.ac.th/service/form/RO-16.pdf", # RO.16
    "https://regis.kmutt.ac.th/service/form/RO-18Updated.pdf", # RO.18
    "https://regis.kmutt.ac.th/service/form/RO-19.pdf", # RO.19
    "https://regis.kmutt.ac.th/service/form/RO-20.pdf", # RO.20
    "https://regis.kmutt.ac.th/service/form/RO-21.pdf", # RO.21
    "https://regis.kmutt.ac.th/service/form/RO-22.pdf", # RO.22
    "https://regis.kmutt.ac.th/service/form/RO-23.pdf", # RO.23
    "https://regis.kmutt.ac.th/service/form/RO-25.pdf", # RO.25
    "https://regis.kmutt.ac.th/service/form/RO-26Updated.pdf", # RO.26
]

def main():
    print(f"🚀 Connecting to Qdrant: {QDRANT_URL}...")
    client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)

    # 1. Check/Create Collection
    if not client.collection_exists(COLLECTION_NAME):
        print(f"📦 Creating new collection: {COLLECTION_NAME}")
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=models.VectorParams(size=384, distance=models.Distance.COSINE),
            sparse_vectors_config={"sparse_vector": models.SparseVectorParams()},
        )
    else:
        print(f"✅ Collection {COLLECTION_NAME} already exists.")

    # 2. Setup Models
    print("🧠 Loading models...")
    embeddings = FastEmbedEmbeddings(model_name="BAAI/bge-small-en-v1.5")
    sparse_embeddings = FastEmbedSparse(model_name="Qdrant/bm25")

    # 3. Process PDFs
    all_docs = []
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)

    print("📄 Downloading and processing PDFs...")
    for url in PDF_URLS:
        try:
            print(f"   - Processing: {url}")
            loader = PyMuPDFLoader(url)
            docs = loader.load()
            # Clean metadata to just filename
            for doc in docs:
                doc.metadata["file"] = url
                doc.metadata["source"] = url
            chunks = text_splitter.split_documents(docs)
            all_docs.extend(chunks)
        except Exception as e:
            print(f"❌ Failed to load {url}: {e}")

    # 4. Upload to Qdrant
    print(f"📤 Uploading {len(all_docs)} chunks to Qdrant...")
    QdrantVectorStore.from_documents(
        documents=all_docs,
        embedding=embeddings,
        sparse_embedding=sparse_embeddings,
        url=QDRANT_URL,
        api_key=QDRANT_API_KEY,
        collection_name=COLLECTION_NAME,
        retrieval_mode=RetrievalMode.HYBRID,
        vector_name="dense_vector",
        sparse_vector_name="sparse_vector",
        force_recreate=True # Don't delete if we just created it
    )
    
    print("🎉 Success! Database is full. Your Railway app should work now.")

if __name__ == "__main__":
    main()