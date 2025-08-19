from flask import Flask, render_template, request, jsonify, send_file
import os
from datetime import datetime
import base64
import requests
import subprocess
import io

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
        # Get the audio data and settings from the request
        audio_data = request.json.get('audio_data')
        fps = request.json.get('fps', '25')
        batch_size = request.json.get('batch_size', '20')
        
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
                'stream_url': stream_url,
                'fps': fps,
                'batch_size': batch_size,
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
    """Receive frames directly from MuseTalk service"""
    try:
        print(f"=== FRAME RECEPTION START ===")
        print(f"DEBUG: Received frame buffer request")
        print(f"DEBUG: Request content type: {request.content_type}")
        
        # Check if it's JSON data (new buffer format)
        if request.content_type and 'application/json' in request.content_type:
            buffer_data = request.json
            
            # Check if this is a finished signal
            if buffer_data.get('status') == 'finished':
                print(f"DEBUG: Received finished signal from MuseTalk")
                print(f"DEBUG: Total frames sent: {buffer_data.get('total_frames_sent', 0)}")
                
                # Mark processing as complete
                global processing_complete
                processing_complete = True
                print(f"DEBUG: Processing marked as complete from finished signal")
                print(f"=== FRAME RECEPTION END (FINISHED) ===")
                
                return jsonify({
                    'success': True,
                    'status': 'finished',
                    'total_frames_sent': buffer_data.get('total_frames_sent', 0),
                    'processing_complete': True,
                    'message': buffer_data.get('message', 'Streaming completed')
                })
            
            # Handle regular frame buffer
            frames = buffer_data.get('frames', [])
            total_frames = buffer_data.get('total_frames', 0)
            is_final = buffer_data.get('final', False)
            
            print(f"DEBUG: Received buffer with {len(frames)} frames")
            print(f"DEBUG: Total frames in request: {total_frames}")
            print(f"DEBUG: Is final: {is_final}")
            
            # Store frames in buffer for frontend access
            global frame_buffer
            frames_added = 0
            for frame_info in frames:
                frame_number = frame_info.get('frame_number', 0)
                frame_data = frame_info.get('frame_data', '')
                
                if frame_data:
                    # Add to buffer directly (keep as base64 for frontend)
                    frame_buffer.append({
                        'frame_number': frame_number,
                        'frame_data': frame_data,  # Keep as base64 for frontend
                        'timestamp': datetime.now().isoformat()
                    })
                    frames_added += 1
            
            # Mark processing as complete if this is the final buffer
            if is_final:
                processing_complete = True
                print(f"DEBUG: Processing marked as complete (final buffer)")
            
            print(f"DEBUG: Frames added to buffer: {frames_added}")
            print(f"DEBUG: Buffer size after adding frames: {len(frame_buffer)}")
            print(f"DEBUG: Processing complete status: {processing_complete}")
            print(f"=== FRAME RECEPTION END ===")
            
            return jsonify({
                'success': True,
                'frames_received': len(frames),
                'frames_added': frames_added,
                'total_buffer_size': len(frame_buffer),
                'processing_complete': processing_complete,
                'message': f'Received {len(frames)} frames, added {frames_added} to buffer'
            })
        
        else:
            # Legacy single frame format (for backward compatibility)
            print(f"DEBUG: Legacy single frame format detected")
            frame_data = request.get_data()
            frame_number = request.headers.get('Frame-Index', 0)
            
            if not frame_data:
                return jsonify({'error': 'No frame data received'}), 400
            
            # Store frame in buffer for frontend access (no file saving)
            frame_buffer.append({
                'frame_number': int(frame_number),
                'frame_data': base64.b64encode(frame_data).decode('utf-8'),
                'timestamp': datetime.now().isoformat()
            })
            
            return jsonify({
                'success': True,
                'frame_number': frame_number,
                'message': f'Frame {frame_number} added to buffer'
            })
        
    except Exception as e:
        print(f"DEBUG: Exception in receive_frame: {e}")
        import traceback
        print(f"DEBUG: Traceback: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500

# Global variables for frame management
frame_buffer = []
total_frames_expected = 0
audio_duration = 0
processing_complete = False

@app.route('/process_audio', methods=['POST'])
def process_audio():
    try:
        # Get parameters from request
        fps = request.json.get('fps', '25')
        batch_size = request.json.get('batch_size', '20')
        
        # Reset frame buffer for new processing session
        global frame_buffer, total_frames_expected, audio_duration, processing_complete
        frame_buffer.clear()
        total_frames_expected = 0
        audio_duration = 0
        processing_complete = False
        
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
            'stream_url': stream_url,
            'fps': fps,
            'batch_size': batch_size,
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

@app.route('/get_frame_buffer', methods=['GET'])
def get_frame_buffer():
    """Get all frames in the buffer (for frontend to check occasionally)"""
    global frame_buffer, processing_complete
    
    return jsonify({
        'frames': frame_buffer,
        'buffer_size': len(frame_buffer),
        'processing_complete': processing_complete
    })

@app.route('/clear_buffer', methods=['POST'])
def clear_buffer():
    """Clear the frame buffer"""
    global frame_buffer, processing_complete
    
    print(f"=== BUFFER CLEAR ===")
    print(f"DEBUG: Clearing frame buffer")
    print(f"DEBUG: Buffer size before clearing: {len(frame_buffer)}")
    
    frame_buffer.clear()
    processing_complete = False
    
    print(f"DEBUG: Buffer size after clearing: {len(frame_buffer)}")
    print(f"DEBUG: Processing complete reset to: {processing_complete}")
    print(f"=== BUFFER CLEAR END ===")
    
    return jsonify({'success': True, 'message': 'Buffer cleared'})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
