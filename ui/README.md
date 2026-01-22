# PaisaPhile UI Structure

## Framework
**Vanilla JavaScript** (no frontend framework)

## External Libraries
- **marked.js** - Markdown rendering
- **Font Awesome** - Icons
- **Google Fonts (Inter)** - Typography

## Folder Structure

```
ui/
├── index.html              # Main HTML file
├── css/                    # Stylesheets (organized by component)
│   ├── variables.css       # CSS variables and theme
│   ├── base.css           # Base/reset styles
│   ├── modal.css          # Settings modal
│   ├── forms.css          # Form inputs and validation
│   ├── layout.css         # Header and app layout
│   ├── chat.css           # Chat messages and bubbles
│   ├── composer.css       # Message input area
│   └── responsive.css     # Mobile responsiveness
└── js/                    # JavaScript modules
    ├── config.js          # Configuration (marked.js setup)
    ├── dom.js             # DOM element references
    ├── state.js           # Application state
    ├── theme.js           # Dark/light theme switching
    ├── utils.js           # Utility functions
    ├── validation.js      # API key validation
    ├── render.js          # Message rendering
    ├── events.js          # Event handlers
    └── api.js             # Backend communication
```

## File Purposes

### CSS Files
- `variables.css` - Color scheme, spacing, shadows for light/dark themes
- `base.css` - Global resets and body styles
- `modal.css` - Settings modal popup styling
- `forms.css` - Input fields, validation states, buttons
- `layout.css` - Header, brand, navigation pills
- `chat.css` - Message bubbles, avatars, charts, typing indicator
- `composer.css` - Message textarea and send button
- `responsive.css` - Mobile/tablet breakpoints

### JS Files
- `config.js` - Initialize marked.js configuration
- `dom.js` - Cache all DOM element references
- `state.js` - Session state (active, processing, welcome shown)
- `theme.js` - Dark/light mode toggle and persistence
- `utils.js` - Helper functions (scroll, escapeHtml)
- `validation.js` - API key validation logic
- `render.js` - Render user/assistant messages and errors
- `events.js` - All event listeners (clicks, form submit, etc.)
- `api.js` - Fetch calls to backend `/api/chat` endpoint

## Benefits of This Structure
1. **Maintainability** - Each file has a single responsibility
2. **Debugging** - Easy to locate specific functionality
3. **Performance** - Can optimize/minify individual files
4. **Collaboration** - Multiple developers can work on different components
5. **Reusability** - Components can be reused across pages
