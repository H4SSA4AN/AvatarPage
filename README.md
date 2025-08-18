# Audio Recorder Web Application

A modern Flask web application that allows users to record audio from their microphone and save it as WAV files.

## Features

- 🎤 Real-time audio recording using Web Audio API
- ⏱️ Recording timer with visual feedback
- 💾 Save recordings as WAV files with timestamps
- 📁 View and download saved recordings
- 🎨 Modern, responsive UI with beautiful animations
- 📱 Mobile-friendly design

## Prerequisites

- Python 3.7 or higher
- A modern web browser with microphone access
- Microphone hardware

## Installation

1. **Clone or download the project files**

2. **Install Python dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the Flask application:**
   ```bash
   python app.py
   ```

4. **Open your web browser and navigate to:**
   ```
   http://localhost:5000
   ```

## Usage

### Recording Audio

1. **Start Recording:** Click the "🎙️ Start Recording" button
   - The browser will request microphone permission
   - The button will turn red and pulse while recording
   - A timer will show the recording duration

2. **Stop Recording:** Click the "⏹️ Stop Recording" button
   - Recording will stop and an audio player will appear
   - You can preview your recording

3. **Save Recording:** Click the "💾 Save Recording" button
   - The recording will be converted to WAV format
   - Saved with a timestamp in the filename
   - Appears in the recordings list

### Managing Recordings

- **View Recordings:** All saved recordings appear in the "📁 Saved Recordings" section
- **Download Recordings:** Click the "📥 Download" button next to any recording
- **Refresh List:** Click "🔄 Refresh List" to update the recordings list

## File Structure

```
AvatarPage/
├── app.py                 # Main Flask application
├── requirements.txt       # Python dependencies
├── README.md             # This file
├── templates/
│   └── index.html        # Main web interface
└── uploads/              # Directory for saved recordings (created automatically)
```

## Technical Details

### Backend (Flask)
- **Routes:**
  - `/` - Main page
  - `/save_audio` - Save audio recording (POST)
  - `/download/<filename>` - Download saved recording
  - `/list_recordings` - Get list of saved recordings

### Frontend (HTML/JavaScript)
- **Web Audio API** for microphone access
- **MediaRecorder API** for audio recording
- **Base64 encoding** for data transfer
- **WAV format conversion** using Web Audio API
- **Responsive CSS** with modern design

### Audio Format
- **Input:** WebM audio from browser
- **Output:** WAV format (16-bit PCM, 44.1kHz)
- **Conversion:** Client-side using Web Audio API

## Browser Compatibility

This application works best in modern browsers that support:
- Web Audio API
- MediaRecorder API
- getUserMedia API

**Recommended browsers:**
- Chrome 66+
- Firefox 60+
- Safari 14+
- Edge 79+

## Security Notes

- The application runs locally and doesn't send audio data to external servers
- Audio files are stored locally in the `uploads/` directory
- Microphone access requires user permission in the browser

## Troubleshooting

### Microphone Access Issues
- Ensure your browser has permission to access the microphone
- Check that your microphone is working and not muted
- Try refreshing the page and granting permission again

### Recording Not Saving
- Check that the `uploads/` directory exists and is writable
- Ensure you have sufficient disk space
- Check the browser console for JavaScript errors

### Audio Quality Issues
- Ensure your microphone is properly connected and configured
- Check your system's audio settings
- Try using a different browser

## License

This project is open source and available under the MIT License.

## Contributing

Feel free to submit issues, feature requests, or pull requests to improve this application.
