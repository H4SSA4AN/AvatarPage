/**
 * OpenAI API client functionality
 */

export class OpenAIClient {
    constructor(apiBase) {
        this.apiBase = apiBase || window.location.origin;
    }
    
    /**
     * Send chat request to OpenAI via server
     */
    async postChat({ text, sessionId }) {
        if (!text) {
            throw new Error('Text is required for chat request');
        }
        
        try {
            const response = await fetch(`${this.apiBase}/api/openai/chat`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    text: text,
                    sessionId: sessionId
                })
            });
            
            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(errorData.error || `HTTP ${response.status}: ${response.statusText}`);
            }
            
            const data = await response.json();
            return data;
            
        } catch (error) {
            console.error('OpenAI chat request failed:', error);
            throw error;
        }
    }
    
    /**
     * Get API base URL
     */
    getApiBase() {
        return this.apiBase;
    }
    
    /**
     * Set API base URL
     */
    setApiBase(apiBase) {
        this.apiBase = apiBase;
    }
}
