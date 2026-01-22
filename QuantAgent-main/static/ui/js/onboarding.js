// Onboarding and Settings Management

// DOM elements
const startChatBtn = document.getElementById('startChatBtn');
const modalTitle = document.getElementById('modalTitle');

// Provider and model selects
const agentProviderSelect = document.getElementById('agentProvider');
const graphProviderSelect = document.getElementById('graphProvider');
const conversationProviderSelect = document.getElementById('conversationProvider');
const agentModelSelect = document.getElementById('agentModel');
const graphModelSelect = document.getElementById('graphModel');
const conversationModelSelect = document.getElementById('conversationModel');

// API key inputs
const agentApiKeyInput = document.getElementById('agentApiKey');
const graphApiKeyInput = document.getElementById('graphApiKey');
const conversationApiKeyInput = document.getElementById('conversationApiKey');

// Initialize onboarding
function initOnboarding() {
    // Navigation button listener
    startChatBtn.addEventListener('click', handleStartChat);
}

// Handle "Start Chat" button click
async function handleStartChat() {
    // Clear previous errors
    clearValidationErrors();
    
    // Validate all fields
    const validation = validateAllFields();
    if (!validation.valid) {
        showValidationError(validation.message);
        return;
    }
    
    // Show loading state
    startChatBtn.disabled = true;
    startChatBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Validating...';
    
    // Validate all API keys
    const apiValidation = await validateAllApiKeys();
    
    if (!apiValidation.valid) {
        startChatBtn.disabled = false;
        startChatBtn.innerHTML = '<i class="fa-solid fa-rocket"></i> Start Chat';
        return;
    }
    
    // All validations passed
    await startSession();
    
    // Reset button
    startChatBtn.disabled = false;
    startChatBtn.innerHTML = '<i class="fa-solid fa-rocket"></i> Start Chat';
}

// Validate all required fields
function validateAllFields() {
    const fields = [
        { name: 'Agent Provider', element: agentProviderSelect },
        { name: 'Agent API Key', element: agentApiKeyInput },
        { name: 'Graph Provider', element: graphProviderSelect },
        { name: 'Graph API Key', element: graphApiKeyInput },
        { name: 'Conversation Provider', element: conversationProviderSelect },
        { name: 'Conversation API Key', element: conversationApiKeyInput }
    ];
    
    for (const field of fields) {
        if (!field.element.value.trim()) {
            field.element.style.borderColor = '#dc3545';
            return {
                valid: false,
                message: `Please fill all required fields: ${field.name} is empty`
            };
        }
    }
    
    return { valid: true };
}

// Validate all API keys
async function validateAllApiKeys() {
    const validations = [
        { provider: agentProviderSelect.value, apiKey: agentApiKeyInput.value, name: 'Agent', input: agentApiKeyInput, messageEl: 'agentValidation' },
        { provider: graphProviderSelect.value, apiKey: graphApiKeyInput.value, name: 'Graph', input: graphApiKeyInput, messageEl: 'graphValidation' },
        { provider: conversationProviderSelect.value, apiKey: conversationApiKeyInput.value, name: 'Conversation', input: conversationApiKeyInput, messageEl: 'conversationValidation' }
    ];
    
    let allValid = true;
    
    for (const validation of validations) {
        const result = await validateApiKey(validation.provider, validation.apiKey);
        
        if (!result.valid) {
            allValid = false;
            validation.input.style.borderColor = '#dc3545';
            const messageEl = document.getElementById(validation.messageEl);
            if (messageEl) {
                messageEl.textContent = `${validation.name} API not valid: ${result.error}`;
                messageEl.style.color = '#dc3545';
                messageEl.style.display = 'block';
            }
        } else {
            validation.input.style.borderColor = '#28a745';
            const messageEl = document.getElementById(validation.messageEl);
            if (messageEl) {
                messageEl.textContent = `${validation.name} API validated successfully`;
                messageEl.style.color = '#28a745';
                messageEl.style.display = 'block';
            }
        }
    }
    
    return { valid: allValid };
}

// Validate single API key
async function validateApiKey(provider, apiKey) {
    try {
        const response = await fetch('/api/validate-api-key', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ provider, api_key: apiKey })
        });
        
        const data = await response.json();
        return data;
    } catch (error) {
        return { valid: false, error: 'Network error' };
    }
}

// Clear validation errors
function clearValidationErrors() {
    [agentApiKeyInput, graphApiKeyInput, conversationApiKeyInput].forEach(input => {
        input.style.borderColor = '';
    });
    
    ['agentValidation', 'graphValidation', 'conversationValidation'].forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.textContent = '';
            el.style.display = 'none';
        }
    });
}

// Show validation error message
function showValidationError(message) {
    alert(message);
}

// Collect settings from all pages
function collectOnboardingSettings() {
    return {
        agent: {
            provider: agentProviderSelect.value || 'openai',
            api_key: agentApiKeyInput.value.trim(),
            model: agentModelSelect.value || ''
        },
        graph: {
            provider: graphProviderSelect.value || 'openai',
            api_key: graphApiKeyInput.value.trim(),
            model: graphModelSelect.value || ''
        },
        conversation: {
            provider: conversationProviderSelect.value || 'openai',
            api_key: conversationApiKeyInput.value.trim(),
            model: conversationModelSelect.value || ''
        }
    };
}

// Start session with configured settings
async function startSession() {
    const settings = collectOnboardingSettings();
    
    // Use defaults if not configured
    const config = {
        agent_api_key: settings.agent.api_key || null,
        agent_provider: settings.agent.provider || 'openai',
        agent_model: settings.agent.model || null,
        graph_api_key: settings.graph.api_key || null,
        graph_provider: settings.graph.provider || 'openai',
        graph_model: settings.graph.model || null,
        conversation_api_key: settings.conversation.api_key || null,
        conversation_provider: settings.conversation.provider || 'openai',
        conversation_model: settings.conversation.model || null
    };
    
    // Store settings for API calls
    pendingSettings = config;
    
    // If this is initial setup
    if (!sessionActive) {
        sessionActive = true;
        composer.disabled = false;
        sendBtn.disabled = false;
        
        // Show chat interface
        document.querySelector('.app').classList.remove('hidden');
        
        composer.focus();
        
        if (!hasShownWelcome) {
            renderAssistant("Hello! I'm PaisaPhile. Ask me real market questions — trends, patterns, indicators, or price checks.");
            hasShownWelcome = true;
        }
    }
    
    // Close modal
    settingsModal.classList.add('hidden');
    
    // Update button text for next time
    const btnText = document.getElementById('startChatBtnText');
    if (btnText && sessionActive) {
        btnText.textContent = 'Save Settings';
    }
}

// Reset onboarding form
function resetOnboarding() {
    agentProviderSelect.value = '';
    graphProviderSelect.value = '';
    conversationProviderSelect.value = '';
    agentApiKeyInput.value = '';
    graphApiKeyInput.value = '';
    conversationApiKeyInput.value = '';
    agentModelSelect.value = '';
    graphModelSelect.value = '';
    conversationModelSelect.value = '';
}

// Initialize when DOM is loaded
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initOnboarding);
} else {
    initOnboarding();
}