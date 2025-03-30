// Inside static/script.js

document.addEventListener('DOMContentLoaded', () => {
    const messageInput = document.getElementById('message-input'); // This is the <textarea>
    const sendButton = document.getElementById('send-button');
    const chatMessages = document.getElementById('chat-messages');
    const statusIndicator = document.getElementById('status-indicator');

    //const API_BASE_URL = 'https://ankixparlai-380281608527.europe-southwest1.run.app'; // Your Cloud Run URL
    const API_BASE_URL = 'http://localhost:8000'; // Your Cloud Run URL
    let currentSessionId = null;
    let isRequestPending = false;

    function addMessage(text, sender, data = {}) {
        const messageDiv = document.createElement('div');
        messageDiv.classList.add('message', sender);
        messageDiv.textContent = text;

        if (sender === 'teacher' && data.query) {
            const button = document.createElement('button');
            button.classList.add('add-card-button');
            button.textContent = '💾 Add Card?';
            button.dataset.query = data.query;
            messageDiv.appendChild(document.createElement('br'));
            messageDiv.appendChild(button);
        }

        chatMessages.appendChild(messageDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    function updateStatus(status) {
        switch(status) {
            case 'online':
                statusIndicator.textContent = '🟢';
                statusIndicator.title = 'Connected';
                break;
            case 'error':
                statusIndicator.textContent = '🟠';
                statusIndicator.title = 'Connection Error';
                addMessage("Error connecting. Check server.", "status");
                break;
            case 'offline':
                 statusIndicator.textContent = '🔴';
                 statusIndicator.title = 'Offline';
                 addMessage("Cannot reach server.", "status");
                 break;
            default: // connecting
                statusIndicator.textContent = '⚪';
                statusIndicator.title = 'Connecting...';
        }
     }

    function autoResizeTextarea() {
        messageInput.style.height = 'auto';
        messageInput.style.height = messageInput.scrollHeight + 'px';
    }

    async function handleAddCardClick(event) {
        const button = event.target;
        const query = button.dataset.query;
        if (!query) return;

        console.log(`Add card requested for query: "${query}"`);
        button.textContent = 'Saving...';
        button.disabled = true;

        try {
            const response = await fetch(API_BASE_URL + '/addcard', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ query: query }),
            });

            const data = await response.json();

            if (response.ok && data.success) {
                console.log('Add card success:', data.message);
                addMessage(`✅ ${data.message} (Query: ${query})`, 'status');
                button.textContent = 'Saved!';
            } else {
                console.error('Add card failed:', data.message);
                addMessage(`❌ Error: ${data.message} (Query: ${query})`, 'status');
                button.textContent = 'Error!';
                button.disabled = false;
                button.textContent = '💾 Add Card?';
            }
        } catch (error) {
            console.error('Network Error during add card:', error);
            addMessage('Network Error: Could not save card data.', 'status');
            button.textContent = 'Network Error!';
             button.disabled = false;
             button.textContent = '💾 Add Card?';
        }
    }

    async function sendMessageToServer(messageText, isInitialGreeting = false) {
        if (isRequestPending) {
            console.warn("Request already pending, skipping send.");
            return;
        }

        if (!isInitialGreeting) {
            messageText = messageInput.value.trim();
            if (!messageText) {
                 return;
             }
        } else if (messageText === null || messageText === undefined) {
            console.error("Initial greeting message text is invalid.");
            return;
        }

        isRequestPending = true;
        sendButton.disabled = true;
        messageInput.disabled = true;

        if (!isInitialGreeting) {
            addMessage(messageText, 'user');
            messageInput.value = '';
            autoResizeTextarea();
        } else {
            addMessage("Starting conversation...", "status");
        }

        let endpoint = '';
        let payload = {};
        let senderType = 'bot';

        if (!isInitialGreeting && messageText.startsWith('? ')) {
            endpoint = '/explain';
            payload = { query: messageText.substring(2).trim() };
            senderType = 'teacher';
        } else {
            endpoint = '/chat';
            payload = { message: messageText, session_id: currentSessionId };
            senderType = 'bot';
        }

        console.log(`Sending fetch request to: ${API_BASE_URL + endpoint}`);
        try {
            const response = await fetch(API_BASE_URL + endpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });

            console.log(`Received response status: ${response.status}`);

            if (!response.ok) {
                const errorData = await response.text();
                console.error('Server Error:', response.status, errorData);
                addMessage(`Server Error: ${response.status}. Check server logs.`, 'status');
                updateStatus('error');
            } else {
                const data = await response.json();
                console.log("Received data:", data);

                if (endpoint === '/chat' && !currentSessionId && data.session_id) {
                    updateStatus('online');
                    addMessage("Connected!", "status");
                }

                if (endpoint === '/chat') {
                    addMessage(data.reply, senderType);
                    currentSessionId = data.session_id;
                } else if (endpoint === '/explain') {
                    addMessage(data.explanation, senderType, { query: data.query });
                }
            }
        } catch (error) {
            console.error('Network or Fetch Error:', error);
            addMessage('Network Error: Could not reach server.', 'status');
            updateStatus('offline');
        } finally {
            console.log("Request finished, resetting pending state.");
            isRequestPending = false;
            sendButton.disabled = false;
            messageInput.disabled = false;
            if (!isInitialGreeting) {
                messageInput.focus();
            }
        }
    }

    sendButton.addEventListener('click', () => sendMessageToServer(null, false));

    messageInput.addEventListener('keypress', (event) => {
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            sendMessageToServer(null, false);
        }
    });

    messageInput.addEventListener('input', autoResizeTextarea);

    chatMessages.addEventListener('click', function(event) {
        if (event.target && event.target.classList.contains('add-card-button')) {
            handleAddCardClick(event);
        }
    });

    async function initializeChat() {
        console.log("Initializing chat...");
        updateStatus('connecting');

        try {
            console.log("Checking initial connection...");
            const response = await fetch(API_BASE_URL + "/");
            console.log("Initial connection check response status:", response.status);

            if (!response.ok) {
                updateStatus('error');
                console.error("Initial connection check failed.");
                return;
            }

            console.log("Server reachable. Attempting to send initial greeting...");
            await sendMessageToServer("Hola", true);
            console.log("Initial greeting process finished.");

            autoResizeTextarea();
            messageInput.focus();

        } catch (error) {
            console.error('Initialization failed:', error);
            updateStatus('offline');
        }
    }

    initializeChat();
});