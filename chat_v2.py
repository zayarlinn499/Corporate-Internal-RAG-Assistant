import os
import pandas as pd

from dotenv import load_dotenv

from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

from langchain_groq import ChatGroq


# =========================
# 1. ENV
# =========================
load_dotenv()

# =========================
# 2. DATA
# =========================
df = pd.read_excel("data/financialdata.xlsx")

documents = []
for _, row in df.iterrows():
    text = f"""
Company: {row['shortName']}
Industry: {row['industry']}
EBITDA Margin: {row['ebitdaMargins']}
Profit Margin: {row['profitMargins']}
Gross Margin: {row['grossMargins']}
Operating Cashflow: {row['operatingCashflow']}
"""

    documents.append(
        Document(
            page_content=text,
            metadata={"department": "finance"}
        )
    )

# =========================
# 3. EMBEDDINGS
# =========================
embeddings = HuggingFaceEmbeddings(model_name="BAAI/bge-small-en")

# =========================
# 4. QDRANT
# =========================
client = QdrantClient(":memory:")

client.create_collection(
    collection_name="finance_data",
    vectors_config=VectorParams(
        size=384,
        distance=Distance.COSINE
    )
)

vector_store = QdrantVectorStore(
    client=client,
    collection_name="finance_data",
    embedding=embeddings,
)

vector_store.add_documents(documents)

# =========================
# 5. LLM
# =========================
llm = ChatGroq(model="llama-3.3-70b-versatile")


# =========================
# 6. ROUTER (NEW ADDITION)
# =========================
def route_query(q: str) -> str:
    q = q.lower()

    if any(x in q for x in ["how many", "highest", "lowest", "average", "sum", "what industries", "list industries", "most"]):
        return "pandas"

    if any(x in q for x in ["company", "industry", "industries", "tell me", "about", "explain"]):
        return "rag"

    return "llm"


# =========================
# 7. PANDAS TOOL
# =========================
def run_pandas(q, df):
    q = q.lower()

    # ----------------------------
    # FIX: TYPO HANDLING
    # ----------------------------
    q = q.replace("comapanies", "companies")

    # ----------------------------
    # 1. COUNT COMPANIES
    # ----------------------------
    if "how many companies" in q:
        return f"Total companies: {len(df)}"

    # ----------------------------
    # 2. COUNT INDUSTRIES (NEW FIX)
    # ----------------------------
    if "how many industries" in q:
        return f"Total unique industries: {df['industry'].nunique()}"

    # ----------------------------
    # 3. HIGH / LOW EBITDA
    # ----------------------------
    if "highest" in q and "ebitda" in q:
        row = df.loc[df["ebitdaMargins"].idxmax()]
        return f"{row['shortName']} has highest EBITDA margin: {row['ebitdaMargins']:.4f}"

    if "lowest" in q and "ebitda" in q:
        row = df.loc[df["ebitdaMargins"].idxmin()]
        return f"{row['shortName']} has lowest EBITDA margin: {row['ebitdaMargins']:.4f}"

    # ----------------------------
    # 4. LIST INDUSTRIES
    # ----------------------------
    if "what industries" in q or "list industries" in q:
        return df["industry"].unique().tolist()

    # ----------------------------
    # 5. ❌ FIXED FALLBACK (IMPORTANT)
    # ----------------------------
    return "❌ I can only answer structured analytics questions like count, industry stats, or margins."
    
# =========================
# 8. RAG TOOL (YOUR ORIGINAL LOGIC IMPROVED)
# =========================
def run_rag(q):
    docs = vector_store.similarity_search(q, k=3)

    context = "\n\n".join([d.page_content for d in docs])

    prompt = f"""
You are a financial assistant.

Use ONLY this context:

{context}

Question:
{q}

If answer is not in context, say "Not enough information".
"""

    return llm.invoke(prompt).content


# =========================
# 9. LLM TOOL
# =========================
def run_llm(q):
    return llm.invoke(q).content


# =========================
# 10. MAIN CHAT LOOP
# =========================
print("\nFinance RAG System (v2 with routing)\n")

while True:
    q = input("Ask a question (type exit to quit): ")

    if q.lower() == "exit":
        break

    route = route_query(q)

    print(f"\n[DEBUG] Route: {route}")

    if route == "pandas":
        answer = run_pandas(q, df)

    elif route == "rag":
        answer = run_rag(q)

    else:
        answer = run_llm(q)

    print("\nAnswer:\n")
    print(answer)