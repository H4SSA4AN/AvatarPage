/**
 * Microphone recording functionality
 */

export class MicrophoneRecorder {
    constructor() {
        this.mediaRecorder = null;
        this.audioChunks = [];
        this.isRecording = false;
        this.onChunkCallback = null;
        this.onStopCallback = null;
        this.stream = null;
    }
    
    /**
     * Check if microphone access is supported
     */
    async checkSupport() {
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            throw new Error('MediaRecorder not supported in this browser');
        }
        
        try {
            // Test microphone access
            const testStream = await navigator.mediaDevices.getUserMedia({ 
                audio: {
                    echoCancellation: true,
                    noiseSuppression: true,
                    autoGainControl: true
                } 
            });
            testStream.getTracks().forEach(track => track.stop());
            return true;
        } catch (error) {
            throw new Error(`Microphone access denied: ${error.message}`);
        }
    }
    
    /**
     * Start recording audio
     */
    async start({ onChunk, onStop }) {
        if (this.isRecording) {
            console.warn('Already recording');
            return;
        }
        
        try {
            // Get microphone stream
            this.stream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    echoCancellation: true,
                    noiseSuppression: true,
                    autoGainControl: true
                }
            });
            
            // Create MediaRecorder with audio/webm;codecs=opus
            this.mediaRecorder = new MediaRecorder(this.stream, {
                mimeType: 'audio/webm;codecs=opus'
            });
            
            this.onChunkCallback = onChunk;
            this.onStopCallback = onStop;
            this.audioChunks = [];
            this.isRecording = true;
            
            // Set up event handlers
            this.mediaRecorder.ondataavailable = (event) => {
                if (event.data.size > 0) {
                    this.audioChunks.push(event.data);
                    
                    // Call onChunk callback with the audio chunk
                    if (this.onChunkCallback) {
                        this.onChunkCallback(event.data);
                    }
                }
            };
            
            this.mediaRecorder.onstop = () => {
                this.isRecording = false;
                
                // Create final blob from all chunks
                const audioBlob = new Blob(this.audioChunks, { 
                    type: 'audio/webm;codecs=opus' 
                });
                
                // Stop all tracks
                if (this.stream) {
                    this.stream.getTracks().forEach(track => track.stop());
                    this.stream = null;
                }
                
                // Call onStop callback with the final audio blob
                if (this.onStopCallback) {
                    this.onStopCallback(audioBlob);
                }
                
                console.log('Recording stopped');
            };
            
            this.mediaRecorder.onerror = (event) => {
                console.error('MediaRecorder error:', event.error);
                this.stop();
            };
            
            // Start recording with 250ms timeslice for chunks
            this.mediaRecorder.start(250);
            console.log('Recording started');
            
        } catch (error) {
            console.error('Failed to start recording:', error);
            throw error;
        }
    }
    
    /**
     * Stop recording
     */
    stop() {
        if (!this.isRecording || !this.mediaRecorder) {
            console.warn('Not currently recording');
            return;
        }
        
        if (this.mediaRecorder.state === 'recording') {
            this.mediaRecorder.stop();
        }
    }
    
    /**
     * Check if currently recording
     */
    isCurrentlyRecording() {
        return this.isRecording;
    }
    
    /**
     * Get current recording state
     */
    getState() {
        return this.mediaRecorder ? this.mediaRecorder.state : 'inactive';
    }
}
