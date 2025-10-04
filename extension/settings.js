/**
 * AI Proctor Settings Page Script
 * Manages configuration storage using Chrome Storage API
 */

// Default configuration
const DEFAULT_CONFIG = {
    backendUrl: 'http://localhost:5002',
    frameInterval: 1000,
    maxReconnectAttempts: 5
};

// DOM Elements
const backendUrlInput = document.getElementById('backendUrl');
const frameIntervalInput = document.getElementById('frameInterval');
const maxReconnectAttemptsInput = document.getElementById('maxReconnectAttempts');
const saveBtn = document.getElementById('saveBtn');
const resetBtn = document.getElementById('resetBtn');
const statusMessage = document.getElementById('statusMessage');

// Load saved settings on page load
document.addEventListener('DOMContentLoaded', loadSettings);

// Event listeners
saveBtn.addEventListener('click', saveSettings);
resetBtn.addEventListener('click', resetSettings);

/**
 * Load settings from Chrome storage
 */
function loadSettings() {
    chrome.storage.sync.get(DEFAULT_CONFIG, (config) => {
        backendUrlInput.value = config.backendUrl;
        frameIntervalInput.value = config.frameInterval;
        maxReconnectAttemptsInput.value = config.maxReconnectAttempts;
    });
}

/**
 * Save settings to Chrome storage
 */
function saveSettings() {
    // Validate inputs
    const backendUrl = backendUrlInput.value.trim();
    const frameInterval = parseInt(frameIntervalInput.value);
    const maxReconnectAttempts = parseInt(maxReconnectAttemptsInput.value);

    if (!backendUrl) {
        showMessage('Backend URL cannot be empty', 'error');
        return;
    }

    if (!isValidUrl(backendUrl)) {
        showMessage('Please enter a valid URL (e.g., http://localhost:5002)', 'error');
        return;
    }

    if (frameInterval < 500 || frameInterval > 5000) {
        showMessage('Frame interval must be between 500 and 5000 ms', 'error');
        return;
    }

    if (maxReconnectAttempts < 1 || maxReconnectAttempts > 10) {
        showMessage('Max reconnect attempts must be between 1 and 10', 'error');
        return;
    }

    // Save to Chrome storage
    const config = {
        backendUrl,
        frameInterval,
        maxReconnectAttempts
    };

    chrome.storage.sync.set(config, () => {
        showMessage('Settings saved successfully! ✓', 'success');
        console.log('[AI Proctor Settings] Saved configuration:', config);
    });
}

/**
 * Reset settings to defaults
 */
function resetSettings() {
    chrome.storage.sync.set(DEFAULT_CONFIG, () => {
        loadSettings();
        showMessage('Settings reset to defaults', 'success');
        console.log('[AI Proctor Settings] Reset to default configuration');
    });
}

/**
 * Display status message
 */
function showMessage(message, type) {
    statusMessage.textContent = message;
    statusMessage.className = `status-message ${type}`;
    statusMessage.style.display = 'block';

    // Auto-hide after 3 seconds
    setTimeout(() => {
        statusMessage.style.display = 'none';
    }, 3000);
}

/**
 * Validate URL format
 */
function isValidUrl(string) {
    try {
        const url = new URL(string);
        return url.protocol === 'http:' || url.protocol === 'https:';
    } catch (_) {
        return false;
    }
}
