// Inside static/script.js

document.addEventListener('DOMContentLoaded', () => {
    const messageInput = document.getElementById('message-input'); // This is the <textarea>
    const sendButton = document.getElementById('send-button');
    const chatMessages = document.getElementById('chat-messages');
    const statusIndicator = document.getElementById('status-indicator');

    const API_BASE_URL = 'https://ankixparlai-380281608527.europe-southwest1.run.app/'; // Your Cloud Run URL
    let currentSessionId = null;
    let isRequestPending = false;

    // --- addMessage Function (no changes needed) ---
    function addMessage(text, sender) {
        const messageDiv = document.createElement('div');
        messageDiv.classList.add('message', sender);
        messageDiv.textContent = text;
        chatMessages.appendChild(messageDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    // --- updateStatus Function (no changes needed) ---
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

    // --- vvv NEW FUNCTION: Auto-resize Textarea vvv ---
    function autoResizeTextarea() {
        // Reset height to auto first to get the correct scrollHeight
        messageInput.style.height = 'auto';
        // Set the height to the scroll height (content height)
        // Add a pixel or two buffer if needed, but scrollHeight usually works well
        messageInput.style.height = messageInput.scrollHeight + 'px';
    }
    // --- ^^^ NEW FUNCTION ^^^ ---

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
            messageInput.value = ''; // Clear the textarea
            // --- vvv CALL RESIZE AFTER CLEARING vvv ---
            autoResizeTextarea(); // Reset height after sending/clearing
            // --- ^^^ CALL RESIZE AFTER CLEARING ^^^ ---
        } else {
            addMessage("Starting conversation...", "status");
        }

        let endpoint = '';
        let payload = {};
        let senderType = 'bot';

        // --- Check for explain command FIRST --- (Corrected logic slightly)
        if (!isInitialGreeting && messageText.startsWith('? ')) {
            endpoint = '/explain';
            payload = { query: messageText.substring(2).trim() };
            senderType = 'teacher';
        } else { // Default to chat
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
                    addMessage(data.explanation, senderType);
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

    // --- Event Listeners ---
    sendButton.addEventListener('click', () => sendMessageToServer(null, false));

    // --- vvv MODIFIED keypress listener vvv ---
    // Listen for keypress to handle Enter/Shift+Enter
    messageInput.addEventListener('keypress', (event) => {
        // Send message on Enter press ONLY if Shift key is NOT held down
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault(); // Prevent default action (newline insertion)
            sendMessageToServer(null, false); // Trigger send message
        }
        // If Shift+Enter, default action (newline) is allowed
    });
    // --- ^^^ MODIFIED keypress listener ^^^ ---

    // --- vvv ADD INPUT LISTENER FOR RESIZING vvv ---
    // Listen for input to resize textarea automatically
    messageInput.addEventListener('input', autoResizeTextarea);
    // --- ^^^ ADD INPUT LISTENER FOR RESIZING ^^^ ---


    // --- Initial Setup Function ---
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

            // --- vvv CALL RESIZE INITIALLY vvv ---
            autoResizeTextarea(); // Set initial height correctly
            // --- ^^^ CALL RESIZE INITIALLY ^^^ ---
            messageInput.focus(); // Focus input after initial sequence

        } catch (error) {
            console.error('Initialization failed:', error);
            updateStatus('offline');
        }
    }

    // --- Start Initialization ---
    initializeChat();

}); // End DOMContentLoaded