// Inside static/script.js

document.addEventListener('DOMContentLoaded', () => {
    // ... (get elements: messageInput, sendButton, chatMessages, statusIndicator) ...
    const messageInput = document.getElementById('message-input');
    const sendButton = document.getElementById('send-button');
    const chatMessages = document.getElementById('chat-messages');
    const statusIndicator = document.getElementById('status-indicator');

    // ... (API_BASE_URL, currentSessionId, isRequestPending) ...
    const API_BASE_URL = 'https://ankixparlai-380281608527.europe-southwest1.run.app/'; // Use your correct IP/Port
    let currentSessionId = null;
    let isRequestPending = false;


    // ... (addMessage function remains the same) ...
    function addMessage(text, sender) {
        const messageDiv = document.createElement('div');
        messageDiv.classList.add('message', sender);
        messageDiv.textContent = text;
        chatMessages.appendChild(messageDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    // ... (updateStatus function remains the same) ...
    function updateStatus(status) {
        switch(status) {
            case 'online':
                statusIndicator.textContent = '🟢';
                statusIndicator.title = 'Connected';
                // Don't add connected message here, wait for successful greeting
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

    // Function to send message or query to backend
    // Make this function explicitly async
    async function sendMessageToServer(messageText, isInitialGreeting = false) {
        // --- vvv Add check for isRequestPending at the very start vvv ---
        if (isRequestPending) {
            console.warn("Request already pending, skipping send."); // Use warn
            return; // Prevent concurrent sends robustly
        }
        // --- ^^^ ---

        // If called manually (not initial greeting), get text from input
        if (!isInitialGreeting) {
            messageText = messageInput.value.trim();
            if (!messageText) { // Also check for empty manual message here
                 return;
             }
        } else if (messageText === null || messageText === undefined) {
            // Guard against null/undefined for initial greeting if logic changes
            console.error("Initial greeting message text is invalid.");
            return;
        }


        isRequestPending = true; // Set pending flag
        sendButton.disabled = true;
        messageInput.disabled = true;

        if (!isInitialGreeting) {
            addMessage(messageText, 'user');
            messageInput.value = '';
        } else {
            addMessage("Starting conversation...", "status");
        }

        let endpoint = '';
        let payload = {};
        let senderType = 'bot'; // Default reply type

        if (!isInitialGreeting && messageText.startsWith('? ')) {
            endpoint = '/explain';
            payload = { query: messageText.substring(2).trim() };
            senderType = 'teacher';
        } else {
            endpoint = '/chat';
            payload = { message: messageText, session_id: currentSessionId };
            senderType = 'bot';
        }

        console.log(`Sending fetch request to: ${API_BASE_URL + endpoint}`); // Keep useful logs
        try {
            // No need to update status to online here, wait for success

            const response = await fetch(API_BASE_URL + endpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });

            console.log(`Received response status: ${response.status}`); // Log status

            if (!response.ok) {
                const errorData = await response.text();
                console.error('Server Error:', response.status, errorData);
                addMessage(`Server Error: ${response.status}. Check server logs.`, 'status');
                updateStatus('error'); // Set error status *after* failed request
            } else {
                const data = await response.json();
                console.log("Received data:", data); // Log received data

                // If this was the first successful chat message, set status to online
                if (endpoint === '/chat' && !currentSessionId && data.session_id) {
                    updateStatus('online'); // Set status only on first success
                    addMessage("Connected!", "status"); // Add connected message now
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
            updateStatus('offline'); // Set offline status on network error
        } finally {
            console.log("Request finished, resetting pending state."); // Log finish
            isRequestPending = false; // Reset pending flag
            sendButton.disabled = false;
            messageInput.disabled = false;
            if (!isInitialGreeting) {
                messageInput.focus();
            }
        }
    }

    // --- Event Listeners --- (Remain the same)
    sendButton.addEventListener('click', () => sendMessageToServer(null, false));
    messageInput.addEventListener('keypress', (event) => {
        if (event.key === 'Enter') {
            sendMessageToServer(null, false);
        }
    });

    // --- Initial Setup Function using async/await ---
    async function initializeChat() {
        console.log("Initializing chat...");
        updateStatus('connecting'); // Initial status

        try {
            // 1. Check server availability
            console.log("Checking initial connection...");
            const response = await fetch(API_BASE_URL + "/");
            console.log("Initial connection check response status:", response.status);

            if (!response.ok) {
                updateStatus('error');
                console.error("Initial connection check failed.");
                return; // Stop initialization if server check fails
            }

            // 2. Server is reachable, now send the initial greeting message
            console.log("Server reachable. Attempting to send initial greeting...");
            // Use await here to ensure this completes before allowing user input fully
            await sendMessageToServer("Hola", true);
            console.log("Initial greeting process finished.");
            messageInput.focus(); // Focus input only after initial greeting sequence

        } catch (error) {
            console.error('Initialization failed:', error);
            updateStatus('offline');
        }
    }

    // --- Start Initialization ---
    initializeChat();

}); // End DOMContentLoaded