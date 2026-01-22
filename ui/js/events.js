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

if (openSettingsBtn) {
    console.log('✅ Attaching click handler to openSettings button');
    openSettingsBtn.addEventListener('click', () => {
        console.log('🔧 Settings button clicked');
        console.log('   Modal element:', settingsModal);
        console.log('   Modal classes before:', settingsModal?.className);
        
        if (settingsModal) {
            settingsModal.classList.remove('hidden');
            console.log('   Modal classes after:', settingsModal.className);
        } else {
            console.error('❌ settingsModal element not found!');
        }
        
        // Update button text based on session state
        const btnText = document.getElementById('startChatBtnText');
        if (btnText) {
            btnText.textContent = sessionActive ? 'Save Settings' : 'Start Chat';
            console.log('   Button text updated to:', btnText.textContent);
        }
    });
} else {
    console.error('❌ openSettingsBtn not found in DOM!');
}

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

if (resetBtn) {
    console.log('✅ Attaching click handler to reset button');
    resetBtn.addEventListener('click', async () => {
        console.log('🔄 Reset button clicked');
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

        // Clear chat but keep settings (sessionSettings remains intact)
        messagesWrap.innerHTML = '';
        composer.value = '';
        composer.style.height = 'auto';
        isProcessing = false;
        hasShownWelcome = false;
        // sessionSettings is NOT cleared - API config persists
        
        // Show welcome message after reset
        renderAssistant("Session reset. Analysis cache and conversation history cleared. Your API settings are preserved.");
    });
} else {
    console.error('❌ resetBtn not found in DOM!');
}
