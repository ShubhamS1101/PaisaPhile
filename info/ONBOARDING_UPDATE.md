# Onboarding & Settings Update

## Overview
Implemented a new 3-page swipeable onboarding flow that replaces the single-page settings modal. Each page configures a different LLM component (Agent, Graph, Conversation) with separate provider, API key, and model selections.

## Key Features

### 🎯 3-Page Swipeable Interface
- **Page 1: Agent LLM** - For indicator, pattern, and trend analysis agents
- **Page 2: Graph LLM** - For planning, routing, and orchestration  
- **Page 3: Conversation LLM** - For memory, summaries, and context management

### 📱 Mobile-Optimized
- Touch swipe gestures support (swipe left/right to navigate)
- Responsive design that fits all screen sizes
- Progress dots for visual navigation
- Back/Next/Skip buttons for easy navigation

### 🔧 Smart Configuration
- **Provider Selection** - Choose from OpenAI, Anthropic, Gemini, or Qwen for each component
- **Model Dropdown** - Disabled until provider is selected, then shows relevant models
- **Default Models** - If no model is selected, uses best model for that provider
- **API Key Reuse** - Can use same API key for all three components or different ones
- **Flexible Setup** - Can skip any configuration and use defaults

### 💾 Session Persistence
- Settings are preserved when opening settings mid-chat
- Only "Reset Session" button flushes conversation history
- Changing settings mid-chat doesn't clear conversation
- Settings remain active across the session

## Files Modified

### HTML
- `ui/index.html` - Replaced single settings modal with 3-page onboarding structure

### CSS
- `ui/css/modal.css` - Added styles for swipeable pages, progress indicators, transitions
- `ui/css/forms.css` - Added `.btn-success` class for "Start Chat" button

### JavaScript
- `ui/js/onboarding.js` (NEW) - Handles page navigation, provider/model selection, swipe gestures
- `ui/js/events.js` - Updated to work with new onboarding flow, preserve settings on reset
- `ui/js/dom.js` - Simplified to only reference elements that exist

## Model Options by Provider

### OpenAI
- GPT-4o (Best reasoning)
- GPT-4o Mini (Fast & cheap) ⭐ Default
- GPT-4 Turbo
- GPT-3.5 Turbo (Cheapest)

### Anthropic
- Claude Opus 4 (Best)
- Claude Sonnet 4
- Claude Haiku 4.5 (Fast) ⭐ Default
- Claude 3.5 Sonnet

### Google Gemini
- Gemini 2.5 Pro (Best)
- Gemini 2.5 Flash (Fast) ⭐ Default
- Gemini 1.5 Pro
- Gemini 1.5 Flash

### Qwen
- Qwen3 Max (Best) ⭐ Default
- Qwen3 VL Plus (Vision)
- Qwen Turbo (Fast)
- Qwen Flash (Fastest)

## User Flow

### Initial Setup
1. User opens app
2. Onboarding modal appears automatically
3. Navigate through 3 pages:
   - Configure Agent LLM (or skip)
   - Configure Graph LLM (or skip)
   - Configure Conversation LLM (or skip)
4. Click "Start Chat" on final page
5. Chat interface activates

### Mid-Chat Settings
1. Click "Settings" button in header
2. Same 3-page interface appears
3. Make changes to any configuration
4. Click "Start Chat" to save and continue
5. **Conversation history is preserved**

### Reset Session
1. Click "Reset" button in header
2. Confirm dialog appears
3. If confirmed:
   - Clears all chat messages
   - Resets agent memory
   - **Keeps all settings configured**
   - Shows welcome message

## Technical Details

### Touch Gestures
- Swipe threshold: 50px
- Supports horizontal swipe only
- Prevents accidental page changes
- Works on all touch devices

### Navigation
- Progress dots indicate current page (1-3)
- Dots are clickable for direct navigation
- Back button disabled on first page
- Skip button hidden on last page
- Next button becomes "Start Chat" on last page

### Default Fallbacks
- If no provider selected: uses OpenAI
- If no API key entered: uses environment variable or config default
- If no model selected: uses provider's default recommended model
- All configurations are optional

## Benefits

✅ **Better UX** - Clearer organization, less overwhelming than single-page form
✅ **Mobile-Friendly** - Swipe gestures, better screen fit
✅ **Flexible** - Can configure all, some, or none
✅ **Persistent** - Settings survive reset, only cleared on logout
✅ **Discoverable** - Progress indicators show what's configured
✅ **Accessible** - Keyboard, touch, and mouse navigation all supported

## Future Enhancements

- API key validation indicators per page
- Save configuration profiles
- Import/export settings
- Remember last used configuration
- Provider availability status
