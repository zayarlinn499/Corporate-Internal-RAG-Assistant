import pandas as pd

from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_qdrant import QdrantVectorStore

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

print("Starting RAG...")

# =========================
# Read Excel
# =========================

df = pd.read_excel("data/financialdata.xlsx")

print(f"Loaded {len(df)} rows")

# =========================
# Convert Excel -> Documents
# =========================

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
            metadata={
                "department": "finance"
            }
        )
    )

print(f"Created {len(documents)} documents")

# =========================
# Embedding Model
# =========================

print("Loading embedding model...")

embeddings = HuggingFaceEmbeddings(
    model_name="BAAI/bge-small-en"
)

print("Embedding model loaded")

# =========================
# Create Qdrant Client
# =========================

client = QdrantClient(":memory:")

# =========================
# Create Collection
# =========================

client.create_collection(
    collection_name="finance_data",
    vectors_config=VectorParams(
        size=384,
        distance=Distance.COSINE,
    ),
)

print("Qdrant collection created")

# =========================
# Store Documents
# =========================

db = QdrantVectorStore(
    client=client,
    collection_name="finance_data",
    embedding=embeddings,
)
db.add_documents(documents)

print("Documents added:", len(documents))

print("Documents stored in Qdrant")

# =========================
# Test Search
# =========================

query = "Which company is in Consumer Electronics?"

print(f"\nQuery: {query}")

results = db.similarity_search(query, k=3)

print("\nTop Results:\n")

for i, doc in enumerate(results, start=1):
    print(f"Result #{i}")
    print(doc.page_content)
    print("=" * 60)