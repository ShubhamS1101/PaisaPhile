// Event Handlers - Premium Analyst UI

// ================================
// TAB CLOSE / UNLOAD HANDLER
// ================================
// Flush session state when tab is closed or page is unloaded
window.addEventListener('beforeunload', (e) => {
    // Use sendBeacon for reliable delivery during unload
    navigator.sendBeacon('/api/flush-session', JSON.stringify({}));
});

// Also handle page visibility change for mobile browsers
document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') {
        // Page is being hidden (tab switched, minimized, or closing)
        // Use sendBeacon as a backup for mobile
        navigator.sendBeacon('/api/flush-session', JSON.stringify({}));
    }
});

// Composer auto-resize
if (composer) {
    composer.addEventListener('input', function () {
        this.style.height = 'auto';
        this.style.height = Math.min(this.scrollHeight, 200) + 'px';
    });
}

// Send on Enter (without Shift)
if (composer) {
    composer.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            if (sendBtn && !sendBtn.disabled) sendMessage();
        }
    });
}

// Send button click
if (sendBtn) {
    sendBtn.addEventListener('click', sendMessage);
}

// Settings button - Open SEPARATE settings page with Continue Chat option
if (openSettingsBtn) {
    openSettingsBtn.addEventListener('click', () => {
        console.log('Settings clicked - opening settings page');
        const settingsPage = document.getElementById('settingsPage');
        if (settingsPage) {
            // Pre-fill settings fields with current values
            const agentProvider = document.getElementById('settingsAgentProvider');
            const agentModel = document.getElementById('settingsAgentModel');
            const agentApiKey = document.getElementById('settingsAgentApiKey');
            const graphProvider = document.getElementById('settingsGraphProvider');
            const graphModel = document.getElementById('settingsGraphModel');
            const graphApiKey = document.getElementById('settingsGraphApiKey');
            const convProvider = document.getElementById('settingsConversationProvider');
            const convModel = document.getElementById('settingsConversationModel');
            const convApiKey = document.getElementById('settingsConversationApiKey');
            
            if (sessionSettings) {
                if (agentProvider) agentProvider.value = sessionSettings.agent?.provider || '';
                if (agentModel) agentModel.value = sessionSettings.agent?.model || '';
                if (agentApiKey) agentApiKey.value = sessionSettings.agent?.api_key || '';
                if (graphProvider) graphProvider.value = sessionSettings.graph?.provider || '';
                if (graphModel) graphModel.value = sessionSettings.graph?.model || '';
                if (graphApiKey) graphApiKey.value = sessionSettings.graph?.api_key || '';
                if (convProvider) convProvider.value = sessionSettings.conversation?.provider || '';
                if (convModel) convModel.value = sessionSettings.conversation?.model || '';
                if (convApiKey) convApiKey.value = sessionSettings.conversation?.api_key || '';
            }
            
            settingsPage.classList.remove('hidden');
            document.querySelector('.app').classList.add('hidden');
        }
    });
} else {
    console.log('openSettingsBtn not found');
}

// Back button on Settings page - Return to chat without saving changes
const settingsBackBtn = document.getElementById('settingsBackBtn');
if (settingsBackBtn) {
    settingsBackBtn.addEventListener('click', () => {
        console.log('Settings back button clicked - no changes saved');
        const settingsPage = document.getElementById('settingsPage');
        if (settingsPage) {
            settingsPage.classList.add('hidden');
            document.querySelector('.app').classList.remove('hidden');
        }
    });
}

