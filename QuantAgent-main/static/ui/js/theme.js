// Theme Management
const savedTheme = localStorage.getItem('theme') || 'light';
document.documentElement.setAttribute('data-theme', savedTheme);
if (savedTheme === 'dark') {
    toggleThemeBtn.querySelector('i').className = 'fa-solid fa-sun';
}

// Function to toggle theme
function toggleTheme() {
    const html = document.documentElement;
    const now = html.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    html.setAttribute('data-theme', now);
    const icon = now === 'dark' ? 'fa-solid fa-sun' : 'fa-solid fa-moon';
    
    // Update main theme button
    toggleThemeBtn.querySelector('i').className = icon;
    
    // Update modal theme button if exists
    const modalThemeBtn = document.getElementById('modalToggleTheme');
    if (modalThemeBtn) {
        modalThemeBtn.querySelector('i').className = icon;
    }
    
    localStorage.setItem('theme', now);
}

// Main theme button
toggleThemeBtn.addEventListener('click', toggleTheme);

// Modal theme button
document.addEventListener('DOMContentLoaded', () => {
    const modalThemeBtn = document.getElementById('modalToggleTheme');
    if (modalThemeBtn) {
        // Set initial icon
        const currentTheme = document.documentElement.getAttribute('data-theme');
        const icon = currentTheme === 'dark' ? 'fa-solid fa-sun' : 'fa-solid fa-moon';
        modalThemeBtn.querySelector('i').className = icon;
        
        // Add click listener
        modalThemeBtn.addEventListener('click', toggleTheme);
    }
});
