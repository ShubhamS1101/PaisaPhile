// Theme Management - Premium Analyst UI
const savedTheme = localStorage.getItem('theme') || 'dark';
document.documentElement.setAttribute('data-theme', savedTheme);

// Logo paths for theme switching
const LOGO_PATHS = {
    light: {
        bull: '/templates/assets/logo/light_mode/light_mode_bull.svg',
        name: '/templates/assets/logo/light_mode/light_mode_name.svg'
    },
    dark: {
        bull: '/templates/assets/logo/dark_mode/dark_mode_bull.svg',
        name: '/templates/assets/logo/dark_mode/dark_mode_name.svg'
    }
};

// Update all logos based on theme
function updateLogo(theme) {
    const paths = LOGO_PATHS[theme] || LOGO_PATHS.dark;
    
    // Update bull logos
    const bullLogos = [
        document.getElementById('setupLogoBull'),
        document.getElementById('headerLogoBull'),
        document.getElementById('settingsLogoBull'),
        document.getElementById('helpLogoBull')
    ];
    
    bullLogos.forEach(logo => {
        if (logo) logo.src = paths.bull;
    });
    
    // Update name logos
    const nameLogos = [
        document.getElementById('setupLogoName'),
        document.getElementById('headerLogoName'),
        document.getElementById('settingsLogoName'),
        document.getElementById('helpLogoName')
    ];
    
    nameLogos.forEach(logo => {
        if (logo) logo.src = paths.name;
    });
    
    // Update bot avatars in chat
    updateBotAvatars(theme);
}

// Update bot avatar images in chat messages
function updateBotAvatars(theme) {
    const paths = LOGO_PATHS[theme] || LOGO_PATHS.dark;
    const avatars = document.querySelectorAll('.avatar.bot img');
    avatars.forEach(img => {
        img.src = paths.bull;
    });
}

// Update theme icons across all buttons
function updateThemeIcons(theme) {
    const icon = theme === 'dark' ? 'fa-solid fa-sun' : 'fa-solid fa-moon';
    
    const themeButtons = [
        document.getElementById('setupThemeBtn'),
        document.getElementById('toggleTheme'),
        document.getElementById('settingsThemeBtn'),
        document.getElementById('helpThemeBtn')
    ];
    
    themeButtons.forEach(btn => {
        if (btn) {
            const iconEl = btn.querySelector('i');
            if (iconEl) {
                iconEl.className = icon;
            }
        }
    });
}

// Function to toggle theme
function toggleTheme() {
    const html = document.documentElement;
    const currentTheme = html.getAttribute('data-theme');
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    
    html.setAttribute('data-theme', newTheme);
    localStorage.setItem('theme', newTheme);
    
    updateThemeIcons(newTheme);
    updateLogo(newTheme);
}

// Initialize theme on page load
function initTheme() {
    const currentTheme = document.documentElement.getAttribute('data-theme') || 'dark';
    updateThemeIcons(currentTheme);
    updateLogo(currentTheme);
}

// Attach event listeners to all theme buttons
function attachThemeListeners() {
    const themeButtons = [
        document.getElementById('setupThemeBtn'),
        document.getElementById('toggleTheme'),
        document.getElementById('settingsThemeBtn'),
        document.getElementById('helpThemeBtn')
    ];
    
    themeButtons.forEach(btn => {
        if (btn) {
            btn.addEventListener('click', toggleTheme);
        }
    });
}

// Initialize
initTheme();
attachThemeListeners();

// Re-initialize after DOM is fully loaded
document.addEventListener('DOMContentLoaded', () => {
    initTheme();
    attachThemeListeners();
});
