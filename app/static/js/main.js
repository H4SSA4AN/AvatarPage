/**
 * Main application logic
 */

import { AppState } from './state.js';
import { MicrophoneRecorder } from './mic.js';
import { VideoPlayer } from './player.js';
import { WebSocketManager } from './ws.js';
import { OpenAIClient } from './openai.js';

class AvatarChatApp {
    constructor() {
        this.state = new AppState();
        this.mic = new MicrophoneRecorder();
        this.player = new VideoPlayer();
        this.ws = new WebSocketManager();
        this.openai = null;
        
        // Configuration from data attributes
        this.config = this.loadConfig();
        
        // Audio chunks buffer
        this.audioChunks = [];
        
        // Initialize components
        this.init();
    }
    
    /**
     * Load configuration from data attributes
     */
    loadConfig() {
        const body = document.body;
        return {
            apiBase: body.dataset.apiBase || window.location.origin,
            avatarId: body.dataset.avatar || 'default-01',
            museMode: body.dataset.museMode || 'file'
        };
    }
    
    /**
     * Initialize the application
     */
    async init() {
        try {
            // Initialize OpenAI client
            this.openai = new OpenAIClient(this.config.apiBase);
            
            // Set video element
            const videoEl = document.getElementById('player');
            this.player.setVideoElement(videoEl);
            
            // Check microphone support
            await this.mic.checkSupport();
            
            // Wire up mic button
            this.wireMicButton();
            
            console.log('Avatar Chat App initialized successfully');
            console.log('Configuration:', this.config);
            
        } catch (error) {
            console.error('Failed to initialize app:', error);
            this.state.setStatus('error');
        }
    }
    
    /**
     * Wire up microphone button events
     */
    wireMicButton() {
        const micButton = document.getElementById('mic');
        
        // Click to toggle recording
        micButton.addEventListener('click', () => {
            if (this.state.isCurrentlyRecording()) {
                this.stopRecording();
            } else {
                this.startRecording();
            }
        });
        
        // Press and hold functionality
        let pressTimer = null;
        let isPressed = false;
        
        micButton.addEventListener('mousedown', () => {
            if (!this.state.isCurrentlyRecording()) {
                isPressed = true;
                pressTimer = setTimeout(() => {
                    if (isPressed) {
                        this.startRecording();
                    }
                }, 200); // 200ms hold to start recording
            }
        });
        
        micButton.addEventListener('mouseup', () => {
            isPressed = false;
            if (pressTimer) {
                clearTimeout(pressTimer);
                pressTimer = null;
            }
        });
        
        micButton.addEventListener('mouseleave', () => {
            isPressed = false;
            if (pressTimer) {
                clearTimeout(pressTimer);
                pressTimer = null;
            }
        });
        
        // Touch events for mobile
        micButton.addEventListener('touchstart', (e) => {
            e.preventDefault();
            if (!this.state.isCurrentlyRecording()) {
                isPressed = true;
                pressTimer = setTimeout(() => {
                    if (isPressed) {
                        this.startRecording();
                    }
                }, 200);
            }
        });
        
        micButton.addEventListener('touchend', (e) => {
            e.preventDefault();
            isPressed = false;
            if (pressTimer) {
                clearTimeout(pressTimer);
                pressTimer = null;
            }
        });
    }
    
    /**
     * Start recording audio
     */
    async startRecording() {
        try {
            // Create session first
            await this.createSession();
            
            // Update state
            this.state.setStatus('recording');
            this.state.setRecording(true);
            
            // Clear previous audio chunks
            this.audioChunks = [];
            
            // Start recording
            await this.mic.start({
                onChunk: (chunk) => {
                    this.audioChunks.push(chunk);
                    console.log('Audio chunk received:', chunk.size, 'bytes');
                },
                onStop: (audioBlob) => {
                    this.handleRecordingComplete(audioBlob);
                }
            });
            
        } catch (error) {
            console.error('Failed to start recording:', error);
            this.state.setStatus('error');
            this.state.setRecording(false);
        }
    }
    
