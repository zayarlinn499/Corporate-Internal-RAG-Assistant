import os
import re
import pandas as pd
import streamlit as st

from dotenv import load_dotenv

from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

from langchain_groq import ChatGroq
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_experimental.agents import create_pandas_dataframe_agent

# =========================
# 1. SETUP & CONFIG
# =========================
st.set_page_config(page_title="Finance RAG Assistant", page_icon="📈", layout="centered")

load_dotenv()

@st.cache_resource
def get_data_and_vectorstore():
    # Load Data
    df = pd.read_excel("data/financialdata.xlsx")
    
    # Create Documents
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
            Document(page_content=text, metadata={"department": "finance", "company": row['shortName'], "industry": row['industry']})
        )
    
    # Setup Embeddings
    embeddings = HuggingFaceEmbeddings(model_name="BAAI/bge-small-en")
    
    # Setup Qdrant
    client = QdrantClient(":memory:")
    client.create_collection(
        collection_name="finance_data",
        vectors_config=VectorParams(size=384, distance=Distance.COSINE)
    )
    vector_store = QdrantVectorStore(
        client=client,
        collection_name="finance_data",
        embedding=embeddings,
    )
    vector_store.add_documents(documents)
    
    return df, vector_store

@st.cache_resource
def get_llm():
    return ChatGroq(model="llama-3.3-70b-versatile")

df, vector_store = get_data_and_vectorstore()
llm = get_llm()

# =========================
# 2. GUARDRAILS
# =========================
def check_guardrails(query: str) -> str | None:
    # 1. PII Regex (Phone & Email)
    email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    phone_pattern = r'\b\d{3}[-.\s]??\d{3}[-.\s]??\d{4}\b'
    
    if re.search(email_pattern, query) or re.search(phone_pattern, query):
        return "🛡️ **Guardrail Alert:** PII (Email or Phone number) detected. Please do not share personal information."
    
    # 2. Prompt Injection Keywords
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

# =========================
# 3. LLM ROUTER
# =========================
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

# =========================
# 4. TOOLS
# =========================
def format_history(messages):
    history_str = ""
    # Only take the last 4 messages to avoid context bloat
    for msg in messages[-4:]:
        role = "User" if msg["role"] == "user" else "Assistant"
        history_str += f"{role}: {msg['content']}\n"
    return history_str

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
        
        # Extract the python code
        import re
        match = re.search(r'```python\n(.*?)\n```', code_response, re.DOTALL)
        if not match:
            match = re.search(r'```(.*?)```', code_response, re.DOTALL)
            
        code = match.group(1) if match else code_response.replace('```', '')
        
        import sys
        import io
        
        old_stdout = sys.stdout
        sys.stdout = mystdout = io.StringIO()
        
        # Execute the generated code
        exec(code, {'df': df, 'pd': pd})
        
        sys.stdout = old_stdout
        answer = mystdout.getvalue().strip()
        return answer if answer else "Done, but no output was printed."
    except Exception as e:
        # Ensure stdout is restored on error
        sys.stdout = sys.__stdout__
        return f"❌ Sorry, I had trouble processing that data request. Details: {str(e)}"

def run_rag(q: str, history_context: str) -> str:
    # Use top k=5 as requested
    docs = vector_store.similarity_search(q, k=5)
    context = "\n\n".join([d.page_content for d in docs])

    prompt = f"""
You are a financial assistant.
Use ONLY this context to answer the question:
{context}

Chat History for context (if the user refers to previous items):
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
# 5. STREAMLIT UI
# =========================
st.title("📊 Finance RAG System")
st.markdown("Ask me questions about company financial data!")

if "messages" not in st.session_state:
    st.session_state.messages = []

# Display chat messages from history on app rerun
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# React to user input
if prompt := st.chat_input("Ask a question..."):
    # Display user message in chat message container
    st.chat_message("user").markdown(prompt)
    # Add user message to chat history
    st.session_state.messages.append({"role": "user", "content": prompt})

    # Get minimal chat history string
    history_str = format_history(st.session_state.messages[:-1]) # exclude current prompt

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            # 1. Guardrails
            guardrail_block = check_guardrails(prompt)
            
            if guardrail_block:
                answer = guardrail_block
            else:
                # 2. LLM Router
                route = route_query_llm(prompt, history_str)
                
                # 3. Execution
                if route == "pandas":
                    answer = run_pandas(prompt, history_str)
                elif route == "rag":
                    answer = run_rag(prompt, history_str)
                else:
                    answer = run_llm(prompt, history_str)

        # 4. Display Answer
        st.markdown(answer)
        
    # Add assistant response to chat history
    st.session_state.messages.append({"role": "assistant", "content": answer})