// Continue Chat button - Save settings and return to chat
const continueChatBtn = document.getElementById('continueChatBtn');
if (continueChatBtn) {
    continueChatBtn.addEventListener('click', async () => {
        console.log('Continue Chat clicked - saving settings');
        
        // Get values from settings page
        const agentProvider = document.getElementById('settingsAgentProvider')?.value || '';
        const agentModel = document.getElementById('settingsAgentModel')?.value || '';
        const agentApiKey = document.getElementById('settingsAgentApiKey')?.value || '';
        const graphProvider = document.getElementById('settingsGraphProvider')?.value || '';
        const graphModel = document.getElementById('settingsGraphModel')?.value || '';
        const graphApiKey = document.getElementById('settingsGraphApiKey')?.value || '';
        const convProvider = document.getElementById('settingsConversationProvider')?.value || '';
        const convModel = document.getElementById('settingsConversationModel')?.value || '';
        const convApiKey = document.getElementById('settingsConversationApiKey')?.value || '';
        
        // Validate required fields
        if (!agentProvider || !agentApiKey || !graphProvider || !graphApiKey || !convProvider || !convApiKey) {
            alert('Please fill in all required fields (Provider and API Key for each LLM).');
            return;
        }
        
        // Update sessionSettings
        sessionSettings = {
            agent: { provider: agentProvider, model: agentModel, api_key: agentApiKey },
            graph: { provider: graphProvider, model: graphModel, api_key: graphApiKey },
            conversation: { provider: convProvider, model: convModel, api_key: convApiKey }
        };
        
        // Send to backend
        try {
            const res = await fetch('/api/configure', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ llm_settings: sessionSettings })
            });
            const data = await res.json();
            if (!data.success) {
                alert('Failed to update settings: ' + (data.error || 'Unknown error'));
                return;
            }
            console.log('Settings updated successfully');
        } catch (err) {
            console.error('Failed to update settings:', err);
            alert('Failed to update settings. Please try again.');
            return;
        }
        
        // Return to chat
        const settingsPage = document.getElementById('settingsPage');
        if (settingsPage) {
            settingsPage.classList.add('hidden');
            document.querySelector('.app').classList.remove('hidden');
        }
    });
}

// New Chat button
if (resetBtn) {
    resetBtn.addEventListener('click', async () => {
        console.log('New Chat clicked');
        const ok = confirm('Start a new chat? This clears the current conversation and analysis cache. Your API settings will be preserved.');
        if (!ok) return;
        
        try {
            const res = await fetch('/api/reset-session', { method: 'POST' });
            const data = await res.json();
            if (!data || !data.success) {
                renderError(data && data.error ? data.error : 'Failed to reset session.');
                return;
            }
        } catch (err) {
            renderError('Failed to reset session.');
            return;
        }

        // Clear chat but keep settings (sessionSettings remains intact)
        if (messagesWrap) messagesWrap.innerHTML = '';
        if (composer) {
            composer.value = '';
            composer.style.height = 'auto';
        }
        isProcessing = false;
        hasShownWelcome = false;
        // sessionSettings is NOT cleared - API config persists
        
        // Show welcome message after new chat
        renderAssistant("New chat started. Analysis cache cleared. Your API settings are preserved. How can I help you today?");
    });
} else {
    console.log('resetBtn not found');
}

// ================================
// HELP PAGE HANDLERS
// ================================
const helpPage = document.getElementById('helpPage');
const setupHelpBtn = document.getElementById('setupHelpBtn');
const helpBackBtn = document.getElementById('helpBackBtn');
const helpCloseBtn = document.getElementById('helpCloseBtn');

// Track where we came from (setup or chat)
let helpReturnTo = 'setup';

// Help button on setup page
if (setupHelpBtn) {
    setupHelpBtn.addEventListener('click', () => {
        console.log('Help clicked from setup');
        helpReturnTo = 'setup';
        if (helpPage && setupPage) {
            setupPage.classList.add('hidden');
            helpPage.classList.remove('hidden');
        }
    });
}

// Back button on help page
if (helpBackBtn) {
    helpBackBtn.addEventListener('click', () => {
        console.log('Help back clicked, returning to:', helpReturnTo);
        if (helpPage) {
            helpPage.classList.add('hidden');
            if (helpReturnTo === 'setup' && setupPage) {
                setupPage.classList.remove('hidden');
            } else if (helpReturnTo === 'chat') {
                document.querySelector('.app').classList.remove('hidden');
            }
        }
    });
}

// Close/Got it button on help page
if (helpCloseBtn) {
    helpCloseBtn.addEventListener('click', () => {
        console.log('Help close clicked');
        if (helpPage) {
            helpPage.classList.add('hidden');
            if (helpReturnTo === 'setup' && setupPage) {
                setupPage.classList.remove('hidden');
            } else if (helpReturnTo === 'chat') {
                document.querySelector('.app').classList.remove('hidden');
            }
        }
    });
}

// Escape key to close setup page (only if session is active)
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        // Close help page
        if (helpPage && !helpPage.classList.contains('hidden')) {
            helpPage.classList.add('hidden');
            if (helpReturnTo === 'setup' && setupPage) {
                setupPage.classList.remove('hidden');
            } else if (helpReturnTo === 'chat') {
                document.querySelector('.app').classList.remove('hidden');
            }
            return;
        }
        // Close setup page
        if (setupPage && !setupPage.classList.contains('hidden') && sessionActive) {
            setupPage.classList.add('hidden');
            document.querySelector('.app').classList.remove('hidden');
        }
    }
});
