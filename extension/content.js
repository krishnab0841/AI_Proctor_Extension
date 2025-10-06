/**
 * AI Interview Proctor - INTERVIEWER'S Content Script
 * This script is injected into the meeting page to monitor a candidate.
 */
(function () {
    if (window.aiProctorHasRun) { return; }
    window.aiProctorHasRun = true;

    // --- Global State ---
    let isMonitoring = false;
    let socket;
    let requestFrameId = null;
    let targetVideoElement = null;
    let isSelectingCandidate = false;
    let reconnectAttempts = 0;
    let maxReconnectAttempts = 5;
    let frameErrorCount = 0;
    let maxFrameErrors = 10;
    const canvasElement = document.createElement('canvas');
    const ctx = canvasElement.getContext('2d');

    // Configuration (loaded from Chrome storage)
    let BACKEND_URL = 'http://localhost:5002'; // Default value, will be overwritten by stored settings
    let FRAME_CAPTURE_INTERVAL = 500; // ms between frames

    // --- Main UI Creation ---
    function createProctorUI() {
        const widget = document.createElement('div');
        widget.id = 'ai-proctor-widget';
        widget.innerHTML = `
            <div id="proctor-header">
                <h3>AI Proctor</h3>
                <span id="proctor-status-indicator"></span>
            </div>
            <div id="proctor-body">
                <div id="proctor-alert-display">
                    <span class="log-placeholder">Loading...</span>
                </div>
                <div id="proctor-controls">
                    <button id="proctor-select-btn">Select Candidate</button>
                    <button id="proctor-start-btn" disabled>Start Monitoring</button>
                </div>
                <div id="proctor-manual-controls" style="display: none;">
                    <button id="proctor-clear-btn" class="proctor-btn secondary">Clear Alerts</button>
                </div>
            </div>
        `;
        document.body.appendChild(widget);

        // Inject necessary assets
        const styleLink = document.createElement('link');
        styleLink.rel = 'stylesheet';
        styleLink.type = 'text/css';
        styleLink.href = chrome.runtime.getURL('style.css');
        document.head.appendChild(styleLink);

        makeDraggable(widget);
    }

    // --- UI Update and Alert Handling ---
    function displayAlert(alertData) {
        const alertDisplay = document.getElementById('proctor-alert-display');
        if (!alertDisplay) {
            console.log('[AI Proctor] Alert suppressed: UI not ready.', alertData);
            return;
        }

        // Remove placeholder if it exists
        const placeholder = alertDisplay.querySelector('.log-placeholder');
        if (placeholder) {
            alertDisplay.innerHTML = ''; // Clear the "Loading..." text
        }

        let severity = 'info';
        if (alertData.alert.includes('🔴')) severity = 'high';
        else if (alertData.alert.includes('🟠')) severity = 'medium';
        else if (alertData.alert.includes('🟡')) severity = 'low';
        if (alertData.type === 'request_360_scan') severity = 'request';

        const alertElement = document.createElement('div');
        alertElement.className = `alert-item ${severity}`;
        
        const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });

        alertElement.innerHTML = `
            <div class="alert-header">
                <strong>${alertData.alert}</strong>
                <span class="alert-time">${time}</span>
            </div>
            <p>${alertData.description}</p>
        `;

        // Prepend the new alert and keep the list scrolled to the top
        // Add an 'OK' button for 360 scan requests
        if (alertData.type === 'request_360_scan') {
            const okButton = document.createElement('button');
            okButton.textContent = 'OK';
            okButton.className = 'ok-button';
            okButton.onclick = () => {
                alertElement.remove();
                // Optionally, send a confirmation back to the server
                if (socket && socket.connected) {
                    socket.emit('client_response', { alert_type: 'request_360_scan', response: 'acknowledged' });
                }
            };
            alertElement.appendChild(okButton);
        }

        alertDisplay.insertBefore(alertElement, alertDisplay.firstChild);

        // Optional: Limit the number of alerts shown to prevent the UI from getting too long
        const maxAlerts = 20;
        if (alertDisplay.children.length > maxAlerts) {
            alertDisplay.removeChild(alertDisplay.lastChild);
        }
    }

    // --- Core Monitoring Logic ---
    function toggleMonitoring() {
        if (isMonitoring) {
            stopMonitoring();
        } else {
            startMonitoring();
        }
    }

    function startMonitoring() {
        try {
            if (typeof io === 'undefined') {
                displayAlert({
                    alert: "🔴 Initialization Error",
                    description: "Socket.IO library not loaded yet. Please wait a moment and try again."
                });
                return;
            }

            if (!targetVideoElement) {
                displayAlert({
                    alert: "🔴 Error: No Candidate Selected",
                    description: "Please click 'Select Candidate' and choose a video to monitor before starting."
                });
                return;
            }

            reconnectAttempts = 0;
            frameErrorCount = 0;

            const auth = { token: config.secretKey };


            socket = io(BACKEND_URL, {
                auth,
                transports: ["websocket", "polling"],
                reconnection: true,
                reconnectionDelay: 1000,
                reconnectionAttempts: maxReconnectAttempts,
                timeout: 10000
            });

            socket.on('connect', () => {
                console.log('[AI Proctor] Connected to backend server');
                isMonitoring = true;
                reconnectAttempts = 0;
                frameErrorCount = 0;
                updateUIState('start');
                window.addEventListener('blur', onTabSwitch);
                // Start the frame capture loop
                sendVideoFrame();
            });

            socket.on('proctoring_alert', (data) => {
                displayAlert(data);
            });

            socket.on('disconnect', (reason) => {
                console.warn('[AI Proctor] Disconnected:', reason);
                if (isMonitoring) {
                    displayAlert({
                        alert: "🔴 Connection Lost",
                        description: `Disconnected from the backend server. Reason: ${reason}` 
                    });
                    if (reason === 'io server disconnect' || reason === 'io client disconnect') {
                        stopMonitoring();
                    }
                }
            });

            socket.on('connect_error', (error) => {
                if (!document.getElementById('ai-proctor-widget')) return;
                console.error('[AI Proctor] Connection error:', error);
                reconnectAttempts++;
                displayAlert({
                    alert: "⚠️ Connection Error",
                    description: `Failed to connect to backend (attempt ${reconnectAttempts}/${maxReconnectAttempts}). Is the server running?` 
                });

                if (reconnectAttempts >= maxReconnectAttempts) {
                    displayAlert({
                        alert: "🔴 Connection Failed",
                        description: "Could not connect to backend server. Please ensure it's running on port 5002."
                    });
                    stopMonitoring();
                }
            });

            socket.on('error', (error) => {
                console.error('[AI Proctor] Socket error:', error);
            });
        } catch (e) {
            console.error('[AI Proctor] Error starting monitoring:', e);
            displayAlert({
                alert: "🔴 Initialization Error",
                description: `Failed to start monitoring: ${e.message}` 
            });
        }
    }

    function stopMonitoring() {
        console.log('[AI Proctor] Stopping monitoring');
        
        // --- Core Logic (always runs) ---
        isMonitoring = false;
        if (socket) {
            socket.disconnect();
            socket = null;
        }
        if (requestFrameId) {
            clearTimeout(requestFrameId);
            requestFrameId = null;
        }
        window.removeEventListener('blur', onTabSwitch);
        reconnectAttempts = 0;
        frameErrorCount = 0;

        // --- UI Logic (only runs if UI is ready) ---
        const proctorWidget = document.getElementById('ai-proctor-widget');
        if (!proctorWidget) {
            // If the UI isn't ready, just ensure the core logic has stopped.
            if (targetVideoElement) {
                targetVideoElement.classList.remove('ai-proctor-target-video');
            }
            targetVideoElement = null;
            return;
        }

        // Update UI state and show final alert
        updateUIState('stop');
        displayAlert({ alert: "⚪ Session Ended", description: "Monitoring has stopped." });

        // Clear selection styling AFTER updating UI
        if (targetVideoElement) {
            targetVideoElement.classList.remove('ai-proctor-target-video');
        }
        targetVideoElement = null;

        // Re-enable selection button
        const selectBtn = document.getElementById('proctor-select-btn');
        if (selectBtn) {
            selectBtn.disabled = false;
            // Correctly set button text based on whether a candidate is still selected
            selectBtn.textContent = targetVideoElement ? 'Change Candidate' : 'Select Candidate';
        }

    }

    // --- Frame Capture & Event Handling ---
    function sendVideoFrame() {
        if (!isMonitoring || !targetVideoElement) return;

        // Schedule the next frame capture
        requestFrameId = setTimeout(sendVideoFrame, FRAME_CAPTURE_INTERVAL);

        if (targetVideoElement.readyState < 2 || targetVideoElement.videoWidth === 0) {
            return; // Wait for the video to be ready
        }

        if (!document.body.contains(targetVideoElement)) {
            displayAlert({
                alert: "🔴 ERROR: Candidate Video Lost",
                description: "The selected candidate's video element is no longer available. Please select a new one."
            });
            stopMonitoring();
            return;
        }

        try {
            canvasElement.width = targetVideoElement.videoWidth;
            canvasElement.height = targetVideoElement.videoHeight;
            ctx.drawImage(targetVideoElement, 0, 0, canvasElement.width, canvasElement.height);

            const frameData = canvasElement.toDataURL('image/jpeg', 0.6);

            if (socket && socket.connected) {
                socket.emit('video_frame', frameData);
                frameErrorCount = 0;
            } else {
                console.warn('[AI Proctor] Socket not connected, skipping frame');
            }
        } catch (e) {
            frameErrorCount++;
            console.error('[AI Proctor] Error capturing frame:', e.message);

            if (frameErrorCount >= maxFrameErrors) {
                displayAlert({
                    alert: "🔴 Capture Error",
                    description: `Failed to capture frames ${frameErrorCount} times. Stopping monitoring.` 
                });
                stopMonitoring();
            }
        }
    }

    function onTabSwitch() {
        if (isMonitoring && socket && socket.connected) {
            try {
                const alertData = {
                    alert: "🟡 ATTENTION: Interviewer Tab Switch",
                    description: "Your focus shifted away from the meeting. Proctoring paused."
                };
                socket.emit('client_alert', alertData);
            } catch (e) {
                console.error('[AI Proctor] Error sending tab switch alert:', e);
            }
        }
    }

    // --- Helper Functions ---

    // --- Candidate Selection Mode (Overlay System) ---
    function enterCandidateSelectionMode() {
        if (isSelectingCandidate) {
            exitCandidateSelectionMode();
            return;
        }
        isSelectingCandidate = true;
        console.log('[AI Proctor] Entering candidate selection mode.');
        displayAlert({ alert: '🟡 Action Required', description: 'Click the \'Select\' button on the candidate\'s video.' });

        const videos = document.querySelectorAll('video');
        if (videos.length === 0) {
            displayAlert({ alert: '🔴 Error', description: 'No video feeds found on the page.' });
            isSelectingCandidate = false;
            return;
        }

        videos.forEach((video, index) => {
            // Filter out small or hidden video elements
            if (video.offsetHeight < 100 || video.offsetWidth < 100 || video.readyState < 2) return;

            const rect = video.getBoundingClientRect();
            const overlay = document.createElement('div');
            overlay.className = 'ai-proctor-selection-overlay';
            overlay.style.top = `${rect.top + window.scrollY}px`;
            overlay.style.left = `${rect.left + window.scrollX}px`;
            overlay.style.width = `${rect.width}px`;
            overlay.style.height = `${rect.height}px`;

            const selectBtn = document.createElement('button');
            selectBtn.className = 'ai-proctor-overlay-btn';
            selectBtn.textContent = 'Select Candidate';
            selectBtn.onclick = () => selectCandidate(video);

            overlay.appendChild(selectBtn);
            document.body.appendChild(overlay);
        });
        
        const selectBtn = document.getElementById('proctor-select-btn');
        if (selectBtn) selectBtn.textContent = 'Cancel Selection';
    }

    function exitCandidateSelectionMode() {
        document.querySelectorAll('.ai-proctor-selection-overlay').forEach(overlay => overlay.remove());
        isSelectingCandidate = false;
        const selectBtn = document.getElementById('proctor-select-btn');
        if (selectBtn) selectBtn.textContent = targetVideoElement ? 'Change Candidate' : 'Select Candidate';
    }

    function selectCandidate(videoElement) {
        // Clear previous selection if any
        if (targetVideoElement) {
            targetVideoElement.classList.remove('ai-proctor-target-video');
        }

        // Set new target
        targetVideoElement = videoElement;
        targetVideoElement.classList.add('ai-proctor-target-video');
        console.log('[AI Proctor] Candidate video selected:', targetVideoElement);

        // Update UI
        const startBtn = document.getElementById('proctor-start-btn');
        if (startBtn) startBtn.disabled = false;

        displayAlert({ alert: '✅ Candidate Selected', description: 'Ready to start monitoring. Click the start button.' });

        exitCandidateSelectionMode();
    }

    function updateUIState(state) {
        const manualControls = document.getElementById('proctor-manual-controls');
        const startBtn = document.getElementById('proctor-start-btn');
        const statusIndicator = document.getElementById('proctor-status-indicator');

        if (!startBtn || !statusIndicator) {
            return; // Exit if UI elements are not ready
        }

        if (state === 'start') {
            startBtn.textContent = "Stop Monitoring";
            startBtn.classList.add('stop');
            statusIndicator.style.backgroundColor = '#22c55e';
            statusIndicator.style.animation = 'pulse-green 2s infinite';
            if (manualControls) manualControls.style.display = 'flex';
        } else {
            startBtn.textContent = "Start Monitoring";
            startBtn.classList.remove('stop');
            statusIndicator.style.backgroundColor = '#ef4444';
            statusIndicator.style.animation = 'pulse-red 2s infinite';
            if (manualControls) manualControls.style.display = 'none';
        }
    }

    function makeDraggable(element) {
        let isDragging = false, offsetX, offsetY;
        const header = element.querySelector('#proctor-header');
        if (!header) return;

        header.onmousedown = (e) => {
            isDragging = true;
            offsetX = e.clientX - element.getBoundingClientRect().left;
            offsetY = e.clientY - element.getBoundingClientRect().top;
            header.style.cursor = 'grabbing';
        };
        document.onmousemove = (e) => {
            if (!isDragging) return;
            element.style.left = (e.clientX - offsetX) + 'px';
            element.style.top = (e.clientY - offsetY) + 'px';
        };
        document.onmouseup = () => {
            isDragging = false;
            header.style.cursor = 'grab';
        };
    }

    // --- Error Reporting ---
    window.addEventListener('error', (event) => {
        if (event.message && event.message.includes('AI Proctor')) {
        }
    });


    // --- Initialize Extension ---
    const initExtension = () => {
        try {
            if (typeof io !== 'undefined') {
                console.log('[AI Proctor] Socket.IO ready');
                const startBtn = document.getElementById('proctor-start-btn');
                const selectBtn = document.getElementById('proctor-select-btn');

                if (selectBtn) {
                    selectBtn.addEventListener('click', enterCandidateSelectionMode);
                }

                if (startBtn) {
                    startBtn.addEventListener('click', toggleMonitoring);
                }


                const clearBtn = document.getElementById('proctor-clear-btn');
                if (clearBtn) {
                    clearBtn.addEventListener('click', () => {
                        const alertDisplay = document.getElementById('proctor-alert-display');
                        if (alertDisplay) {
                            alertDisplay.innerHTML = '<span class="log-placeholder">Alerts cleared. Waiting for new events...</span>';
                        }
                    });
                }
            } else {
                console.error('[AI Proctor] window.io not available');
                displayAlert({
                    alert: "🔴 Critical Error",
                    description: "Failed to initialize WebSocket connection."
                });
            }
        } catch (error) {
            console.error('[AI Proctor] Initialization error:', error);
            displayAlert({
                alert: "🔴 Initialization Error",
                description: error.message
            });
        }
    };

    // --- Load Configuration from Chrome Storage ---
    let config = {}; // To hold the loaded configuration

    function loadConfiguration(callback) {
        const defaults = {
            backendUrl: 'http://localhost:5002',
            frameInterval: 1000,
            maxReconnectAttempts: 5,
            secretKey: '' // Ensure secretKey is part of the loaded config
        };
        
        chrome.storage.sync.get(defaults, (loadedConfig) => {
            config = loadedConfig; // Store loaded config globally
            BACKEND_URL = config.backendUrl;
            FRAME_CAPTURE_INTERVAL = config.frameInterval;
            maxReconnectAttempts = config.maxReconnectAttempts;
            console.log('[AI Proctor] Loaded configuration:', loadedConfig);
            if (callback) callback();
        });
    }

    // --- Initialize ---
    try {
        // Load configuration first, then initialize the rest of the extension
        loadConfiguration(() => {
            // Use a robust polling mechanism to wait for the meeting UI to be ready
            const initInterval = setInterval(() => {
                const meetUIReady = document.querySelector('video');
                
                if (meetUIReady) {
                    console.log('[AI Proctor] Meeting UI is ready. Initializing...');
                    clearInterval(initInterval);
                    
                    // Create the UI and set up event listeners
                    createProctorUI();
                    initExtension();
                }
            }, 1000); // Check every second
        });
        console.log('[AI Proctor] Waiting for configuration and meeting UI...');
    } catch (e) {
        console.error('[AI Proctor] Failed to initialize:', e);
        alert('AI Proctor failed to initialize. Please refresh the page.');
    }
})();
