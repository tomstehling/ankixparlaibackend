// static/script.js (CORRECTED)

document.addEventListener('DOMContentLoaded', () => {
    // --- UI Element References ---
    const chatMessages = document.getElementById('chat-messages');
    const messagesContainer = document.getElementById('messages-container');
    const explanationBox = document.getElementById('explanation-box');
    const explanationTextArea = document.getElementById('explanation-text-area');
    const explanationActions = document.getElementById('explanation-actions');
    const messageInput = document.getElementById('message-input');
    const sendButton = document.getElementById('send-button');
    const statusIndicator = document.getElementById('status-indicator');

    // --- Modal Elements ---
    const modal = document.getElementById('card-creator-modal');
    const modalCloseBtn = document.getElementById('modal-close-btn');
    const modalCancelBtn = document.getElementById('modal-cancel-button');
    const modalTargetWord = document.getElementById('modal-target-word'); // Display only
    const modalProposedSpanish = document.getElementById('modal-proposed-spanish'); // Display only
    const modalProposedEnglish = document.getElementById('modal-proposed-english'); // Display only
    const modalUserSpanishInput = document.getElementById('modal-user-spanish-input');
    const modalUserEnglishInput = document.getElementById('modal-user-english-input');
    const modalAcceptProposalBtn = document.getElementById('modal-accept-proposal-btn');
    const modalSubmitSpanishBtn = document.getElementById('modal-submit-spanish-btn');
    const modalSubmitEnglishBtn = document.getElementById('modal-submit-english-btn');
    const modalStepProposeInput = document.getElementById('modal-step-propose-input');
    const modalStepValidation = document.getElementById('modal-step-validation');
    const modalStepSave = document.getElementById('modal-step-save');
    const modalFinalSpanish = document.getElementById('modal-final-spanish'); // Display only
    const modalFinalEnglish = document.getElementById('modal-final-english'); // Display only
    const modalFeedback = document.getElementById('modal-feedback'); // Display only
    const modalValidityStatus = document.getElementById('modal-validity-status'); // Display only
    const modalTagsInput = document.getElementById('modal-tags-input');
    const modalSaveButton = document.getElementById('modal-save-button');
    const modalStatusMessage = document.getElementById('modal-status-message');
    const modalFallbackProposeBtn = document.getElementById('modal-fallback-propose-btn');

    // --- State Variables ---
    const API_BASE_URL = ''; // Same-origin
    let currentSessionId = null;
    let isRequestPending = false;
    let cardCreatorState = {}; // Stores modal-specific temporary data

    // ========================================================================
    // Helper Functions (UI Updates)
    // ========================================================================

    function addMessage(text, sender) {
        if (!messagesContainer) { console.error("Messages container not found!"); return; }
        const messageDiv = document.createElement('div');
        messageDiv.classList.add('message', sender); // user, bot, status
        // Basic Markdown-like formatting
        let formattedMessage = text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>'); // Bold
        formattedMessage = formattedMessage.replace(/\*(.*?)\*/g, '<em>$1</em>');     // Italics
        formattedMessage = formattedMessage.replace(/\n/g, '<br>');               // Newlines
        messageDiv.innerHTML = formattedMessage;
        messagesContainer.appendChild(messageDiv);
        // Scroll to bottom
        if (chatMessages) {
            requestAnimationFrame(() => { chatMessages.scrollTop = chatMessages.scrollHeight; });
        }
    }

    // *** Handles structured explanation response ***
    const showExplanation = (explanationData) => {
        if (!explanationBox || !explanationTextArea || !explanationActions) {
            console.error("Required explanation elements not found!");
            addMessage("Error: Could not display explanation (UI elements missing).", "status");
            return;
        }
        // Ensure data is valid (basic check)
        if (!explanationData || typeof explanationData.explanation_text !== 'string' || typeof explanationData.topic !== 'string') {
            console.error("Invalid explanation data received:", explanationData);
            addMessage("Error: Received invalid explanation data from server.", "status");
            hideExplanation(); // Hide the box if data is bad
            return;
        }

        const { explanation_text, topic, example_spanish, example_english } = explanationData;

        // 1. Display Explanation Text
        let formattedExplanation = explanation_text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
        formattedExplanation = formattedExplanation.replace(/\*(.*?)\*/g, '<em>$1</em>');
        formattedExplanation = formattedExplanation.replace(/\n/g, '<br>');
        explanationTextArea.innerHTML = `<strong>Explanation for "${topic}":</strong><br>${formattedExplanation}`;

        // 2. Clear previous actions and create "Add Flashcard" button
        explanationActions.innerHTML = ''; // Clear any old button before adding new one
        const addButton = document.createElement('button');
        addButton.id = 'dynamic-add-card-btn'; // Give it an ID if needed
        addButton.textContent = `✨ Add Flashcard for "${topic}"`;
        addButton.classList.add('add-card-from-explanation-btn'); // Add class for styling

        // 3. Attach data needed by the modal to the button
        addButton.dataset.topic = topic;
        addButton.dataset.exampleEs = example_spanish || ''; // Use empty string if null/undefined
        addButton.dataset.exampleEn = example_english || ''; // Use empty string if null/undefined

        // 4. Add event listener to the button
        addButton.addEventListener('click', handleCreateCardFromExplanation);

        // 5. Append button and show explanation box
        explanationActions.appendChild(addButton);
        explanationBox.style.display = 'block'; // Make the box visible

        // Scroll down to ensure it's seen
        if(chatMessages) {
             requestAnimationFrame(() => { chatMessages.scrollTop = chatMessages.scrollHeight; });
        }
    };

    // *** CORRECTED: Only hide the box, don't destroy inner elements ***
    const hideExplanation = () => {
        if (explanationBox) {
             explanationBox.style.display = 'none';
             // DO NOT clear innerHTML here. Let showExplanation manage content.
        }
    };

    function updateStatus(status) {
        if (!statusIndicator) return;
        switch (status) {
            case 'online': statusIndicator.textContent = '🟢'; statusIndicator.title = 'Connected'; break;
            case 'error': statusIndicator.textContent = '🟠'; statusIndicator.title = 'Connection Error'; break;
            case 'offline': statusIndicator.textContent = '🔴'; statusIndicator.title = 'Offline'; break;
            case 'connecting': // Added connecting state explicitly
            default: statusIndicator.textContent = '⚪'; statusIndicator.title = 'Connecting...';
        }
    }

    function autoResizeTextarea() {
        if (!messageInput) return;
        messageInput.style.height = 'auto'; // Temporarily shrink to get scrollHeight
        const maxHeight = parseInt(window.getComputedStyle(messageInput).maxHeight, 10) || 100; // Example max height
        let newHeight = messageInput.scrollHeight;
        if (maxHeight && newHeight > maxHeight) {
            newHeight = maxHeight;
            messageInput.style.overflowY = 'auto'; // Allow scrolling if max height reached
        } else {
            messageInput.style.overflowY = 'hidden'; // Hide scrollbar if not needed
        }
        messageInput.style.height = newHeight + 'px';
    }

    const getLastBotMessage = () => {
        if (!messagesContainer) return null;
        const botMessages = messagesContainer.querySelectorAll('.message.bot');
        if (botMessages.length > 0) {
            // Try to get innerHTML to preserve formatting if needed, fallback to innerText
            return botMessages[botMessages.length - 1].innerHTML || botMessages[botMessages.length - 1].innerText;
        }
        return null;
    };

    const clearChat = () => {
        if (messagesContainer) messagesContainer.innerHTML = '';
        hideExplanation();
        currentSessionId = null; // Reset session
        console.log("Chat cleared and session reset.");
        addMessage("Chat cleared. Session reset.", "status");
        // Optionally send a new greeting or reset state further
    };

    // ========================================================================
    // Main Send Message Logic (Handles Chat & Explanations)
    // ========================================================================

    const sendMessage = async (initialGreeting = null) => {
        if (isRequestPending) { console.warn("Request already pending."); return; }
        if (!messageInput || !sendButton) { console.error("Cannot send message: Input or Send button missing."); return; }

        let message;
        if (initialGreeting !== null) {
            message = initialGreeting; // Use provided greeting
            // Don't add initial greeting to chat UI here, wait for response
        } else {
            message = messageInput.value.trim();
            if (!message) return; // Don't send empty messages
            addMessage(message, 'user');
            messageInput.value = ''; // Clear input AFTER sending
            autoResizeTextarea(); // Resize after clearing
        }

        hideExplanation(); // Always hide previous explanation before sending new message

        isRequestPending = true;
        if (sendButton) sendButton.disabled = true;
        if (messageInput) messageInput.disabled = true;
        addMessage("...", "bot"); // Placeholder for bot response

        let endpoint;
        let body;
        let isExplanationQuery = false;

        // Determine endpoint based on message content (only if not initial greeting)
        if (initialGreeting === null && message.startsWith('?')) {
            isExplanationQuery = true;
            endpoint = `${API_BASE_URL}/explain`;
            const topic = message.substring(1).trim();
            if (!topic) {
                 addMessage("Please provide a topic after the '?'. Usage: `? [topic]`", "status");
                 isRequestPending = false;
                 if (sendButton) sendButton.disabled = false;
                 if (messageInput) messageInput.disabled = false;
                 // Remove placeholder message
                 const placeholder = messagesContainer?.querySelector('.message.bot:last-child');
                 if (placeholder?.textContent === '...') placeholder.remove();
                 return;
            }
            body = { topic: topic, context: getLastBotMessage() };
        } else {
            endpoint = `${API_BASE_URL}/chat`;
            body = { message: message, session_id: currentSessionId };
        }

        console.log(`Sending to ${endpoint}:`, body);

        try {
            const response = await fetch(endpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            console.log(`Received response status: ${response.status}`);

            // Remove placeholder message regardless of success/error
            const placeholder = messagesContainer?.querySelector('.message.bot:last-child');
            if (placeholder?.textContent === '...') placeholder.remove();

            if (!response.ok) {
                let errorDetail = `Server error ${response.status}`;
                try { const errorData = await response.json(); errorDetail = errorData.detail || errorDetail; }
                catch (e) { /* Ignore JSON parsing error if body is empty */ }
                throw new Error(errorDetail);
            }

            const data = await response.json();
            console.log("Received data:", data);

            // Handle Session ID (Important for subsequent chat calls)
            if (data.session_id && data.session_id !== currentSessionId) {
                 currentSessionId = data.session_id;
                 console.log("Session ID updated:", currentSessionId);
                 // Update status if it was 'connecting'
                 if(statusIndicator && statusIndicator.textContent === '⚪') {
                    updateStatus('online');
                    if (initialGreeting !== null) addMessage("Connected! Chat ready.", "status"); // Status msg only on initial connect
                 }
            }

            // Handle Response Type (Explanation or Chat Reply)
            if (isExplanationQuery) {
                // Pass the entire structured data object to showExplanation
                showExplanation(data);
                // Optionally add a small confirmation message to the chat
                // addMessage(`Got explanation for "${data.topic}". See details below.`, "status");
            } else {
                // Add regular chat reply
                if (data.reply) { addMessage(data.reply, 'bot'); }
                else { addMessage("Received an empty response.", "status"); }
            }
             if (statusIndicator?.textContent !== '🟢') updateStatus('online'); // Mark as online on successful message

        } catch (error) {
            console.error('Error during fetch:', error);
            // Ensure placeholder is removed if it wasn't already
            const placeholder = messagesContainer?.querySelector('.message.bot:last-child');
            if (placeholder?.textContent === '...') placeholder.remove();

            addMessage(`Error: ${error.message}`, 'status');
            if (error.message.includes('Failed to fetch') || error.message.includes('NetworkError')) {
                updateStatus('offline');
            } else {
                updateStatus('error'); // General server/network error
            }
        } finally {
            isRequestPending = false;
            if (sendButton) sendButton.disabled = false;
            if (messageInput) messageInput.disabled = false;
            // Only refocus if it wasn't the initial greeting load
            if (initialGreeting === null && messageInput) {
                 messageInput.focus();
            }
        }
    };

    // ========================================================================
    // Card Creator Modal Functions
    // ========================================================================

    const resetModalState = () => {
        cardCreatorState = {}; // Clear temporary data
        // Clear display elements
        if (modalTargetWord) modalTargetWord.textContent = '';
        if (modalProposedSpanish) modalProposedSpanish.textContent = '...';
        if (modalProposedEnglish) modalProposedEnglish.textContent = '...';
        if (modalFinalSpanish) modalFinalSpanish.textContent = '';
        if (modalFinalEnglish) modalFinalEnglish.textContent = '';
        if (modalFeedback) modalFeedback.textContent = '';
        if (modalValidityStatus) modalValidityStatus.textContent = '';
        // Clear input elements
        if (modalUserSpanishInput) modalUserSpanishInput.value = '';
        if (modalUserEnglishInput) modalUserEnglishInput.value = '';
        if (modalTagsInput) modalTagsInput.value = '';
        // Reset status message
        if (modalStatusMessage) { modalStatusMessage.textContent = ''; modalStatusMessage.className = 'modal-status'; }
        // Reset step visibility
        if (modalStepProposeInput) modalStepProposeInput.classList.remove('hidden');
        if (modalStepValidation) modalStepValidation.classList.add('hidden');
        if (modalStepSave) modalStepSave.classList.add('hidden');
        // Reset button states
        if (modalSaveButton) modalSaveButton.disabled = false;
        if (modalFallbackProposeBtn) {
            modalFallbackProposeBtn.classList.add('hidden'); // Hide by default
            modalFallbackProposeBtn.disabled = false; // Re-enable
        }
        console.log("Modal state reset.");
    };

    const openCardCreatorModal = () => {
        if (!modal) { console.error("Modal element not found!"); return; }
        resetModalState(); // Ensure modal is clean before opening
        modal.classList.remove('hidden');
        console.log("Modal opened.");
    };

    const closeCardCreatorModal = () => {
        if (!modal) { console.error("Modal element not found!"); return; }
        modal.classList.add('hidden');
        resetModalState(); // Clean up after closing
        console.log("Modal closed.");
    };

    // Helper to display status messages inside the modal
    const showModalStatus = (message, isError = false) => {
         if (!modalStatusMessage) { console.warn("Modal status message element not found."); return; }
         modalStatusMessage.textContent = message;
         modalStatusMessage.className = `modal-status ${isError ? 'error' : 'success'}`;
    }

    // Renamed for clarity, now used as fallback IF needed by handleCreateCardFromExplanation
    const fetchAndPopulateProposal = async (targetWord) => {
        if (!modalTargetWord || !modalProposedSpanish || !modalProposedEnglish || !modalUserSpanishInput || !modalUserEnglishInput) {
             console.error("Modal elements missing for proposal fetch.");
             showModalStatus("Modal UI error (missing elements).", true);
             if (modalFallbackProposeBtn) modalFallbackProposeBtn.disabled = false; // Re-enable if UI error
             return;
        }
        // Show loading state specifically for proposal area
        modalProposedSpanish.textContent = 'Generating suggestion...';
        modalProposedEnglish.textContent = ''; // Clear english part
        showModalStatus('Requesting sentence suggestion...'); // General status

        try {
            const response = await fetch(`${API_BASE_URL}/propose_sentence`, {
                 method: 'POST',
                 headers: { 'Content-Type': 'application/json' },
                 body: JSON.stringify({ target_word: targetWord })
            });
            if (!response.ok) {
                 let errorDetail = `Server error ${response.status}`;
                 try { const errorData = await response.json(); errorDetail = errorData.detail || errorDetail; }
                 catch (e) { /* Ignore */ }
                 throw new Error(errorDetail);
            }
            const data = await response.json();
            console.log("Proposal received (fallback):", data);

            if (!data.proposed_spanish || !data.proposed_english) {
                throw new Error("Suggestion received but content is missing.");
            }

            // Store and display proposal
            cardCreatorState.proposedSpanish = data.proposed_spanish;
            cardCreatorState.proposedEnglish = data.proposed_english;
            modalProposedSpanish.textContent = data.proposed_spanish;
            modalProposedEnglish.textContent = data.proposed_english;

            // Pre-fill user input for easier editing/acceptance
            modalUserSpanishInput.value = data.proposed_spanish;
            modalUserEnglishInput.value = ''; // Keep user english empty unless they type

            if (modalFallbackProposeBtn) modalFallbackProposeBtn.classList.add('hidden'); // Hide fallback btn after success
            showModalStatus('Suggestion loaded.', false); // Clear loading status

        } catch (error) {
            console.error("Error fetching sentence proposal (fallback):", error);
            modalProposedSpanish.textContent = 'Error loading suggestion.';
            modalProposedEnglish.textContent = '';
            showModalStatus(`Error getting suggestion: ${error.message}`, true);
             if (modalFallbackProposeBtn) modalFallbackProposeBtn.disabled = false; // Re-enable button on failure
        }
    };

     // Handles clicking "Accept Suggestion" button
     const handleAcceptProposal = () => {
        console.log("Accept Proposal clicked");
        if (!cardCreatorState.proposedSpanish || !cardCreatorState.proposedEnglish) {
            showModalStatus("Cannot accept suggestion - data missing.", true);
            return;
        }
        if (!modalFinalSpanish || !modalFinalEnglish || !modalFeedback || !modalValidityStatus || !modalStepValidation || !modalStepSave || !modalStepProposeInput) {
            console.error("Modal elements missing for accept proposal action.");
            showModalStatus("Modal UI Error (missing elements).", true);
            return;
        }

        // Directly use the proposed sentences as final
        cardCreatorState.finalSpanish = cardCreatorState.proposedSpanish;
        cardCreatorState.finalEnglish = cardCreatorState.proposedEnglish;

        // Update the UI for the final step
        modalFinalSpanish.textContent = cardCreatorState.finalSpanish;
        modalFinalEnglish.textContent = cardCreatorState.finalEnglish;
        modalFeedback.textContent = "Using suggested sentence pair."; // Provide clear feedback
        modalValidityStatus.textContent = "Accepted"; // Indicate status

        // Show validation/save steps, hide propose/input step
        modalStepValidation.classList.remove('hidden');
        modalStepSave.classList.remove('hidden');
        modalStepProposeInput.classList.add('hidden');

        showModalStatus(''); // Clear any previous status messages
     };

     // Handles submitting either Spanish (for validation) or English (for translation)
     const callValidateOrTranslate = async (sentence, language) => {
        console.log(`Calling validation/translation for lang=${language}:`, sentence);
        if (!cardCreatorState.targetWord || !sentence) {
            showModalStatus("Missing target word or sentence to process.", true);
            return;
        }
        if (!modalFinalSpanish || !modalFinalEnglish || !modalFeedback || !modalValidityStatus || !modalStepValidation || !modalStepSave || !modalStepProposeInput) {
            console.error("Modal elements missing for validate/translate action.");
            showModalStatus("Modal UI Error (missing elements).", true);
            return;
        }

        const actionText = language === 'es' ? 'Validating' : 'Translating';
        showModalStatus(`Processing (${actionText} sentence)...`, false);

        // Disable buttons during processing? (Optional but good UX)
        // if (modalSubmitSpanishBtn) modalSubmitSpanishBtn.disabled = true;
        // if (modalSubmitEnglishBtn) modalSubmitEnglishBtn.disabled = true;

        try {
            const response = await fetch(`${API_BASE_URL}/validate_translate_sentence`, {
                 method: 'POST',
                 headers: { 'Content-Type': 'application/json' },
                 body: JSON.stringify({
                    target_word: cardCreatorState.targetWord,
                    user_sentence: sentence,
                    language: language
                 })
            });
            if (!response.ok) {
                 let errorDetail = `Server error ${response.status}`;
                 try { const errorData = await response.json(); errorDetail = errorData.detail || errorDetail; }
                 catch (e) { /* Ignore */ }
                 throw new Error(errorDetail);
            }
            const data = await response.json();
            console.log("Validation/Translation response:", data);

            if (!data.final_spanish || !data.final_english) {
                throw new Error("Processing finished but final sentences are missing.");
            }

            // Store final results
            cardCreatorState.finalSpanish = data.final_spanish;
            cardCreatorState.finalEnglish = data.final_english;

            // Update UI with results
            modalFinalSpanish.textContent = data.final_spanish;
            modalFinalEnglish.textContent = data.final_english;
            modalFeedback.innerHTML = data.feedback || '(No specific feedback provided)'; // Use innerHTML for potential formatting
            modalValidityStatus.textContent = data.is_valid ? "Valid / Translated" : "Corrected";

            // Show validation/save steps, hide propose/input step
            modalStepValidation.classList.remove('hidden');
            modalStepSave.classList.remove('hidden');
            modalStepProposeInput.classList.add('hidden');

            showModalStatus(`${actionText} complete. Review and save.`, false);

        } catch (error) {
             console.error("Error validating/translating sentence:", error);
             showModalStatus(`Processing Error: ${error.message}`, true);
        } finally {
             // Re-enable buttons if they were disabled
             // if (modalSubmitSpanishBtn) modalSubmitSpanishBtn.disabled = false;
             // if (modalSubmitEnglishBtn) modalSubmitEnglishBtn.disabled = false;
        }
     };

     // Handles clicking the final "Save Card to DB" button
     const handleSaveCard = async () => {
        console.log("Save Card clicked");
        const spanishFront = cardCreatorState.finalSpanish;
        const englishBack = cardCreatorState.finalEnglish;

        if (!modalTagsInput) { console.error("Tags input element not found!"); return; }
        const tagsRaw = modalTagsInput.value.trim();

        if (!spanishFront || !englishBack) {
            showModalStatus("Cannot save - Final Spanish or English content is missing.", true);
            return;
        }

        // Process tags: split by comma, trim whitespace, filter empty tags
        const tags = tagsRaw ? tagsRaw.split(',').map(tag => tag.trim()).filter(tag => tag) : [];
        console.log("Card details to save:", { front: spanishFront, back: englishBack, tags: tags });

        showModalStatus('Saving card to database...', false);
        if (modalSaveButton) modalSaveButton.disabled = true; // Prevent double-clicks

        try {
            const response = await fetch(`${API_BASE_URL}/save_final_card`, {
                 method: 'POST',
                 headers: { 'Content-Type': 'application/json' },
                 body: JSON.stringify({
                    spanish_front: spanishFront,
                    english_back: englishBack,
                    tags: tags // Send as an array
                 })
            });
            if (!response.ok) {
                 let errorDetail = `Server error ${response.status}`;
                 try { const errorData = await response.json(); errorDetail = errorData.detail || errorDetail; }
                 catch (e) { /* Ignore */ }
                 throw new Error(errorDetail);
            }
            const data = await response.json();
            console.log("Save card response:", data);

            if (data.success && data.card_id) {
                showModalStatus(`Card saved successfully (ID: ${data.card_id})! Closing modal...`, false);
                // Close modal after a short delay
                setTimeout(closeCardCreatorModal, 2500);
            } else {
                // If success is false or card_id is missing, treat as error
                throw new Error(data.message || "Save operation failed on the server.");
            }
        } catch (error) {
             console.error("Error saving card:", error);
             showModalStatus(`Error saving card: ${error.message}`, true);
             if (modalSaveButton) modalSaveButton.disabled = false; // Re-enable button on failure
        }
     };

    // *** NEW: Handler for the dynamic button inside explanation box ***
    const handleCreateCardFromExplanation = (event) => {
        console.log("Add card from explanation button clicked.");
        const button = event.currentTarget; // Use currentTarget for the element the listener is attached to
        const topic = button.dataset.topic;
        const exampleEs = button.dataset.exampleEs; // Will be '' if null/undefined from dataset
        const exampleEn = button.dataset.exampleEn; // Will be '' if null/undefined from dataset

        if (!topic) {
            console.error("Could not get topic from button dataset.");
            alert("Error: Could not determine the word for the flashcard."); // User-facing alert
            return;
        }

        openCardCreatorModal(); // Open and reset the modal first

        // Set target word in state and UI
        cardCreatorState.targetWord = topic;
        if (modalTargetWord) modalTargetWord.textContent = topic; // Update display element

        // Pre-populate if *both* example sentences were provided by /explain
        if (exampleEs && exampleEn) {
            console.log("Pre-populating modal with example:", { spanish: exampleEs, english: exampleEn });
            // Store as proposed state
            cardCreatorState.proposedSpanish = exampleEs;
            cardCreatorState.proposedEnglish = exampleEn;
            // Display the proposed sentences
            if (modalProposedSpanish) modalProposedSpanish.textContent = exampleEs;
            if (modalProposedEnglish) modalProposedEnglish.textContent = exampleEn;
            // Pre-fill the *user input* fields for easy acceptance/editing
            if (modalUserSpanishInput) modalUserSpanishInput.value = exampleEs;
            if (modalUserEnglishInput) modalUserEnglishInput.value = ''; // Keep user english input empty initially

            // Hide the fallback button since we have a suggestion
            if (modalFallbackProposeBtn) modalFallbackProposeBtn.classList.add('hidden');
            showModalStatus("Suggestion from explanation loaded. Accept or edit.", false);

        } else {
            // No examples (or only one) provided by /explain
            console.log("No complete example sentence pair provided by explanation. Modal fields left empty.");
            // Clear proposed state and display areas
            cardCreatorState.proposedSpanish = null;
            cardCreatorState.proposedEnglish = null;
            if (modalProposedSpanish) modalProposedSpanish.textContent = '(No suggestion from explanation)';
            if (modalProposedEnglish) modalProposedEnglish.textContent = '';
            // Ensure user input fields are empty
            if (modalUserSpanishInput) modalUserSpanishInput.value = '';
            if (modalUserEnglishInput) modalUserEnglishInput.value = '';

            // Show the fallback button to allow user to request a suggestion
            if (modalFallbackProposeBtn) modalFallbackProposeBtn.classList.remove('hidden');
            showModalStatus("Enter sentences or request a suggestion.", false);
        }
    };


    // ========================================================================
    // Event Listeners Setup
    // ========================================================================

    // Chat Input / Send
    if (sendButton) {
        sendButton.addEventListener('click', () => sendMessage(null)); // Pass null to indicate user message
    } else { console.error("Send button (#send-button) not found!"); }

    if (messageInput) {
        messageInput.addEventListener('keypress', (event) => {
             // Send on Enter unless Shift+Enter is pressed
             if (event.key === 'Enter' && !event.shiftKey) {
                 event.preventDefault(); // Prevent default newline insertion
                 sendMessage(null); // Pass null to indicate user message
             }
        });
        messageInput.addEventListener('input', autoResizeTextarea); // Auto-resize on input
    } else { console.error("Message input (#message-input) not found!"); }

    // --- Optional Clear Chat Button Listener ---
    // const clearChatButton = document.getElementById('clear-chat-btn'); // Add this to your HTML if needed
    // if (clearChatButton) { clearChatButton.addEventListener('click', clearChat); }

    // Card Creator Modal Actions & Closing
    if (modalCloseBtn) { modalCloseBtn.addEventListener('click', closeCardCreatorModal); }
    else { console.warn("Modal close button (#modal-close-btn) not found."); }

    if (modalCancelBtn) { modalCancelBtn.addEventListener('click', closeCardCreatorModal); }
    else { console.warn("Modal cancel button (#modal-cancel-button) not found."); }

    // Close modal if clicking outside the modal content
    if (modal) {
        modal.addEventListener('click', (event) => {
             if (event.target === modal) { // Check if the click was directly on the backdrop
                 closeCardCreatorModal();
             }
        });
    } else { console.error("Modal container (#card-creator-modal) not found!"); }

    // Connect Modal Step Buttons to Handlers
    if (modalAcceptProposalBtn) { modalAcceptProposalBtn.addEventListener('click', handleAcceptProposal); }
    else { console.warn("Modal accept proposal button not found."); }

    if (modalSubmitSpanishBtn) {
        modalSubmitSpanishBtn.addEventListener('click', () => {
            if (!modalUserSpanishInput) return;
            const userSpanish = modalUserSpanishInput.value.trim();
            if (!userSpanish) { showModalStatus("Please enter your Spanish sentence.", true); return; }
            callValidateOrTranslate(userSpanish, 'es');
        });
    } else { console.warn("Modal submit Spanish button not found."); }

    if (modalSubmitEnglishBtn) {
        modalSubmitEnglishBtn.addEventListener('click', () => {
            if (!modalUserEnglishInput) return;
            const userEnglish = modalUserEnglishInput.value.trim();
            if (!userEnglish) { showModalStatus("Please enter your English sentence for translation.", true); return; }
            callValidateOrTranslate(userEnglish, 'en');
        });
    } else { console.warn("Modal submit English button not found."); }

    if (modalSaveButton) { modalSaveButton.addEventListener('click', handleSaveCard); }
    else { console.warn("Modal save button not found."); }

    // Add Listener for Fallback "Suggest Sentence" Button
    if (modalFallbackProposeBtn) {
         modalFallbackProposeBtn.addEventListener('click', () => {
             if (cardCreatorState.targetWord) {
                 modalFallbackProposeBtn.disabled = true; // Disable while fetching
                 fetchAndPopulateProposal(cardCreatorState.targetWord);
             } else {
                 showModalStatus("Cannot suggest sentence - target word missing from state.", true);
             }
         });
    } else { console.warn("Modal fallback propose button (#modal-fallback-propose-btn) not found."); }


    // ========================================================================
    // Initialization
    // ========================================================================
    async function initializeChat() {
        console.log("Initializing chat...");
        updateStatus('connecting'); // Set initial status
        try {
            // Optional: Check server root path first for quick connectivity test
            console.log(`Checking initial connection to ${API_BASE_URL || '/'}`);
            const rootResponse = await fetch(API_BASE_URL + "/"); // Assuming '/' route exists and returns 2xx
            console.log("Initial connection check response status:", rootResponse.status);
            if (!rootResponse.ok) { throw new Error(`Server check failed: ${rootResponse.status}`); }

            console.log("Server reachable. Sending initial greeting to /chat...");
            await sendMessage("Hola", true); // Send initial greeting, true indicates it's not a user message
            console.log("Initial greeting process finished.");

            autoResizeTextarea(); // Initial resize
            if (messageInput) messageInput.focus(); // Focus input after init

        } catch (error) {
            console.error('Initialization failed:', error);
            updateStatus('offline');
            addMessage(`Initialization Error: Could not connect to the chat service. Please check the connection or try refreshing the page. (${error.message})`, 'status');
            // Disable input if init fails?
            // if(messageInput) messageInput.disabled = true;
            // if(sendButton) sendButton.disabled = true;
        }
    }

    // Start the initialization process when the DOM is ready
    initializeChat();

}); // End DOMContentLoaded