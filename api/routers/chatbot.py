import ollama
import chromadb
from pypdf import PdfReader 
from fastapi import FastAPI 
import uvicorn

client = chromadb.Client()
collection = client.create_collection(name="docs")

reader = PdfReader('../../GDPRArticles.pdf')
chunks = [page.extract_text().strip() for page in reader.pages if page.extract_text().strip()]
print("Done reading pages!")
for i, chunk in enumerate(chunks):
    response = ollama.embed(model="nomic-embed-text", input=chunk)
    embedding = response["embeddings"][0]
    collection.add(
        ids=[str(i)],
        embeddings=[embedding],
        documents=[chunk]
    )
print("Embeddings done!")

app = FastAPI()

@app.post("/chat")
async def chat_bot(prompt: str):
    if not prompt:
        return
    query = prompt
    response = ollama.embed(model="nomic-embed-text", input=query)
    query_embedding = response["embeddings"][0]

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=1
    )
    data = results['documents'][0][0]

    output = ollama.generate(
        model="llama3.2",
        prompt=f"Context: {data}\n\nQuestion: {query}\n\nAnswer:"
    )
    return {"response": output["response"]}


if __name__ == '__main__':
    uvicorn.run(app, port=8080, host='0.0.0.0')