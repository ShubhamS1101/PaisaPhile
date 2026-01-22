// DOM Element References
const settingsModal = document.getElementById('settingsModal');

// Validation elements
const agentValidation = document.getElementById('agentValidation');
const graphValidation = document.getElementById('graphValidation');
const conversationValidation = document.getElementById('conversationValidation');

// Header buttons
const openSettingsBtn = document.getElementById('openSettings');
const resetBtn = document.getElementById('resetSession');
const toggleThemeBtn = document.getElementById('toggleTheme');

// Log what we found
console.log('🔍 DOM Elements loaded:');
console.log('   settingsModal:', settingsModal);
console.log('   openSettingsBtn:', openSettingsBtn);
console.log('   resetBtn:', resetBtn);

// Chat elements
const messagesWrap = document.getElementById('messagesWrap');
const messagesEl = document.getElementById('messages');
const composer = document.getElementById('composer');
const sendBtn = document.getElementById('send');
