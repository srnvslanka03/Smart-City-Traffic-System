# 🚦 Adaptive Traffic Light Control System

[![Python 3.11.3](https://img.shields.io/badge/python-3.11.3-blue.svg)](https://www.python.org/downloads/release/python-3113/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Open in GitHub](https://img.shields.io/badge/Open%20in-GitHub-blue?logo=github)](https://github.com/srnvslanka03/Smart-City-Traffic-System)

An intelligent traffic management system that uses computer vision to analyze traffic density and optimize traffic light timings in real-time, reducing congestion and improving traffic flow.

## 🌟 Features

- Real-time vehicle detection using YOLO
- Adaptive traffic light control based on vehicle density
- Web-based dashboard for monitoring
- Simulation mode for testing and demonstration
- Cross-platform support (Windows, Linux, macOS)

## 🚀 Quick Start

### Prerequisites

- Python 3.11.3 (recommended) or 3.8+
- Git
- Web browser (Chrome, Firefox, or Edge recommended)
- 4GB+ RAM (8GB recommended for better performance)

### Windows Installation (Recommended)

1. **Download and extract** the project or clone it using Git:
   ```
   
   git clone https://github.com/srnvslanka03/Smart-City-Traffic-System-
   
   ```

2. **Run the setup script** (double-click `run.bat` or run in Command Prompt):
   ```
   run.bat
   ```
   This will:
   - Create a virtual environment
   - Install all required dependencies
   - Start the web application

3. **Access the application** in your browser:
   ```
   http://localhost:5000
   ```

### Manual Installation (Alternative)

1. **Create and activate a virtual environment**:
   ```
   # Windows
   python -m venv venv
   .\venv\Scripts\activate
   
   # Linux/macOS
   python3 -m venv venv
   source venv/bin/activate
   ```

2. **Install dependencies**:
   ```
   pip install -r requirements.txt
   ```

3. **Download the YOLO weights**:
   - Download from: [Google Drive](https://drive.google.com/file/d/1flTehMwmGg-PMEeQCsDS2VWRLGzV6Wdo/view?usp=sharing)
   - Create a `bin` directory in the project root
   - Place the downloaded `yolo.weights` file in the `bin` directory

4. **Run the application**:
   ```
   python web_app.py
   ```

## 🖥️ Usage

### Web Interface
Access the web interface at `http://localhost:5000` to:
- View real-time traffic simulation
- Monitor traffic density
- Adjust simulation parameters
- View historical data and analytics

### Simulation Modes
1. **Live Camera Mode**:
   - Uses your webcam for real vehicle detection
   - Press 'q' to quit the camera feed

2. **Simulation Mode**:
   - Runs a pre-recorded simulation
   - Adjust parameters in `simulation.py`

## 🛠️ Project Structure

```
.
├── bin/                  # YOLO weights and model files
├── cfg/                 # Configuration files
├── data/                # Sample data and resources
├── darkflow/            # YOLO implementation
├── static/              # Web assets (CSS, JS, images)
├── templates/           # HTML templates
├── web_app.py           # Main web application
├── simulation.py        # Traffic simulation
├── vehicle_detection.py # Vehicle detection module
└── requirements.txt     # Python dependencies
```

## 🔍 Troubleshooting

### Common Issues

1. **Dependency Installation Fails**
   - Ensure you have Python 3.8+ installed
   - Run Command Prompt as Administrator
   - Try: `pip install --upgrade pip setuptools wheel`

2. **Webcam Not Detected**
   - Check if another application is using the camera
   - Try disconnecting and reconnecting the camera
   - Use simulation mode as an alternative

3. **Performance Issues**
   - Close other resource-intensive applications
   - Reduce simulation quality in settings
   - Use a more powerful computer for better performance

4. **Port 5000 Already in Use**
   ```
   # Find and kill the process
   netstat -ano | findstr :5000
   taskkill /PID <PID> /F
   ```
   Or change the port in `web_app.py`

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📧 Contact

For any queries, please open an issue on the [GitHub repository](https://github.com/srnvslanka03/Smart-City-Traffic-System-).
