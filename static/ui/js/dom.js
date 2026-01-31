// DOM Element References

// Setup Page elements
const setupPage = document.getElementById('setupPage');
const setupLogoBull = document.getElementById('setupLogoBull');
const setupLogoName = document.getElementById('setupLogoName');
const setupThemeBtn = document.getElementById('setupThemeBtn');

// Validation elements
const agentValidation = document.getElementById('agentValidation');
const graphValidation = document.getElementById('graphValidation');
const conversationValidation = document.getElementById('conversationValidation');

// Header elements (chat page) - these exist in hidden div but are still in DOM
const headerLogoBull = document.getElementById('headerLogoBull');
const headerLogoName = document.getElementById('headerLogoName');
const openSettingsBtn = document.getElementById('openSettings');
const resetBtn = document.getElementById('resetSession');
const toggleThemeBtn = document.getElementById('toggleTheme');

// Chat elements
const messagesWrap = document.getElementById('messagesWrap');
const messagesEl = document.getElementById('messages');
const composer = document.getElementById('composer');
const sendBtn = document.getElementById('send');

// Debug: Log if buttons are found
console.log('DOM Elements loaded:');
console.log('  openSettingsBtn:', openSettingsBtn ? 'found' : 'NOT FOUND');
console.log('  resetBtn:', resetBtn ? 'found' : 'NOT FOUND');
console.log('  setupPage:', setupPage ? 'found' : 'NOT FOUND');
