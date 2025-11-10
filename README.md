# Audio Recorder Web Application

A modern Flask web application that allows users to record audio from their microphone and save it as WAV files.


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

3. **Create a `.env` file in the project root:**
   ```bash
   OPENAI_API_KEY= #Your key
   TRANSCRIBE_MODEL=whisper-1
   CHAT_MODEL=gpt-4o-mini
   TTS_MODEL=tts-1
   TTS_VOICE=alloy
   SYSTEM_PROMPT=You are a concise, helpful assistant.
   MUSETALK_URL=http://localhost:8085
   ```
   - Paste all required environment variables into this `.env` file

4. **Run the Flask application:**
   ```bash
   python app.py
   ```

5. **Open your web browser and navigate to:**
   ```
   http://localhost:5000
   ```



## License

This project is open source and available under the MIT License.

