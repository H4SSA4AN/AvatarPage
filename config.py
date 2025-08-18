import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    """Application configuration."""
    
    # API Configuration
    API_BASE = os.getenv('API_BASE', 'http://localhost:5000')
    
    # Avatar Configuration
    DEFAULT_AVATAR_ID = os.getenv('DEFAULT_AVATAR_ID', 'default-01')
    
    # OpenAI Configuration
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
    OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-3.5-turbo')
    
    # Musetalk Configuration
    MUSE_MODE = os.getenv('MUSE_MODE', 'file')  # 'mse' or 'file'
    MUSE_STREAM_URL = os.getenv('MUSE_STREAM_URL', 'ws://localhost:8080/stream')
    MUSE_FILE_URL = os.getenv('MUSE_FILE_URL', 'http://localhost:8080/video')
    
    # Flask Configuration
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
