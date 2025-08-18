from flask import Flask, render_template, request, jsonify, send_file
import os
from datetime import datetime
import base64

app = Flask(__name__)

# Ensure uploads directory exists
UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/save_audio', methods=['POST'])
def save_audio():
    try:
        # Get the audio data from the request
        audio_data = request.json.get('audio_data')
        
        if not audio_data:
            return jsonify({'error': 'No audio data received'}), 400
        
        # Remove the data URL prefix to get just the base64 data
        if audio_data.startswith('data:audio/wav;base64,'):
            audio_data = audio_data.split(',')[1]
        
        # Decode the base64 data
        audio_bytes = base64.b64decode(audio_data)
        
        # Generate a unique filename with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'recording_{timestamp}.wav'
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        
        # Save the audio file
        with open(filepath, 'wb') as f:
            f.write(audio_bytes)
        
        return jsonify({
            'success': True,
            'filename': filename,
            'message': f'Audio saved as {filename}'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/download/<filename>')
def download_file(filename):
    try:
        return send_file(
            os.path.join(UPLOAD_FOLDER, filename),
            as_attachment=True,
            download_name=filename
        )
    except FileNotFoundError:
        return jsonify({'error': 'File not found'}), 404

@app.route('/list_recordings')
def list_recordings():
    try:
        files = []
        for filename in os.listdir(UPLOAD_FOLDER):
            if filename.endswith('.wav'):
                filepath = os.path.join(UPLOAD_FOLDER, filename)
                files.append({
                    'filename': filename,
                    'size': os.path.getsize(filepath),
                    'created': datetime.fromtimestamp(os.path.getctime(filepath)).strftime('%Y-%m-%d %H:%M:%S')
                })
        return jsonify({'recordings': files})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
