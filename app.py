from flask import Flask, render_template, request, jsonify
import os
import uuid
from config import Config

app = Flask(__name__)
app.config.from_object(Config)

@app.route('/')
def index():
    """Render the main page with injected configuration."""
    config_data = {
        'api_base': app.config['API_BASE'],
        'avatar_id': app.config['DEFAULT_AVATAR_ID'],
        'muse_mode': app.config['MUSE_MODE']
    }
    return render_template('index.html', config=config_data)

@app.route('/health')
def health():
    """Health check endpoint."""
    return jsonify({"ok": True})

@app.route('/api/session', methods=['POST'])
def create_session():
    """Create a new session and return session ID."""
    session_id = str(uuid.uuid4())
    return jsonify({"sessionId": session_id})

@app.route('/api/openai/chat', methods=['POST'])
def openai_chat():
    """Handle OpenAI chat requests."""
    data = request.get_json()
    if not data or 'text' not in data:
        return jsonify({"error": "Missing text parameter"}), 400
    
    user_text = data['text']
    
    # TODO: Call OpenAI API with OPENAI_API_KEY and OPENAI_MODEL
    # For now, return placeholder response
    reply = f"[OPENAI_REPLY_PLACEHOLDER] for: {user_text}"
    
    return jsonify({"reply": reply})

@app.route('/api/muse/start', methods=['POST'])
def muse_start():
    """Start Musetalk generation."""
    data = request.get_json()
    if not data or 'sessionId' not in data:
        return jsonify({"error": "Missing sessionId parameter"}), 400
    
    session_id = data['sessionId']
    avatar_id = data.get('avatarId', app.config['DEFAULT_AVATAR_ID'])
    text = data.get('text', '')
    
    # TODO: Call Musetalk API to start generation
    # For now, return configured mode
    return jsonify({
        "mode": app.config['MUSE_MODE'],
        "sessionId": session_id,
        "avatarId": avatar_id
    })

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
