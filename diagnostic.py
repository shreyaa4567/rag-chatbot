# diagnostic.py
import config
from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings

embeddings = OllamaEmbeddings(model=config.EMBED_MODEL)
db = Chroma(persist_directory=config.CHROMA_DIR, embedding_function=embeddings)
results = db.similarity_search("imagination Einstein", k=10)

for r in results:
    print(r.metadata.get("source"))
    print(r.page_content[:300])
    print("---")