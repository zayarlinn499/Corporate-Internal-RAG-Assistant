from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

# Create local in-memory Qdrant
client = QdrantClient(":memory:")

# Create collection
client.create_collection(
    collection_name="finance_data",
    vectors_config=VectorParams(
        size=384,  # bge-small-en output size
        distance=Distance.COSINE,
    ),
)

# Create vector store
db = QdrantVectorStore.from_documents(
    documents=documents,
    embedding=embeddings,
    client=client,
    collection_name="finance_data",
)

print("Vector DB created!")

# Test search
query = "Which company is in Consumer Electronics?"

results = db.similarity_search(query, k=3)

print("\nSearch Results:\n")

for doc in results:
    print(doc.page_content)
    print("=" * 50)