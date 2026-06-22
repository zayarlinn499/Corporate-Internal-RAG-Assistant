const form = document.getElementById('chat-form');
const input = document.getElementById('user-input');
const chatWindow = document.getElementById('chat-window');
const newChatBtn = document.getElementById('new-chat-btn');
const uploadBtn = document.getElementById('upload-btn');
const docUpload = document.getElementById('doc-upload');
const docList = document.getElementById('doc-list');
const uploadStatus = document.getElementById('upload-status');
const chatList = document.getElementById('chat-list');

let currentChatId = null;

// Initialize marked.js options
marked.setOptions({
    breaks: true,
    gfm: true
});

// App Initialization
async function initApp() {
    fetchDocuments();
    await fetchChats();
    if (!currentChatId) {
        await createNewChat();
    }
}

initApp();

// ==========================================
// CHAT HISTORY LOGIC
// ==========================================
async function fetchChats() {
    try {
        const response = await fetch('/api/chats');
        const chats = await response.json();
        
        chatList.innerHTML = '';
        // Sort by ID or reverse order (latest first)
        chats.reverse().forEach(chat => {
            const li = document.createElement('li');
            li.className = `chat-item ${chat.id === currentChatId ? 'active' : ''}`;
            li.textContent = chat.title;
            li.onclick = () => loadChat(chat.id);
            chatList.appendChild(li);
        });
        
        if (chats.length > 0 && !currentChatId) {
            currentChatId = chats[0].id;
            loadChat(currentChatId);
        }
    } catch (e) {
        console.error("Failed to fetch chats", e);
    }
}

async function createNewChat() {
    try {
        const response = await fetch('/api/chats', { method: 'POST' });
        const data = await response.json();
        currentChatId = data.chat_id;
        
        // Reset Window
        chatWindow.innerHTML = `
            <div class="message assistant-message intro">
                <div class="avatar">AI</div>
                <div class="content">Hello! I'm your financial data assistant. Ask me anything!</div>
            </div>
        `;
        fetchChats(); // Refresh sidebar to show new chat
    } catch (e) {
        console.error("Failed to create chat", e);
    }
}

async function loadChat(chatId) {
    currentChatId = chatId;
    fetchChats(); // Refresh sidebar active state
    
    try {
        const response = await fetch(`/api/chats/${chatId}`);
        const chatData = await response.json();
        
        chatWindow.innerHTML = '';
        if (chatData.messages.length === 0) {
            chatWindow.innerHTML = `
                <div class="message assistant-message intro">
                    <div class="avatar">AI</div>
                    <div class="content">Hello! I'm your financial data assistant. Ask me anything!</div>
                </div>
            `;
        } else {
            chatData.messages.forEach(msg => {
                appendMessage(msg.role, msg.content, false);
            });
        }
        scrollToBottom();
    } catch (e) {
        console.error("Failed to load chat", e);
    }
}

newChatBtn.addEventListener('click', createNewChat);

// ==========================================
// MESSAGE LOGIC
// ==========================================
function appendMessage(role, text, animate = true) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${role}-message`;
    if (!animate) { messageDiv.style.animation = 'none'; }
    
    const avatar = document.createElement('div');
    avatar.className = 'avatar';
    avatar.textContent = role === 'user' ? 'U' : 'AI';
    
    const content = document.createElement('div');
    content.className = 'content';
    
    if (role === 'assistant') {
        content.innerHTML = marked.parse(text);
    } else {
        content.textContent = text;
    }
    
    messageDiv.appendChild(avatar);
    messageDiv.appendChild(content);
    chatWindow.appendChild(messageDiv);
    
    scrollToBottom();
}

function showTypingIndicator() {
    const indicator = document.createElement('div');
    indicator.className = 'message assistant-message typing';
    indicator.id = 'typing-indicator';
    
    const avatar = document.createElement('div');
    avatar.className = 'avatar';
    avatar.textContent = 'AI';
    
    const content = document.createElement('div');
    content.className = 'content typing-indicator';
    content.innerHTML = '<div class="dot"></div><div class="dot"></div><div class="dot"></div>';
    
    indicator.appendChild(avatar);
    indicator.appendChild(content);
    chatWindow.appendChild(indicator);
    
    scrollToBottom();
}

function removeTypingIndicator() {
    const indicator = document.getElementById('typing-indicator');
    if (indicator) indicator.remove();
}

function scrollToBottom() {
    chatWindow.scrollTop = chatWindow.scrollHeight;
}

form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const query = input.value.trim();
    if (!query) return;

    if (!currentChatId) {
        await createNewChat();
    }

    appendMessage('user', query);
    input.value = '';
    showTypingIndicator();

    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                query: query,
                chat_id: currentChatId
            })
        });

        if (!response.ok) throw new Error('Network response was not ok');
        
        const data = await response.json();
        removeTypingIndicator();
        appendMessage('assistant', data.answer);
        
        // Refresh chat list in case title changed
        fetchChats();

    } catch (error) {
        removeTypingIndicator();
        appendMessage('assistant', '❌ Sorry, there was an error communicating with the server.');
        console.error('Error:', error);
    }
});

// ==========================================
// DOCUMENT MANAGER LOGIC
// ==========================================
async function fetchDocuments() {
    try {
        const response = await fetch('/api/documents');
        const data = await response.json();
        
        docList.innerHTML = '';
        data.documents.forEach(doc => {
            const li = document.createElement('li');
            li.className = 'doc-item';
            li.innerHTML = `
                <span class="doc-name" title="${doc}">${doc}</span>
                <button class="delete-btn" onclick="deleteDocument('${doc}')" title="Delete">🗑️</button>
            `;
            docList.appendChild(li);
        });
    } catch (error) {
        console.error("Failed to fetch documents", error);
    }
}

uploadBtn.addEventListener('click', () => docUpload.click());

docUpload.addEventListener('change', async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    
    const formData = new FormData();
    formData.append("file", file);
    
    uploadStatus.textContent = "Uploading...";
    
    try {
        const response = await fetch('/api/documents', {
            method: 'POST',
            body: formData
        });
        
        if (response.ok) {
            uploadStatus.textContent = "Success!";
            fetchDocuments();
        } else {
            const err = await response.json();
            uploadStatus.textContent = err.detail || "Upload failed.";
        }
    } catch (error) {
        uploadStatus.textContent = "Error during upload.";
    }
    
    setTimeout(() => { uploadStatus.textContent = ""; }, 3000);
    docUpload.value = '';
});

async function deleteDocument(filename) {
    if (!confirm(`Are you sure you want to delete ${filename}?`)) return;
    
    try {
        const response = await fetch(`/api/documents/${filename}`, { method: 'DELETE' });
        if (response.ok) {
            fetchDocuments();
        } else {
            alert("Failed to delete document.");
        }
    } catch (error) {
        console.error("Delete error:", error);
    }
}
