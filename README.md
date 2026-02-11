# Twinsafe Central Hub

Twinsafe Central Hub is a modular application for monitoring and generating reports for Twinsafe-based systems. It features a FastAPI backend with OPC UA integration and a modern web frontend.

## Directly After Cloning

1.  **Create a virtual environment:**
    ```bash
    python -m venv .venv
    ```

2.  **Activate the virtual environment:**
    **Linux:**
    ```bash
    source .venv/bin/activate
    ```

    **Windows:**
    ```powershell
    .\.venv\Scripts\Activate.ps1
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

## Running the Application

To start the server:
```bash
python -m visualisation.backend.main
```
The application will be available at `http://localhost:9000`.

## Project Structure

- `visualisation/backend/`: FastAPI application, modular routers, and OPC integration.
- `visualisation/frontend/`: Modernized UI with Tailwind CSS and centralized styling.
- `chart_generation/`: Core logic for generating PDF charts from CSV data.
- `OTS_File_Sorter/`: Utility for monitoring and sorting data files.
- `utils/`: Miscellaneous utility scripts.

## Features

- **Rig Overview**: Live monitoring of multiple rigs.
- **Historical Trend**: Interactive visualization of logged data with cursor measurements.
- **PDF Generation**: Tool for creating professional PDF reports from test data.
- **OPC UA Integration**: Framework for real-time data acquisition from industrial controllers.
