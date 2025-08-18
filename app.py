from flask import Flask, render_template, request, jsonify, send_file
import os
from datetime import datetime
import base64
import requests
import subprocess

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
        
        # Use fixed filename 'input.wav'
        filename = 'input.wav'
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        
        # Save the audio file
        with open(filepath, 'wb') as f:
            f.write(audio_bytes)
        
        # Automatically send to MuseTalk for processing
        try:
            print(f"DEBUG: Starting MuseTalk request for file: {filepath}")
            
            # MuseTalk server configuration
            musetalk_url = "http://localhost:8085/process"
            stream_url = "http://localhost:5000/receive_frame"  # This Flask app's endpoint
            
            print(f"DEBUG: MuseTalk URL: {musetalk_url}")
            print(f"DEBUG: Stream URL: {stream_url}")
            
            # Prepare the files and data for the request
            files = {
                'audio': ('input.wav', open(filepath, 'rb'), 'audio/wav'),
            }
            
            data = {
                'video_path': 'data/video/1FrameVideo.mp4',
                'stream_url': stream_url,
                'bbox_shift': '0'
            }
            
            print(f"DEBUG: Sending request to MuseTalk...")
            # Send request to MuseTalk server
            response = requests.post(musetalk_url, files=files, data=data)
            print(f"DEBUG: MuseTalk response status: {response.status_code}")
            print(f"DEBUG: MuseTalk response: {response.text}")
            
            if response.status_code == 200:
                return jsonify({
                    'success': True,
                    'filename': filename,
                    'message': f'Audio saved as {filename} and sent to MuseTalk for processing',
                    'musetalk_response': response.json() if response.headers.get('content-type') == 'application/json' else response.text
                })
            else:
                return jsonify({
                    'success': True,
                    'filename': filename,
                    'message': f'Audio saved as {filename}',
                    'warning': f'MuseTalk processing failed with status {response.status_code}',
                    'musetalk_response': response.text
                })
                
        except requests.exceptions.ConnectionError as e:
            print(f"DEBUG: Connection error to MuseTalk: {e}")
            return jsonify({
                'success': True,
                'filename': filename,
                'message': f'Audio saved as {filename}',
                'warning': 'Could not connect to MuseTalk server. Make sure it is running on localhost:8085'
            })
        except Exception as e:
            print(f"DEBUG: Exception in MuseTalk request: {e}")
            return jsonify({
                'success': True,
                'filename': filename,
                'message': f'Audio saved as {filename}',
                'warning': f'Error sending to MuseTalk: {str(e)}'
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

@app.route('/receive_frame', methods=['POST'])
def receive_frame():
    try:
        print(f"DEBUG: Received frame request")
        print(f"DEBUG: Request content type: {request.content_type}")
        print(f"DEBUG: Request data: {request.get_data()[:200]}...")  # First 200 chars
        
        # Check if it's JSON, form data, or raw image data
        if request.content_type and 'application/json' in request.content_type:
            # JSON request
            frame_data = request.json.get('frame_data')
            frame_number = request.json.get('frame_number', 0)
        elif request.content_type and ('image/' in request.content_type):
            # Raw image data (JPEG, PNG, etc.)
            frame_data = request.get_data()  # Get raw binary data
            frame_number = 0  # Default frame number for raw image data
        else:
            # Form data request (like from curl)
            frame_data = request.form.get('frame_data')
            frame_number = request.form.get('frame_number', 0)
        
        print(f"DEBUG: Frame number: {frame_number}")
        print(f"DEBUG: Frame data type: {type(frame_data)}")
        print(f"DEBUG: Frame data length: {len(frame_data) if frame_data else 0}")
        
        if not frame_data:
            print(f"DEBUG: No frame data received")
            return jsonify({'error': 'No frame data received'}), 400
        
        # Handle different data types
        if isinstance(frame_data, bytes):
            # Raw binary image data (JPEG, PNG, etc.)
            frame_bytes = frame_data
            print(f"DEBUG: Using raw binary image data")
        elif isinstance(frame_data, str):
            # Base64 encoded data
            # Remove the data URL prefix to get just the base64 data
            if frame_data.startswith('data:image/png;base64,'):
                frame_data = frame_data.split(',')[1]
            elif frame_data.startswith('data:image/jpeg;base64,'):
                frame_data = frame_data.split(',')[1]
            
            print(f"DEBUG: About to decode base64 data")
            # Decode the base64 data
            frame_bytes = base64.b64decode(frame_data)
        else:
            print(f"DEBUG: Unknown frame data type")
            return jsonify({'error': 'Unknown frame data type'}), 400
        print(f"DEBUG: Decoded frame bytes length: {len(frame_bytes)}")
        
        # Create frames directory if it doesn't exist
        frames_folder = os.path.join(UPLOAD_FOLDER, 'frames')
        if not os.path.exists(frames_folder):
            os.makedirs(frames_folder)
        
        # Determine file extension based on content type
        if request.content_type and 'jpeg' in request.content_type:
            extension = 'jpg'
        elif request.content_type and 'png' in request.content_type:
            extension = 'png'
        else:
            extension = 'png'  # Default to PNG
        
        # Save the frame with frame number
        filename = f'frame_{frame_number:06d}.{extension}'
        filepath = os.path.join(frames_folder, filename)
        
        print(f"DEBUG: Saving frame to: {filepath}")
        with open(filepath, 'wb') as f:
            f.write(frame_bytes)
        
        print(f"DEBUG: Frame saved successfully")
        return jsonify({
            'success': True,
            'filename': filename,
            'frame_number': frame_number,
            'message': f'Frame {frame_number} saved as {filename}'
        })
        
    except Exception as e:
        print(f"DEBUG: Exception in receive_frame: {e}")
        import traceback
        print(f"DEBUG: Traceback: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500

@app.route('/process_audio', methods=['POST'])
def process_audio():
    try:
        # Check if input.wav exists
        audio_filepath = os.path.join(UPLOAD_FOLDER, 'input.wav')
        if not os.path.exists(audio_filepath):
            return jsonify({'error': 'No input.wav file found. Please record audio first.'}), 404
        
        # MuseTalk server configuration
        musetalk_url = "http://localhost:8085/process"
        stream_url = "http://localhost:5000/receive_frame"  # This Flask app's endpoint
        
        # Prepare the files and data for the request
        files = {
            'audio': ('input.wav', open(audio_filepath, 'rb'), 'audio/wav'),
        }
        
        data = {
            'video_path': 'data/video/yongen.mp4',
            'stream_url': stream_url,
            'bbox_shift': '0'
        }
        
        # Send request to MuseTalk server
        response = requests.post(musetalk_url, files=files, data=data)
        
        if response.status_code == 200:
            return jsonify({
                'success': True,
                'message': 'Audio sent to MuseTalk for processing',
                'response': response.json() if response.headers.get('content-type') == 'application/json' else response.text
            })
        else:
            return jsonify({
                'error': f'MuseTalk server returned status {response.status_code}',
                'response': response.text
            }), response.status_code
            
    except requests.exceptions.ConnectionError:
        return jsonify({'error': 'Could not connect to MuseTalk server. Make sure it is running on localhost:8085'}), 503
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
