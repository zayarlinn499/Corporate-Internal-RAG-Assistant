# 🏢 Corporate RAG Chatbot

![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![Groq](https://img.shields.io/badge/LLM-Groq-orange.svg)
![Qdrant](https://img.shields.io/badge/VectorStore-Qdrant-red.svg)
![LangChain](https://img.shields.io/badge/Framework-LangChain-green.svg)

> An intelligent, AI-powered corporate assistant that securely retrieves and generates answers based on internal company documents using Retrieval-Augmented Generation (RAG).

## 🌟 Overview
The **Corporate RAG Chatbot** empowers organizations to query their own data naturally and securely. By combining the blazing-fast inference of **Groq** with the high-performance **Qdrant** vector database, this application instantly searches through enterprise documents to provide accurate, context-aware responses.

Say goodbye to digging through endless PDFs and wikis—just ask the chatbot!

## ✨ Key Features
- **🧠 Context-Aware AI**: Provides highly accurate answers grounded *only* in your provided company documents.
- **⚡ Ultra-Fast Generation**: Powered by Groq for near-instantaneous LLM responses.
- **🔍 Semantic Search**: Uses state-of-the-art embedding models and Qdrant vector database to understand the meaning behind your queries, not just keyword matching.
- **🛡️ Data Privacy**: Designed to keep corporate knowledge secure by utilizing local in-memory vector stores and protecting API keys.

## 🛠️ Technology Stack
- **Language**: Python
- **LLM Provider**: Groq API
- **Vector Database**: Qdrant (In-Memory)
- **Framework**: LangChain

## 🚀 Getting Started

### 1. Clone the repository
```bash
git clone https://github.com/YOUR_USERNAME/Corporate-RAG-Chatbot.git
cd Corporate-RAG-Chatbot
```

### 2. Set up the environment
Create a virtual environment and install the dependencies:
```bash
python -m venv venv
# On Windows:
venv\Scripts\activate
# On Mac/Linux:
source venv/bin/activate

pip install -r requirements.txt
```

### 3. Add your API Keys
Create a `.env` file in the root directory and add your Groq API key:
```env
GROQ_API_KEY=your_groq_api_key_here
```

### 4. Run the application
```bash
python app.py
```

## 🤝 Contributing
Contributions, issues, and feature requests are welcome! Feel free to check the issues page.
