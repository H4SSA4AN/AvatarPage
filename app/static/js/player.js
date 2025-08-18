/**
 * Video player functionality for MSE streaming and file playback
 */

export class VideoPlayer {
    constructor() {
        this.mediaSource = null;
        this.sourceBuffer = null;
        this.queue = [];
        this.isUpdating = false;
        this.videoElement = null;
        this.mseSupported = false;
        
        // Check MSE support
        this.checkMSESupport();
    }
    
    /**
     * Check if MediaSource Extensions are supported
     */
    checkMSESupport() {
        this.mseSupported = 'MediaSource' in window && MediaSource.isTypeSupported('video/webm; codecs="vp8"');
        console.log(`MSE supported: ${this.mseSupported}`);
        return this.mseSupported;
    }
    
    /**
     * Initialize MSE for streaming
     */
    initMSE(videoEl) {
        if (!this.mseSupported) {
            throw new Error('MediaSource Extensions not supported');
        }
        
        this.videoElement = videoEl;
        
        // Create MediaSource
        this.mediaSource = new MediaSource();
        this.videoElement.src = URL.createObjectURL(this.mediaSource);
        
        this.mediaSource.addEventListener('sourceopen', () => {
            try {
                // Create SourceBuffer for video/webm with VP8 codec
                this.sourceBuffer = this.mediaSource.addSourceBuffer('video/webm; codecs="vp8"');
                this.sourceBuffer.mode = 'segments';
                
                this.sourceBuffer.addEventListener('updateend', () => {
                    this.isUpdating = false;
                    this.processQueue();
                });
                
                this.sourceBuffer.addEventListener('error', (event) => {
                    console.error('SourceBuffer error:', event);
                    this.handleError();
                });
                
                console.log('MSE initialized successfully');
            } catch (error) {
                console.error('Failed to create SourceBuffer:', error);
                this.handleError();
            }
        });
        
        this.mediaSource.addEventListener('error', (event) => {
            console.error('MediaSource error:', event);
            this.handleError();
        });
    }
    
    /**
     * Append video fragment to MSE stream
     */
    append(fragment) {
        if (!this.mseSupported || !this.sourceBuffer) {
            console.warn('MSE not available for appending');
            return;
        }
        
        // Add to queue if currently updating
        if (this.isUpdating) {
            this.queue.push(fragment);
            return;
        }
        
        this.appendFragment(fragment);
    }
    
    /**
     * Append fragment directly to SourceBuffer
     */
    appendFragment(fragment) {
        try {
            this.isUpdating = true;
            this.sourceBuffer.appendBuffer(fragment);
        } catch (error) {
            console.error('Failed to append fragment:', error);
            this.handleError();
        }
    }
    
    /**
     * Process queued fragments
     */
    processQueue() {
        if (this.queue.length > 0 && !this.isUpdating) {
            const fragment = this.queue.shift();
            this.appendFragment(fragment);
        }
    }
    
    /**
     * End the MSE stream
     */
    end() {
        if (this.mediaSource && this.mediaSource.readyState === 'open') {
            this.mediaSource.endOfStream();
            console.log('MSE stream ended');
        }
    }
    
    /**
     * Play a video file
     */
    playFile(url) {
        if (!this.videoElement) {
            console.error('Video element not initialized');
            return;
        }
        
        // Reset video element
        this.videoElement.src = url;
        this.videoElement.load();
        
        // Play when ready
        this.videoElement.addEventListener('canplay', () => {
            this.videoElement.play().catch(error => {
                console.error('Failed to play video:', error);
            });
        }, { once: true });
        
        console.log(`Playing file: ${url}`);
    }
    
    /**
     * Handle errors gracefully
     */
    handleError() {
        // Clear queue
        this.queue = [];
        this.isUpdating = false;
        
        // Reset video element
        if (this.videoElement) {
            this.videoElement.src = '';
        }
        
        console.error('Video player error occurred');
    }
    
    /**
     * Get MSE support status
     */
    isMSESupported() {
        return this.mseSupported;
    }
    
    /**
     * Set video element
     */
    setVideoElement(videoEl) {
        this.videoElement = videoEl;
    }
    
    /**
     * Get current video element
     */
    getVideoElement() {
        return this.videoElement;
    }
}
