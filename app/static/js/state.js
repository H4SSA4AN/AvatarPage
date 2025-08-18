/**
 * State management for the application
 */

export class AppState {
    constructor() {
        this.currentStatus = 'idle';
        this.sessionId = null;
        this.isRecording = false;
        
        // Status definitions
        this.statuses = {
            idle: { text: 'idle', class: 'status-idle' },
            recording: { text: 'recording', class: 'status-recording' },
            processing: { text: 'processing', class: 'status-processing' },
            connected: { text: 'connected', class: 'status-streaming' },
            stt: { text: 'speech to text', class: 'status-processing' },
            chat: { text: 'chat processing', class: 'status-processing' },
            tts: { text: 'text to speech', class: 'status-processing' },
            musetalk_connect: { text: 'connecting to avatar', class: 'status-processing' },
            streaming: { text: 'streaming', class: 'status-streaming' },
            error: { text: 'error', class: 'status-error' }
        };
        
        this.statusElement = document.getElementById('status');
        this.micElement = document.getElementById('mic');
        this.assistantTextElement = document.getElementById('assistantText');
    }
    
    /**
     * Update the current status and UI
     */
    setStatus(status) {
        if (!this.statuses[status]) {
            console.warn(`Unknown status: ${status}`);
            return;
        }
        
        this.currentStatus = status;
        const statusInfo = this.statuses[status];
        
        // Update status badge
        this.statusElement.textContent = statusInfo.text;
        this.statusElement.className = `status-badge ${statusInfo.class}`;
        
        console.log(`Status changed to: ${status}`);
    }
    
    /**
     * Set recording state and update mic button
     */
    setRecording(isRecording) {
        this.isRecording = isRecording;
        
        if (isRecording) {
            this.micElement.classList.add('recording');
            this.micElement.textContent = '⏹️';
            this.micElement.title = 'Click to stop recording';
        } else {
            this.micElement.classList.remove('recording');
            this.micElement.textContent = '🎤';
            this.micElement.title = 'Press and hold to record';
        }
    }
    
    /**
     * Set session ID
     */
    setSessionId(sessionId) {
        this.sessionId = sessionId;
        console.log(`Session ID set: ${sessionId}`);
    }
    
    /**
     * Show assistant response text
     */
    showAssistantText(text) {
        this.assistantTextElement.textContent = text;
        this.assistantTextElement.classList.remove('hidden');
    }
    
    /**
     * Hide assistant response text
     */
    hideAssistantText() {
        this.assistantTextElement.classList.add('hidden');
    }
    
    /**
     * Get current status
     */
    getStatus() {
        return this.currentStatus;
    }
    
    /**
     * Get session ID
     */
    getSessionId() {
        return this.sessionId;
    }
    
    /**
     * Check if currently recording
     */
    isCurrentlyRecording() {
        return this.isRecording;
    }
}
