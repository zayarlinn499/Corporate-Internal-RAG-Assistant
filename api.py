import os
import re
import sys
import io
import shutil
import json
import uuid
import PyPDF2
import pandas as pd
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv

from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient, models
from qdrant_client.models import Distance, VectorParams

from langchain_groq import ChatGroq
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser

# =========================
# 1. SETUP & CONFIG
# =========================
load_dotenv()

app = FastAPI()
os.makedirs("data/uploads", exist_ok=True)
CHATS_FILE = "data/chats.json"

# Global State
df = pd.DataFrame()
vector_store = None
qdrant_client = None
llm = ChatGroq(model="llama-3.3-70b-versatile")

# Chat Storage Logic
def load_chats():
    if os.path.exists(CHATS_FILE):
        with open(CHATS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_chats(chats):
    with open(CHATS_FILE, "w") as f:
        json.dump(chats, f, indent=4)

def init_system():
    global df, vector_store, qdrant_client
    
    # 1. Base Data
    if os.path.exists("data/financialdata.xlsx"):
        df = pd.read_excel("data/financialdata.xlsx")
        df['source'] = 'financialdata.xlsx'
    else:
        df = pd.DataFrame()

    documents = []
    if not df.empty:
        for _, row in df.iterrows():
            text = f"""
Company: {row.get('shortName', '')}
Industry: {row.get('industry', '')}
EBITDA Margin: {row.get('ebitdaMargins', '')}
Profit Margin: {row.get('profitMargins', '')}
Gross Margin: {row.get('grossMargins', '')}
Operating Cashflow: {row.get('operatingCashflow', '')}
"""
            documents.append(
                Document(page_content=text, metadata={"source": "financialdata.xlsx", "type": "base_excel"})
            )

    # 2. Qdrant Setup
    embeddings = HuggingFaceEmbeddings(model_name="BAAI/bge-small-en")
    qdrant_client = QdrantClient(":memory:")
    qdrant_client.create_collection(
        collection_name="finance_data",
        vectors_config=VectorParams(size=384, distance=Distance.COSINE)
    )
    vector_store = QdrantVectorStore(
        client=qdrant_client,
        collection_name="finance_data",
        embedding=embeddings,
    )
    
    if documents:
        vector_store.add_documents(documents)

    # 3. Load previously uploaded files
    for f in os.listdir("data/uploads"):
        ingest_file(os.path.join("data/uploads", f), f)

def ingest_file(filepath: str, filename: str):
    global df
    new_docs = []
    
    if filename.endswith(('.xlsx', '.xls')):
        try:
            new_df = pd.read_excel(filepath)
            new_df['source'] = filename
            df = pd.concat([df, new_df], ignore_index=True)
            
            for _, row in new_df.iterrows():
                text = " | ".join([f"{col}: {val}" for col, val in row.items() if col != 'source'])
                new_docs.append(Document(page_content=text, metadata={"source": filename, "type": "excel"}))
        except Exception as e:
            print(f"Error parsing Excel {filename}: {e}")
            
    elif filename.endswith('.pdf'):
        try:
            with open(filepath, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                text = ""
                for page in reader.pages:
                    if page.extract_text():
                        text += page.extract_text() + "\n"
            
            chunks = [t.strip() for t in text.split('\n\n') if len(t.strip()) > 10]
            for chunk in chunks:
                new_docs.append(Document(page_content=chunk, metadata={"source": filename, "type": "pdf"}))
        except Exception as e:
            print(f"Error parsing PDF {filename}: {e}")
            
    elif filename.endswith('.txt'):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                text = f.read()
            chunks = [t.strip() for t in text.split('\n\n') if len(t.strip()) > 10]
            for chunk in chunks:
                new_docs.append(Document(page_content=chunk, metadata={"source": filename, "type": "txt"}))
        except Exception as e:
            print(f"Error parsing TXT {filename}: {e}")

    if new_docs:
        vector_store.add_documents(new_docs)

def remove_file_data(filename: str):
    global df
    if 'source' in df.columns:
        df = df[df['source'] != filename]
        
    qdrant_client.delete(
        collection_name="finance_data",
        points_selector=models.Filter(
            must=[
                models.FieldCondition(
                    key="metadata.source",
                    match=models.MatchValue(value=filename)
                )
            ]
        )
    )

# Initialize system on startup
init_system()

# =========================
# 2. Pydantic Models
# =========================
class ChatRequest(BaseModel):
    query: str
    chat_id: str

class ChatResponse(BaseModel):
    answer: str

# =========================
# 3. AI FUNCTIONS
# =========================
def check_guardrails(query: str) -> str | None:
    email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    phone_pattern = r'\b\d{3}[-.\s]??\d{3}[-.\s]??\d{4}\b'
    
    if re.search(email_pattern, query) or re.search(phone_pattern, query):
        return "🛡️ **Guardrail Alert:** PII (Email or Phone number) detected. Please do not share personal information."
    
    blocked_phrases = [
        "ignore instructions", "ignore all instructions",
        "reveal system prompt", "what is your prompt",
        "give me all data", "dump database"
    ]
    query_lower = query.lower()
    for phrase in blocked_phrases:
        if phrase in query_lower:
            return "🛡️ **Guardrail Alert:** Invalid query detected. This action is not allowed."
            
    return None

def route_query_llm(query: str, history_context: str) -> str:
    router_prompt = PromptTemplate.from_template("""
You are an intelligent routing assistant for a financial chatbot.
Given the user's latest query and the chat history, classify the latest query into exactly one of these three categories:

1. "pandas": The user is asking for math, aggregation, counting, or listing based on tabular data (e.g., "how many companies", "highest ebitda", "list industries").
2. "rag": The user is asking for information, explanations, or details about specific companies or industries (e.g., "tell me about Microsoft", "what does Apple do?").
3. "llm": The user is asking a general conversational question not related to financial data (e.g., "hello", "how are you").

Chat History:
{history}

Latest Query: {query}

Output ONLY the category name ("pandas", "rag", or "llm") in lowercase. No other text.
""")
    chain = router_prompt | llm | StrOutputParser()
    result = chain.invoke({"history": history_context, "query": query})
    
    result = result.strip().lower()
    if "pandas" in result: return "pandas"
    if "rag" in result: return "rag"
    return "llm"

def run_pandas(q: str, history_context: str) -> str:
    schema = df.dtypes.to_string()
    
    prompt = f"""
You are a data analyst. You have a pandas dataframe named `df` with these columns and types:
{schema}

Chat History:
{history_context}

User Question: {q}

Write EXACTLY ONE python script that calculates the answer and prints it using `print()`. 
Do NOT explain your code. Return ONLY the python code inside ```python ``` blocks.
Assume `df` is already loaded and `pandas as pd` is imported.
If they ask for count/number of companies, use `len(df)` or `df['shortName'].nunique()`.
"""
    try:
        code_response = llm.invoke(prompt).content
        
        match = re.search(r'```python\n(.*?)\n```', code_response, re.DOTALL)
        if not match:
            match = re.search(r'```(.*?)```', code_response, re.DOTALL)
            
        code = match.group(1) if match else code_response.replace('```', '')
        
        old_stdout = sys.stdout
        sys.stdout = mystdout = io.StringIO()
        
        exec(code, {'df': df, 'pd': pd})
        
        sys.stdout = old_stdout
        answer = mystdout.getvalue().strip()
        return answer if answer else "Done, but no output was printed."
    except Exception as e:
        sys.stdout = sys.__stdout__
        return f"❌ Sorry, I had trouble processing that data request. Details: {str(e)}"

def run_rag(q: str, history_context: str) -> str:
    # Reformulate query to handle pronouns like "it" based on history
    if history_context.strip():
        rewrite_prompt = f"""
Given the following conversation history and the latest user question, rephrase the latest question to be a standalone question that can be understood without the history (e.g., replacing "it" with the subject).
If the latest question is already standalone, just return it exactly as is. DO NOT answer the question, just rewrite it.

Chat History:
{history_context}

Latest Question: {q}

Standalone Question:"""
        search_query = llm.invoke(rewrite_prompt).content.strip()
        # Clean up quotes if the LLM adds them
        search_query = search_query.strip('"').strip("'")
    else:
        search_query = q

    docs = vector_store.similarity_search(search_query, k=5)
    context = "\n\n".join([d.page_content for d in docs])

    prompt = f"""
You are a financial assistant.
Use ONLY this context to answer the question:
{context}

Chat History for context:
{history_context}

Latest Question:
{q}

If the answer is not in the context, say "Not enough information".
"""
    return llm.invoke(prompt).content

def run_llm(q: str, history_context: str) -> str:
    prompt = f"""
Chat History:
{history_context}

Latest Question: {q}
"""
    return llm.invoke(prompt).content

# =========================
# 4. API Endpoints
# =========================

# Chat History Endpoints
@app.get("/api/chats")
async def get_chats():
    chats = load_chats()
    return [{"id": k, "title": v.get("title", "New Chat")} for k, v in chats.items()]

@app.post("/api/chats")
async def create_chat():
    chats = load_chats()
    chat_id = str(uuid.uuid4())
    chats[chat_id] = {
        "title": "New Chat",
        "messages": []
    }
    save_chats(chats)
    return {"chat_id": chat_id, "title": "New Chat"}

@app.get("/api/chats/{chat_id}")
async def get_chat_history(chat_id: str):
    chats = load_chats()
    if chat_id not in chats:
        raise HTTPException(status_code=404, detail="Chat not found")
    return chats[chat_id]

# Main Chat Endpoint
@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest):
    query = request.query
    chat_id = request.chat_id
    
    chats = load_chats()
    if chat_id not in chats:
        raise HTTPException(status_code=404, detail="Chat not found. Please create a new chat.")
        
    # Build history string from stored messages
    history_str = ""
    for msg in chats[chat_id]["messages"]:
        role = "User" if msg["role"] == "user" else "Assistant"
        history_str += f"{role}: {msg['content']}\n"
    
    # 1. Guardrails
    guardrail_block = check_guardrails(query)
    if guardrail_block:
        return ChatResponse(answer=guardrail_block)
        
    # 2. Router
    route = route_query_llm(query, history_str)
    
    # 3. Execution
    try:
        if route == "pandas":
            answer = run_pandas(query, history_str)
        elif route == "rag":
            answer = run_rag(query, history_str)
        else:
            answer = run_llm(query, history_str)
            
        # 4. Update Chat Storage
        if len(chats[chat_id]["messages"]) == 0:
            chats[chat_id]["title"] = query[:30] + "..." if len(query) > 30 else query
            
        chats[chat_id]["messages"].append({"role": "user", "content": query})
        chats[chat_id]["messages"].append({"role": "assistant", "content": answer})
        save_chats(chats)
            
        return ChatResponse(answer=answer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Document Management Endpoints
@app.get("/api/documents")
async def get_documents():
    files = os.listdir("data/uploads")
    return {"documents": files}

@app.post("/api/documents")
async def upload_document(file: UploadFile = File(...)):
    if not file.filename.endswith(('.txt', '.pdf', '.xlsx', '.xls')):
        raise HTTPException(status_code=400, detail="Only .txt, .pdf, and excel files are allowed.")
        
    filepath = os.path.join("data/uploads", file.filename)
    with open(filepath, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    ingest_file(filepath, file.filename)
    return {"message": "File uploaded successfully", "filename": file.filename}

@app.delete("/api/documents/{filename}")
async def delete_document(filename: str):
    filepath = os.path.join("data/uploads", filename)
    if os.path.exists(filepath):
        os.remove(filepath)
        remove_file_data(filename)
        return {"message": "Document deleted"}
    raise HTTPException(status_code=404, detail="File not found")

# Mount static files to serve the frontend
if os.path.exists("static"):
    app.mount("/", StaticFiles(directory="static", html=True), name="static")
