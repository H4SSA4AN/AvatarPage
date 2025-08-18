# Avatar Chat - Minimal Flask Website

A minimal Flask website for real-time avatar chat with microphone recording, OpenAI integration, and video streaming capabilities.

## Features

- **Single-page UI**: Clean, centered interface with mic button, status badge, and video player
- **Audio Recording**: Records microphone audio in ~250ms chunks using MediaRecorder with Opus codec
- **OpenAI Integration**: Server-side chat processing (API key kept secure)
- **Video Streaming**: Support for both MSE streaming and file playback modes
- **Modular Architecture**: Clean separation of UI, browser logic, and Flask routes
- **ES6 Modules**: Vanilla JavaScript with ES modules, no bundlers required

## Tech Stack

- **Backend**: Python 3.11+, Flask (no extensions beyond built-ins)
- **Frontend**: Vanilla JavaScript (ES modules), HTML5, CSS3
- **Audio**: MediaRecorder API with `audio/webm;codecs=opus`
- **Video**: MediaSource Extensions (MSE) for streaming, standard video playback for files
- **Configuration**: Environment variables with sensible defaults

## Project Structure

```
AvatarPage/
├── app.py                 # Main Flask application
├── config.py             # Configuration management
├── requirements.txt      # Python dependencies
├── env.example          # Environment variables template
├── README.md            # This file
└── app/
    ├── templates/
    │   └── index.html   # Main HTML template
    └── static/
        └── js/
            ├── main.js      # Main application logic
            ├── state.js     # State management
            ├── mic.js       # Microphone recording
            ├── player.js    # Video player (MSE/file)
            ├── ws.js        # WebSocket placeholder
            └── openai.js    # OpenAI API client
```

## Setup Instructions

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment

Copy the example environment file and configure your settings:

```bash
cp env.example .env
```

Edit `.env` with your configuration:

```env
# API Configuration
API_BASE=http://localhost:5000

# Avatar Configuration
DEFAULT_AVATAR_ID=default-01

# OpenAI Configuration (uncomment and add your key)
# OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-3.5-turbo

# Musetalk Configuration
MUSE_MODE=file  # 'mse' or 'file'
MUSE_STREAM_URL=ws://localhost:8080/stream
MUSE_FILE_URL=http://localhost:8080/video

# Flask Configuration
SECRET_KEY=your-secret-key-here
```

### 3. Run the Application

```bash
python app.py
```

The application will be available at `http://localhost:5000`

## User Flow (MVP)

1. **User presses/holds mic** → Browser records audio chunks (250ms)
2. **UI shows status transitions**: idle → recording → processing → streaming
3. **OpenAI Integration**: Browser sends captured audio/text to `/api/openai/chat`
4. **Musetalk Integration**: Browser connects to WS for MSE streaming or fetches video file
5. **Video playback**: Video element plays the incoming stream/file

## API Endpoints

### GET `/`
Renders the main page with injected configuration (data attributes on `<body>`)

### GET `/health`
Returns JSON health check: `{"ok": true}`

### POST `/api/session`
Creates a new session and returns a random session ID

### POST `/api/openai/chat`
Accepts `{"text": "<user text>"}` and returns `{"reply": "<assistant response>"}`

### POST `/api/muse/start`
Accepts `{"sessionId": "...", "avatarId": "...", "text": "..."}` and returns `{"mode": "mse"|"file"}`

## JavaScript Modules

### `state.js`
Manages application state and UI updates:
- Status badge text transitions
- Mic button state
- Session management
- Assistant text display

### `mic.js`
Handles microphone recording:
- MediaRecorder with `audio/webm;codecs=opus`
- 250ms audio chunks
- Start/stop functionality with callbacks

### `player.js`
Video playback functionality:
- MSE path: MediaSource + SourceBuffer with `video/webm;codecs="vp8"`
- File path: Standard video element playback
- FIFO queue for fragment management
- Error handling and fallbacks

### `ws.js`
WebSocket placeholder for future Musetalk integration:
- URL computation from API base and session ID
- Placeholder connection handlers
- Ready for real WebSocket implementation

### `openai.js`
OpenAI API client:
- Server-side API calls (no keys in browser)
- Chat request handling
- Error management

### `main.js`
Main application orchestrator:
- Component initialization
- User interaction handling
- Flow coordination
- Configuration management

## Configuration

The application reads configuration from environment variables and injects them as data attributes on the `<body>` element:

- `data-api-base`: Base URL for API calls
- `data-avatar`: Default avatar ID
- `data-muse-mode`: Musetalk mode ('mse' or 'file')

## Development Notes

### TODOs for Real Integration

1. **OpenAI Integration**: Replace placeholder in `/api/openai/chat` with actual OpenAI API calls
2. **Speech-to-Text**: Add STT processing for audio chunks
3. **WebSocket Streaming**: Implement real WebSocket connection in `ws.js`
4. **Musetalk API**: Connect to actual Musetalk service for avatar generation
5. **Error Handling**: Add comprehensive error handling and user feedback

### Browser Compatibility

- **MediaRecorder**: Modern browsers with Opus codec support
- **MediaSource Extensions**: Chrome, Firefox, Safari (with limitations)
- **WebSocket**: All modern browsers
- **ES6 Modules**: Modern browsers (IE not supported)

### Security Considerations

- OpenAI API key is kept server-side only
- Session IDs are randomly generated UUIDs
- CORS should be configured for production deployment
- HTTPS required for microphone access in production

## License

This project is provided as-is for educational and development purposes.
