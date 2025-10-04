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
    let reconnectAttempts = 0;
    let maxReconnectAttempts = 5;
    let frameErrorCount = 0;
    let maxFrameErrors = 10;
    const canvasElement = document.createElement('canvas');
    const ctx = canvasElement.getContext('2d');

    // Configuration (loaded from Chrome storage)
    let BACKEND_URL = 'http://localhost:5002';
    let FRAME_CAPTURE_INTERVAL = 1000; // ms between frames

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
                <button id="proctor-start-btn" disabled>Start Monitoring</button>
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
        if (!alertDisplay) return;

        let severity = 'info';
        if (alertData.alert.includes('🔴')) severity = 'high';
        else if (alertData.alert.includes('🟠')) severity = 'medium';
        else if (alertData.alert.includes('🟡')) severity = 'low';

        alertDisplay.innerHTML = `
            <div class="alert-item ${severity}">
                <strong>${alertData.alert}</strong>
                <p>${alertData.description}</p>
            </div>
        `;
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

            targetVideoElement = findCandidateVideoElement();
            if (!targetVideoElement) {
                displayAlert({
                    alert: "🔴 Error",
                    description: "Could not find a candidate's video. Pin the candidate or ensure their video is the largest on screen."
                });
                return;
            }

            reconnectAttempts = 0;
            frameErrorCount = 0;

            socket = io(BACKEND_URL, {
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
        targetVideoElement = null;
        reconnectAttempts = 0;
        frameErrorCount = 0;
        updateUIState('stop');
        displayAlert({ alert: "⚪ Session Ended", description: "Monitoring has stopped." });
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
            console.warn('[AI Proctor] Video element removed from DOM, searching for new one');
            targetVideoElement = findCandidateVideoElement();
            if (!targetVideoElement) {
                displayAlert({
                    alert: "⚠️ Video Lost",
                    description: "Candidate video element disappeared. Monitoring paused."
                });
                return;
            }
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
    function findCandidateVideoElement() {
        const videos = Array.from(document.querySelectorAll('video'));
        if (videos.length === 0) return null;

        const largeVideos = videos.filter(v => v.offsetHeight > 150 && v.readyState >= 2);

        if (largeVideos.length === 1) return largeVideos[0];

        largeVideos.sort((a, b) => (b.offsetWidth * b.offsetHeight) - (a.offsetWidth * a.offsetHeight));

        return largeVideos.length > 0 ? largeVideos[0] : null;
    }

    function updateUIState(state) {
        const startBtn = document.getElementById('proctor-start-btn');
        const statusIndicator = document.getElementById('proctor-status-indicator');

        if (state === 'start') {
            startBtn.textContent = "Stop Monitoring";
            startBtn.classList.add('stop');
            statusIndicator.style.backgroundColor = '#22c55e';
            statusIndicator.style.animation = 'pulse-green 2s infinite';
        } else {
            startBtn.textContent = "Start Monitoring";
            startBtn.classList.remove('stop');
            statusIndicator.style.backgroundColor = '#ef4444';
            statusIndicator.style.animation = 'pulse-red 2s infinite';
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
            element.style.left = `${e.clientX - offsetX}px`;
            element.style.top = `${e.clientY - offsetY}px`;
        };
        document.onmouseup = () => {
            isDragging = false;
            header.style.cursor = 'grab';
        };
    }

    // --- Error Reporting ---
    window.addEventListener('error', (event) => {
        if (event.message && event.message.includes('AI Proctor')) {
            console.error('[AI Proctor] Global error:', event.error);
        }
    });


    // --- Initialize Extension ---
    const initExtension = () => {
        try {
            if (typeof io !== 'undefined') {
                console.log('[AI Proctor] Socket.IO ready');
                const startBtn = document.getElementById('proctor-start-btn');
                if (startBtn) {
                    startBtn.disabled = false;
                    startBtn.addEventListener('click', toggleMonitoring);
                }
                displayAlert({
                    alert: "✅ Ready",
                    description: "Click 'Start Monitoring' to begin."
                });
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
    function loadConfiguration(callback) {
        const defaults = {
            backendUrl: 'http://localhost:5002',
            frameInterval: 1000,
            maxReconnectAttempts: 5
        };
        
        chrome.storage.sync.get(defaults, (config) => {
            BACKEND_URL = config.backendUrl;
            FRAME_CAPTURE_INTERVAL = config.frameInterval;
            maxReconnectAttempts = config.maxReconnectAttempts;
            console.log('[AI Proctor] Loaded configuration:', config);
            if (callback) callback();
        });
    }

    // --- Initialize ---
    try {
        // Load configuration first, then initialize
        loadConfiguration(() => {
            // Use a robust polling mechanism to initialize the extension
            const initInterval = setInterval(() => {
                // Wait for a video element to be present, a reliable sign the meeting is active.
                const meetUIReady = document.querySelector('video');
                
                if (meetUIReady) {
                    console.log('[AI Proctor] Meeting UI is ready. Initializing...');
                    clearInterval(initInterval);
                    // Only create the UI and initialize once the video is ready
                    createProctorUI();
                    initExtension();
                }
            }, 1000); // Check every second
        });
        console.log('[AI Proctor] Extension initialized successfully');
    } catch (e) {
        console.error('[AI Proctor] Failed to initialize:', e);
        alert('AI Proctor failed to initialize. Please refresh the page.');
    }
})();