    /**
     * Stop recording audio
     */
    stopRecording() {
        if (this.state.isCurrentlyRecording()) {
            this.mic.stop();
        }
    }
    
    /**
     * Handle recording completion
     */
    async handleRecordingComplete(audioBlob) {
        try {
            this.state.setStatus('processing');
            this.state.setRecording(false);
            
            console.log('Recording completed, audio size:', audioBlob.size, 'bytes');
            
            // For now, use placeholder text (later will be STT)
            const placeholderText = "Hello, this is a placeholder for speech-to-text conversion.";
            
            // Call OpenAI chat
            await this.handleOpenAIChat(placeholderText);
            
        } catch (error) {
            console.error('Failed to handle recording completion:', error);
            this.state.setStatus('error');
        }
    }
    
    /**
     * Create a new session
     */
    async createSession() {
        try {
            const response = await fetch(`${this.config.apiBase}/api/session`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                }
            });
            
            if (!response.ok) {
                throw new Error(`Failed to create session: ${response.status}`);
            }
            
            const data = await response.json();
            this.state.setSessionId(data.sessionId);
            
        } catch (error) {
            console.error('Failed to create session:', error);
            throw error;
        }
    }
    
    /**
     * Handle OpenAI chat request
     */
    async handleOpenAIChat(text) {
        try {
            this.state.setStatus('chat');
            
            const response = await this.openai.postChat({
                text: text,
                sessionId: this.state.getSessionId()
            });
            
            // Show assistant response
            this.state.showAssistantText(response.reply);
            
            // Handle Musetalk based on mode
            await this.handleMusetalk(response.reply);
            
        } catch (error) {
            console.error('OpenAI chat failed:', error);
            this.state.setStatus('error');
        }
    }
    
    /**
     * Handle Musetalk avatar generation
     */
    async handleMusetalk(text) {
        try {
            this.state.setStatus('musetalk_connect');
            
            // Call Musetalk start endpoint
            const response = await fetch(`${this.config.apiBase}/api/muse/start`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    sessionId: this.state.getSessionId(),
                    avatarId: this.config.avatarId,
                    text: text
                })
            });
            
            if (!response.ok) {
                throw new Error(`Musetalk start failed: ${response.status}`);
            }
            
            const data = await response.json();
            
            if (data.mode === 'mse') {
                await this.handleMSEStreaming();
            } else {
                await this.handleFilePlayback();
            }
            
        } catch (error) {
            console.error('Musetalk handling failed:', error);
            this.state.setStatus('error');
        }
    }
    
    /**
     * Handle MSE streaming mode
     */
    async handleMSEStreaming() {
        try {
            this.state.setStatus('streaming');
            
            // Check MSE support
            if (!this.player.isMSESupported()) {
                console.warn('MSE not supported, falling back to file mode');
                await this.handleFilePlayback();
                return;
            }
            
            // Initialize MSE
            const videoEl = document.getElementById('player');
            this.player.initMSE(videoEl);
            
            // TODO: Connect to WebSocket for streaming
            console.log('MSE streaming mode - WebSocket integration pending');
            
            // For now, show waiting message
            this.state.showAssistantText('Waiting for stream... (WebSocket integration pending)');
            
        } catch (error) {
            console.error('MSE streaming failed:', error);
            this.state.setStatus('error');
        }
    }
    
    /**
     * Handle file playback mode
     */
    async handleFilePlayback() {
        try {
            this.state.setStatus('streaming');
            
            // TODO: Get actual file URL from Musetalk service
            // For now, use a placeholder
            const placeholderUrl = 'https://sample-videos.com/zip/10/mp4/SampleVideo_1280x720_1mb.mp4';
            
            this.player.playFile(placeholderUrl);
            
            console.log('File playback mode - using placeholder video');
            
        } catch (error) {
            console.error('File playback failed:', error);
            this.state.setStatus('error');
        }
    }
}

// Initialize app when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    new AvatarChatApp();
});
