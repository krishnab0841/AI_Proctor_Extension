# AI Interview Proctor

A sophisticated, real-time proctoring tool designed as a browser extension for **interviewers**. It integrates directly into video conferencing platforms to automatically detect and flag potential cheating behaviors from the candidate's video feed. This version features an optimized AI model for better performance and reliability.

## ✨ Core Features

- **Advanced AI-Powered Tracking**:
  - **Gaze & Head Pose Detection**: Uses MediaPipe to track where the candidate is looking.
  - **Suspicious Object Detection**: Employs a YOLOv5 model to identify high-risk objects like phones, books, and extra people.
  - **Multiple Person Detection**: Flags if more than one person is in the frame.
- **Intelligent Alerts & Analysis**:
  - **Behavioral Scoring**: A real-time suspicion score (0-100) that increases based on patterns of suspicious behavior.
  - **Contextual Analysis**: Uses a local image captioning model (Salesforce BLIP) to efficiently describe scenes when high-risk objects are detected.
- **Proctor Controls & UX**:
  - **Automated 360° Scan**: Automatically requests a 360-degree environmental scan 5 minutes after monitoring begins.
  - **Interactive Alerts**: 360-scan requests include an "OK" button for candidate acknowledgment.
  - **Clearable Alert Feed**: Proctors can clear the alert list at any time.
- **Secure and Configurable**:
  - **Token-Based Authentication**: Secures the WebSocket connection between the extension and the backend.
  - **Centralized Configuration**: All key parameters for the backend and frontend are easily configurable.
  - **Local First**: All AI models, including the lightweight BLIP model, run locally ensuring privacy and eliminating the need for external API keys or subscriptions.

## 🆕 Recent Updates

- **Optimized AI Model**: Switched to Salesforce's BLIP model for faster and more efficient image analysis.
- **Simplified UI**: Removed manual scan button for a cleaner interface.
- **Automated 360° Scan**: Now automatically triggers a single 360° scan 5 minutes after monitoring starts.
- **Improved Stability**: Enhanced WebSocket connection handling for better reliability.

## 🔄 Workflow

```mermaid
flowchart TD
    subgraph Proctor's Browser (Extension)
        A[Start Monitoring] --> B[Capture Video Frame];
        B --> D[Send Frame to Backend];
        I[Receive Alert] --> J[Display in Proctor Widget];
        K[Manual Trigger] --> L[Send Request to Backend];
    end

    subgraph Local Server (Backend)
        D --> E{Analyze Frame};
        E -->|Object/Gaze Detection| F[Update Suspicion Score];
        F --> G{Threshold Met?};
        G -->|Yes| H[Emit Alert];
        G -->|No| D;
        H --> I;
        L --> E;
    end
```

## 🚀 Quick Start

### Prerequisites

- Python 3.9+
- A Chromium-based browser (Google Chrome, Brave, etc.)

### 1. Backend Setup

1.  **Navigate to the backend directory**:
    ```bash
    cd backend
    ```
2.  **Create and activate a virtual environment**:
    ```bash
    # For Windows
    python -m venv venv
    .\venv\Scripts\activate

    # For macOS/Linux
    python3 -m venv venv
    source venv/bin/activate
    ```
3.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```
4.  **Configure the backend**:
    - Open `backend/config.py`.
    - Change the `SECRET_KEY` to a new, random, and secure string. **This is a critical security step.**

### 2. Frontend Setup

1.  **Open your browser** and navigate to `chrome://extensions`.
2.  **Enable Developer Mode** using the toggle in the top-right corner.
3.  Click **"Load unpacked"** and select the `extension` folder from this project.
4.  **Configure the extension**:
    - Click the new AI Proctor extension icon in your toolbar and select **Options**.
    - Enter the same `SECRET_KEY` you set in the backend configuration.
    - Verify the other settings and click **Save**.

### 3. Running the Application

1.  **Start the backend server**:
    ```bash
    # Make sure you are in the 'backend' directory with your virtual environment active
    python main.py
    ```
2.  **Join a video call** on a supported platform.
3.  The **AI Proctor widget** will appear on the page.
4.  Click **"Select Candidate"** and choose the video feed you want to monitor.
5.  Click **"Start Monitoring"** to begin the analysis.

## ⚙️ Configuration

### Backend (`backend/config.py`)

All backend settings are managed in `config.py`. Key settings include:

- `SECRET_KEY`: The secret token for authenticating clients.
- `YOLO_CONFIDENCE_THRESHOLD`: The minimum confidence for an object to be detected (0.0 to 1.0).
- `SUSPICION_SCORE_THRESHOLD`: The score at which a high-suspicion alert is triggered.
- `INITIAL_360_SCAN_DELAY`: The time for the first 360-scan request (in seconds).
- `SUBSEQUENT_360_SCAN_INTERVAL`: The interval for subsequent 360-scan requests.

### Frontend (Extension Options Page)

- **Backend Server URL**: The address of your running backend server.
- **Secret Key**: The authentication token.
- **Frame Capture Interval**: The time between frame captures (in milliseconds).

## Project Structure

```
AI_Proctor_Extension/
├── backend/                 # Python backend server
│   ├── main.py              # FastAPI/Socket.IO server and main logic
│   ├── enhanced_detection.py # Advanced detection algorithms
│   ├── config.py            # All backend configuration
│   └── requirements.txt     # Python dependencies
│
├── extension/               # Browser extension source
│   ├── manifest.json        # Extension metadata and permissions
│   ├── content.js           # Injects the UI and handles communication
│   ├── settings.html        # Extension options page UI
│   ├── settings.js          # Logic for the options page
│   └── style.css            # Styles for the proctor widget
│
└── README.md               # This documentation
```

## ⚖️ Privacy & Ethics

- **Transparency is key**: Always inform candidates that a proctoring tool is in use.
- **Compliance**: Ensure your use of this tool complies with all local privacy laws and regulations.
- **Use as an Indicator**: This tool is designed to flag potential issues, not to make final decisions. Always use alerts as a starting point for further investigation.

## License

This project is open-source and available under the MIT License.