# preload.py
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_qdrant import FastEmbedSparse
# or whatever library you use in main.py

print("Downloading models...")
# Initialize the model here to force the download
embeddings = HuggingFaceEmbeddings(model_name='BAAI/bge-m3')
sparse_embeddings = FastEmbedSparse(model_name="Qdrant/bm25")
print("Download complete!")