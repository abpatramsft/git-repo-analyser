# Git Repo Visualiser

A web application that analyzes GitHub repositories and generates visual overviews including markdown-based flow diagrams.

## Features

- **Repository Overview**: Get comprehensive information about a GitHub repository including description, languages, stars, forks, and recent activity
- **Structure Analysis**: Explore the file structure and understand the project organization
- **Flow Diagrams**: Generate Mermaid-based flow diagrams showing the architecture and component relationships
- **Dependency Analysis**: Analyze project dependencies from package.json, requirements.txt, etc.
- **Application variations**: There are two variations of the repo analyser:
 - Simple repo analyzer - This uses the web_fetch tool to read the github files from the web and analyse and provide the response
 - Advacned repo analyzer - This clones the public repo a "temp_repos" folder, and then leverages the file read and search tools to perform a deeper analysis of the file and its content. Wroks well for more complicated repos and deeper understanding with file level read and search functionalities

## Prerequisites

- Python 3.8+
- GitHub Copilot SDK

## Installation

1. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

## Usage

1. Start the application:

To start the Simple repo analyser: 
```bash
python app.py
```

To start the Advacned repo analyser: 
```bash
python advanced_app.py
```

2. Open your browser and navigate to: http://localhost:5001 (if you are running app.py) and http://localhost:5002 (if you are running advanced_app.py)

3. Enter a GitHub repository URL (e.g., `https://github.com/microsoft/vscode`)

4. Select the analysis type:
   - **Overview**: General repository information
   - **Structure**: File and directory structure
   - **Flow Diagram**: Mermaid diagram of architecture
   - **Dependencies**: Project dependencies analysis

5. Click "Analyze" to generate the visualization

## How It Works

This application uses the GitHub Copilot SDK to analyze GitHub repositories. The Copilot SDK provides capabilities to:

- Fetch and analyze repository information
- Understand code structure and dependencies
- Generate architecture diagrams using Mermaid syntax

No additional MCP servers are required - the app uses Copilot's built-in capabilities.

## API Endpoints

- `GET /` - Main web interface
- `POST /api/analyze` - Analyze a repository
  - Body: `{ "repo_url": "https://github.com/owner/repo", "type": "overview|structure|diagram|dependencies" }`
- `GET /api/health` - Health check endpoint
