// Event Handlers
composer.addEventListener('input', function () {
    this.style.height = 'auto';
    this.style.height = Math.min(this.scrollHeight, 200) + 'px';
});

composer.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        if (!sendBtn.disabled) sendMessage();
    }
});

sendBtn.addEventListener('click', sendMessage);

openSettingsBtn.addEventListener('click', () => {
    settingsModal.classList.remove('hidden');
    // Update button text based on session state
    const btnText = document.getElementById('startChatBtnText');
    if (btnText) {
        btnText.textContent = sessionActive ? 'Save Settings' : 'Start Chat';
    }
});

// Close modal button
const closeModalBtn = document.getElementById('closeModal');
if (closeModalBtn) {
    closeModalBtn.addEventListener('click', () => {
        settingsModal.classList.add('hidden');
    });
}

// Close modal when clicking outside
settingsModal.addEventListener('click', (e) => {
    if (e.target === settingsModal) {
        settingsModal.classList.add('hidden');
    }
});

resetBtn.addEventListener('click', async () => {
    const ok = confirm('Reset conversation? This clears chat history and agent memory. Settings will be preserved.');
    if (!ok) return;
    try {
        const res = await fetch('/api/reset-session', { method: 'POST' });
        const data = await res.json();
        if (!data || !data.success) {
            renderError(data && data.error ? data.error : 'Failed to reset session.');
            return;
        }
    } catch (_) {
        renderError('Failed to reset session.');
        return;
    }

    // Clear chat but keep settings
    messagesWrap.innerHTML = '';
    composer.value = '';
    composer.style.height = 'auto';
    isProcessing = false;
    hasShownWelcome = false;
    
    // Show welcome message after reset
    renderAssistant("Session reset. I'm ready for new questions!");
});
