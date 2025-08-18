/**
 * Main application logic - Simplified test version
 */

console.log('Main.js module loaded successfully');

// Simple test to see if we can access DOM elements
document.addEventListener('DOMContentLoaded', () => {
    console.log('DOM loaded, testing basic functionality...');
    
    // Test if we can find the mic button
    const micButton = document.getElementById('mic');
    if (micButton) {
        console.log('Found mic button:', micButton);
        
        // Add a simple click handler for testing
        micButton.addEventListener('click', () => {
            console.log('Mic button clicked!');
            alert('Mic button works! This is a test.');
        });
        
        // Update debug info
        const jsStatus = document.getElementById('jsStatus');
        if (jsStatus) {
            jsStatus.textContent = 'JavaScript: Basic functionality working';
        }
    } else {
        console.error('Could not find mic button');
    }
    
    // Test configuration loading
    const body = document.body;
    const config = {
        apiBase: body.dataset.apiBase || window.location.origin,
        avatarId: body.dataset.avatar || 'default-01',
        museMode: body.dataset.museMode || 'file'
    };
    
    console.log('Configuration loaded:', config);
});

// Export a simple object to show the module is working
export const testModule = {
    name: 'AvatarChatApp',
    version: '1.0.0',
    status: 'loaded'
};
