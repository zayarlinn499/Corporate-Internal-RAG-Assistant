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
# Load API Key
# =========================

load_dotenv()

# =========================
# Read Excel
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
# Embeddings
# =========================

embeddings = HuggingFaceEmbeddings(
    model_name="BAAI/bge-small-en"
)

# =========================
# Qdrant
# =========================

client = QdrantClient(":memory:")

client.create_collection(
    collection_name="finance_data",
    vectors_config=VectorParams(
        size=384,
        distance=Distance.COSINE,
    ),
)

db = QdrantVectorStore(
    client=client,
    collection_name="finance_data",
    embedding=embeddings,
)

db.add_documents(documents)

# =========================
# Groq LLM
# =========================

llm = ChatGroq(
    model="llama-3.3-70b-versatile"
)

# =========================
# Chat Loop
# =========================

while True:

    question = input("\nAsk a question (type exit to quit): ")

    if question.lower() == "exit":
        break

    docs = db.similarity_search(question, k=3)

    context = "\n\n".join(
        [doc.page_content for doc in docs]
    )

    prompt = f"""
You are a financial assistant.

Answer ONLY using the context below.

Context:
{context}

Question:
{question}
"""

    response = llm.invoke(prompt)

    print("\nAnswer:\n")
    print(response.content)