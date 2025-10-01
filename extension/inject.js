// Get the Socket.IO URL from the script's data attribute
var currentScript = document.currentScript;
var socketIOUrl = currentScript ? currentScript.getAttribute('data-socketio-url') : null;

if (!socketIOUrl) {
    console.error('[AI Proctor Inject] No Socket.IO URL provided');
    window.postMessage({ type: 'SOCKETIO_ERROR' }, '*');
} else {
    // Load Socket.IO from the extension
    var script = document.createElement('script');
    script.src = socketIOUrl;
    script.onload = function() {
        console.log('[AI Proctor Inject] Socket.IO loaded in page context');
        
        // Wait a bit for io to be available
        setTimeout(function() {
            if (typeof window.io !== 'undefined') {
                console.log('[AI Proctor Inject] window.io is available');
                window.postMessage({ type: 'SOCKETIO_READY' }, '*');
            } else {
                console.error('[AI Proctor Inject] window.io is not available after load');
                window.postMessage({ type: 'SOCKETIO_ERROR' }, '*');
            }
        }, 100);
    };
    script.onerror = function() {
        console.error('[AI Proctor Inject] Failed to load Socket.IO');
        window.postMessage({ type: 'SOCKETIO_ERROR' }, '*');
    };
    document.head.appendChild(script);
}
