# Ollama LLMs Manager

A user-friendly GUI application for managing Ollama language models on Windows. Easily download, manage, and organize your local LLM installations with a modern dark-themed interface.
---

![Ollama LLMs Manager Screenshot](Screenshot.png)

---

## Features

- **Model Management**: View, download, and manage Ollama language models
- **Category Organization**: Models organized by capabilities (tools, thinking, vision, embedding, completion, audio, cloud)
- **Badge System**: Visual indicators for model capabilities and features
- **Dark Theme UI**: Modern dark Anthracite-themed interface for comfortable viewing
- **Windows Integration**: Native Windows integration with dark title bar support
- **Automatic Model Detection**: Intelligent detection of Ollama installation across common Windows locations

## Supported Model Categories

- **Tools**: Models with tool/function calling capabilities
- **Thinking**: Reasoning and complex reasoning models
- **Vision**: Models with image understanding capabilities
- **Embedding**: Text embedding and semantic search models
- **Completion**: Standard text completion models
- **Audio**: Models with audio processing capabilities
- **Cloud**: Cloud-integrated models

## Installation

### Option 1: Executable (Recommended for Users)

1. Download `Ollama_LLMs_Manager.exe` from [Releases](https://github.com/Gabrieliam42/Ollama_LLMs_Manager/releases)
2. Run the executable directly - no installation required
3. The application will automatically locate your Ollama installation

### Option 2: Python Script (For Developers)

1. Ensure you have Python 3.12+ installed
2. Install Ollama from [ollama.ai](https://ollama.ai)
3. Clone this repository:
   ```bash
   git clone https://github.com/Gabrieliam42/Ollama_LLMs_Manager.git
   cd Ollama_LLMs_Manager
   ```
4. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
5. Run the application:
   ```bash
   python Ollama_LLMs_Manager.py
   ```

## Requirements

- **Windows 10/11** (64-bit)
- **Ollama** - Download from [ollama.ai](https://ollama.ai)
- **Python 3.12+** (if running from source)

## Configuration

### Ollama Installation Detection

The application automatically searches for Ollama in these locations:

1. `OLLAMA_EXE` environment variable (if set)
2. Same directory as the application (`ollama.exe`)
3. `Ollama` subdirectory
4. Windows PATH
5. `%LOCALAPPDATA%\Programs\Ollama`
6. `%ProgramFiles%\Ollama`
7. `%ProgramFiles(x86)%\Ollama`

### Custom Ollama Location

Set the `OLLAMA_EXE` environment variable to your Ollama executable path:

```bash
set OLLAMA_EXE=C:\Path\To\Your\ollama.exe
```

## Usage

1. Launch the application
2. View available Ollama models in the main interface
3. Models are organized by category and capabilities
4. Use the badge system to identify model features at a glance
5. Download new models through the Ollama CLI or this manager

## System Information

This application is optimized for:
- **GPU**: NVIDIA RTX 3090 (24GB VRAM)
- **CPU**: Intel i9-14900KF
- **RAM**: 128GB
- **Runtime**: Windows 11

However, it works on any Windows 10/11 system with Ollama installed.

## Development

### Building from Source

Requirements:
- Python 3.12+
- PyInstaller
- Dependencies in `requirements.txt`

Build the executable:

```bash
pip install -r requirements.txt
pyinstaller Ollama_LLMs_Manager.spec
```

The executable will be generated in the `dist/` directory.

## Files

- `Ollama_LLMs_Manager.py` - Main application source code
- `Ollama_LLMs_Manager.exe` - Pre-built Windows executable
- `Ollama_LLMs_Manager.spec` - PyInstaller build specification
- `requirements.txt` - Python dependencies

## Troubleshooting

### "Could not locate ollama.exe"

Make sure Ollama is installed and either:
- Added to your Windows PATH
- Set in the `OLLAMA_EXE` environment variable
- Located in one of the default installation paths

### Dark Theme Not Applied

The dark theme is automatically applied on Windows 10/11. If it doesn't appear:
- Try restarting the application
- Ensure Windows 11 dark mode is enabled in Settings

## Author

**Gabriel Mihai Sandu**

- GitHub: [@Gabrieliam42](https://github.com/Gabrieliam42)

## License

This project is provided as-is for managing Ollama installations locally.

## Support

For issues, feature requests, or questions, please visit the [GitHub repository](https://github.com/Gabrieliam42/Ollama_LLMs_Manager) and open an issue.

---

**Note**: This application requires Ollama to be installed separately. Visit [ollama.ai](https://ollama.ai) to download Ollama.
