// Validation Logic
function setValidation(element, msgEl, ok, message) {
    element.classList.remove('valid', 'invalid');
    msgEl.classList.remove('show', 'success', 'error');
    msgEl.textContent = '';
    if (ok === null) return;
    element.classList.add(ok ? 'valid' : 'invalid');
    msgEl.classList.add('show', ok ? 'success' : 'error');
    msgEl.textContent = message;
}

function clearAllValidation() {
    setValidation(agentApiKeyInput, agentValidation, null, '');
    setValidation(graphApiKeyInput, graphValidation, null, '');
    setValidation(conversationApiKeyInput, conversationValidation, null, '');
}

async function validateKey(inputEl, msgEl) {
    const apiKey = (inputEl.value || '').trim();
    if (!apiKey) {
        setValidation(inputEl, msgEl, null, '');
        return false;
    }

    inputEl.classList.remove('valid', 'invalid');
    msgEl.classList.add('show');
    msgEl.classList.remove('success', 'error');
    msgEl.textContent = 'Validating…';
    msgEl.style.color = 'var(--text-tertiary)';

    try {
        const res = await fetch('/api/validate-api-key', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ provider: providerSelect.value, api_key: apiKey })
        });
        const data = await res.json();
        msgEl.style.color = '';

        if (data && data.valid) {
            setValidation(inputEl, msgEl, true, '✓ Valid');
            return true;
        }
        setValidation(inputEl, msgEl, false, '✗ Invalid API key');
        return false;
    } catch (_) {
        msgEl.style.color = '';
        setValidation(inputEl, msgEl, false, '✗ Validation failed');
        return false;
    }
}

async function validateAllKeys() {
    const a = await validateKey(agentApiKeyInput, agentValidation);
    const g = await validateKey(graphApiKeyInput, graphValidation);
    const c = await validateKey(conversationApiKeyInput, conversationValidation);
    return a && g && c;
}

function collectSettings() {
    return {
        provider: providerSelect.value,
        agent_api_key: (agentApiKeyInput.value || '').trim(),
        graph_api_key: (graphApiKeyInput.value || '').trim(),
        conversation_api_key: (conversationApiKeyInput.value || '').trim(),
        agent_model: (agentModelInput.value || '').trim() || null,
        graph_model: (graphModelInput.value || '').trim() || null,
        conversation_model: (conversationModelInput.value || '').trim() || null,
    };
}
