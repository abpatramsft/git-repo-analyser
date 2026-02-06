"""
Git Repo Visualiser - Web UI for analyzing GitHub repositories

This Flask app provides a web interface for analyzing GitHub repositories
using the GitHub Copilot SDK. It generates markdown-based flow diagrams 
and repository overviews.

Run: python app.py
Then open: http://localhost:5002
"""

from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from copilot import CopilotClient
import asyncio
import re

app = Flask(__name__)
CORS(app)


def parse_github_url(url: str) -> tuple:
    """
    Parse a GitHub URL to extract owner and repo name.
    
    Args:
        url: GitHub repository URL (e.g., https://github.com/owner/repo)
    
    Returns:
        Tuple of (owner, repo) or (None, None) if invalid
    """
    patterns = [
        r'github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$',
        r'^([^/]+)/([^/]+)$',
    ]
    
    url = url.strip()
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1), match.group(2)
    
    return None, None


async def analyze_github_repo(repo_url: str, analysis_type: str = "overview") -> dict:
    """
    Analyze a GitHub repository using the Copilot SDK.
    
    Args:
        repo_url: The GitHub repository URL
        analysis_type: Type of analysis (overview, structure, dependencies, diagram)
    """
    owner, repo = parse_github_url(repo_url)
    if not owner or not repo:
        return {
            "response": "Invalid GitHub URL. Please use format: https://github.com/owner/repo",
            "events": []
        }

    client = CopilotClient()
    await client.start()

    # Create session without MCP servers - use Copilot's built-in capabilities
    session = await client.create_session({"model": "gpt-4.1"})

    done = asyncio.Event()
    response_content = []
    events_log = []

    def handle_event(event):
        if event.type.value == "assistant.message":
            response_content.append(event.data.content)
        elif event.type.value == "assistant.message_delta":
            delta = event.data.delta_content or ""
            if delta:
                events_log.append({
                    "type": "message_delta",
                    "content": delta
                })
        elif event.type.value == "tool.execution_start":
            events_log.append({
                "type": "tool_start",
                "tool_name": event.data.tool_name,
                "tool_call_id": getattr(event.data, 'tool_call_id', None)
            })
        elif event.type.value == "tool.execution_complete":
            events_log.append({
                "type": "tool_complete",
                "tool_call_id": event.data.tool_call_id,
                "result": getattr(event.data, 'result', None)
            })
        elif event.type.value == "session.idle":
            done.set()

    session.on(handle_event)

    # Build analysis prompts based on type
    analysis_prompts = {
        "overview": f"""You are a helpful assistant that analyzes GitHub repositories.

Please analyze the GitHub repository: https://github.com/{owner}/{repo}

Provide a comprehensive overview including:
1. **Repository Information**: Name, description, primary language, what the project does
2. **Structure Overview**: Main directories and their purposes based on common conventions
3. **Key Files**: Important files like README, package.json, requirements.txt, etc.
4. **Technology Stack**: Languages, frameworks, and tools likely used
5. **Project Type**: What kind of project this is (web app, library, CLI, etc.)

Fetch and analyze the repository information to provide accurate details.""",

        "structure": f"""You are a helpful assistant that analyzes GitHub repositories.

Please analyze the file structure of: https://github.com/{owner}/{repo}

1. List the main directories and explain their purposes
2. Identify the project type (web app, library, CLI tool, etc.)
3. Find configuration files and explain what they configure
4. Identify entry points and main source files

Browse the repository to understand its structure.""",

        "diagram": f"""You are a helpful assistant that analyzes GitHub repositories and creates Mermaid diagrams.

IMPORTANT: Do NOT analyze any local files or the current working directory.
ONLY analyze the remote GitHub repository at this URL: https://github.com/{owner}/{repo}

Your task:
1. Fetch information about the GitHub repository {owner}/{repo} from the web
2. Based on the repository's README, file structure, and code organization, create a Mermaid flow diagram

The diagram should show:
- The overall architecture/structure of the project
- How different components/modules relate to each other
- Data flow or dependency relationships between parts

Output a Mermaid diagram using this format:
```mermaid
graph TD
    A[Component A] --> B[Component B]
    B --> C[Component C]
```

Use actual component names, directories, or module names from the {owner}/{repo} repository.
Do NOT reference any local files - only use information from the GitHub repository.""",

        "dependencies": f"""You are a helpful assistant that analyzes GitHub repositories.

Please analyze the dependencies of: https://github.com/{owner}/{repo}

1. Find all dependency files (package.json, requirements.txt, Cargo.toml, go.mod, etc.)
2. List the main dependencies and their purposes
3. Identify any development dependencies
4. Summarize the technology stack

Fetch the dependency information from the repository.""",
    }

    prompt = analysis_prompts.get(analysis_type, analysis_prompts["overview"])

    await session.send({"prompt": prompt})
    await done.wait()
    await session.destroy()
    await client.stop()

    return {
        "response": "\n".join(response_content) if response_content else "No response received.",
        "events": events_log,
        "owner": owner,
        "repo": repo
    }


@app.route('/')
def index():
    """Serve the main HTML page."""
    return render_template('index.html')


@app.route('/api/analyze', methods=['POST'])
def analyze():
    """Handle the repository analysis request."""
    data = request.json
    repo_url = data.get('repo_url', '')
    analysis_type = data.get('type', 'overview')

    if not repo_url:
        return jsonify({'error': 'Repository URL is required'}), 400

    try:
        result = asyncio.run(analyze_github_repo(repo_url, analysis_type))
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({'status': 'ok', 'service': 'git-repo-visualiser'})


if __name__ == '__main__':
    print("=" * 60)
    print("🔍 Git Repo Visualiser")
    print("=" * 60)
    print("\nAnalyze GitHub repositories and generate flow diagrams")
    print("Using GitHub MCP Server for repository access")
    print("\nStarting server on http://localhost:5002")
    print("=" * 60)
    app.run(debug=True, port=5002)
