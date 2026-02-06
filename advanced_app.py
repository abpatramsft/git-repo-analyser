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
import subprocess
import shutil
import os
import tempfile
import stat
import time

app = Flask(__name__)
CORS(app)

# Base directory for cloned repos
TEMP_REPOS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp_repos")


def remove_readonly(func, path, excinfo):
    """Error handler for shutil.rmtree to handle read-only files on Windows."""
    os.chmod(path, stat.S_IWRITE)
    func(path)


def safe_rmtree(path: str, retries: int = 3):
    """
    Safely remove a directory tree, handling Windows file locking issues.
    
    Args:
        path: Path to the directory to remove
        retries: Number of retries if deletion fails
    """
    for attempt in range(retries):
        try:
            if os.path.exists(path):
                # On Windows, try to release git locks first
                git_dir = os.path.join(path, ".git")
                if os.path.exists(git_dir):
                    # Run git gc to release locks
                    subprocess.run(
                        ["git", "-C", path, "gc", "--prune=now"],
                        capture_output=True,
                        timeout=10
                    )
                shutil.rmtree(path, onerror=remove_readonly)
            return True
        except Exception as e:
            print(f"⚠️ Cleanup attempt {attempt + 1} failed: {e}")
            if attempt < retries - 1:
                time.sleep(1)  # Wait before retry
    print(f"⚠️ Could not fully clean up {path}, will be cleaned on next run")
    return False


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


def clone_repo(owner: str, repo: str) -> str:
    """
    Clone a GitHub repository to a temp folder.
    
    Args:
        owner: Repository owner
        repo: Repository name
    
    Returns:
        Path to the cloned repository
    """
    # Ensure temp_repos directory exists
    os.makedirs(TEMP_REPOS_DIR, exist_ok=True)
    
    # Create a unique folder for this repo (use short name to avoid path issues on Windows)
    repo_path = os.path.join(TEMP_REPOS_DIR, f"{repo[:20]}")
    
    # Remove if exists (fresh clone each time)
    if os.path.exists(repo_path):
        safe_rmtree(repo_path)
    
    # Clone the repository
    clone_url = f"https://github.com/{owner}/{repo}.git"
    print(f"\n{'='*60}")
    print(f"📥 CLONING REPOSITORY: {clone_url}")
    print(f"   Target folder: {repo_path}")
    print(f"{'='*60}\n")
    
    # Configure git to handle long paths on Windows and do shallow clone
    result = subprocess.run(
        [
            "git", "clone", 
            "--depth", "1",           # Shallow clone
            "--single-branch",        # Only clone default branch
            "--no-tags",              # Skip tags
            "-c", "core.longpaths=true",  # Handle long paths on Windows
            clone_url, 
            repo_path
        ],
        capture_output=True,
        text=True
    )
    
    # Check if at least the directory was created (partial success is ok)
    if not os.path.exists(repo_path):
        print(f"❌ Clone failed: {result.stderr}")
        raise Exception(f"Failed to clone repository: {result.stderr}")
    
    # If checkout failed but clone succeeded, try to restore what we can
    if "checkout failed" in result.stderr.lower():
        print(f"⚠️ Checkout had issues, attempting recovery...")
        subprocess.run(
            ["git", "-C", repo_path, "restore", "--source=HEAD", ":/"],
            capture_output=True,
            text=True
        )
    
    print(f"✅ Repository cloned successfully to: {repo_path}\n")
    return repo_path


def cleanup_repo(repo_path: str):
    """
    Remove the cloned repository folder.
    
    Args:
        repo_path: Path to the cloned repository
    """
    if repo_path and os.path.exists(repo_path):
        print(f"\n{'='*60}")
        print(f"🧹 CLEANING UP: {repo_path}")
        print(f"{'='*60}\n")
        safe_rmtree(repo_path)
        print(f"✅ Cleanup complete\n")


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

    # Clone the repository locally
    repo_path = None
    try:
        repo_path = clone_repo(owner, repo)
    except Exception as e:
        return {
            "response": f"Failed to clone repository: {str(e)}",
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
            tool_name = event.data.tool_name
            tool_call_id = getattr(event.data, 'tool_call_id', None)
            tool_args = getattr(event.data, 'arguments', None)
            print(f"\n{'='*60}")
            print(f"🔧 TOOL CALLED: {tool_name}")
            print(f"   Call ID: {tool_call_id}")
            if tool_args:
                print(f"   Arguments: {tool_args}")
            print(f"{'='*60}")
            events_log.append({
                "type": "tool_start",
                "tool_name": tool_name,
                "tool_call_id": tool_call_id
            })
        elif event.type.value == "tool.execution_complete":
            tool_call_id = event.data.tool_call_id
            result = getattr(event.data, 'result', None)
            print(f"\n{'='*60}")
            print(f"✅ TOOL RESULT (Call ID: {tool_call_id})")
            print(f"-"*60)
            # Truncate result if too long for readability
            result_str = str(result) if result else "No result"
            if len(result_str) > 1000:
                print(f"{result_str[:1000]}...\n[TRUNCATED - {len(result_str)} chars total]")
            else:
                print(result_str)
            print(f"{'='*60}\n")
            events_log.append({
                "type": "tool_complete",
                "tool_call_id": tool_call_id,
                "result": result
            })
        elif event.type.value == "session.idle":
            done.set()

    session.on(handle_event)

    # Build analysis prompts based on type - now using LOCAL cloned repo
    analysis_prompts = {
        "overview": f"""You are a helpful assistant that analyzes code repositories.

I have cloned the GitHub repository {owner}/{repo} to a local folder at: {repo_path}

Please analyze this LOCAL repository by reading files and exploring the directory structure.

Use file system tools (read_file, list_dir, grep_search, semantic_search) to explore the cloned repository.

Provide a comprehensive overview including:
1. **Repository Information**: Name, description, primary language, what the project does (read the README.md)
2. **Structure Overview**: List the directories and explain their purposes
3. **Key Files**: Read important files like README.md, package.json, requirements.txt, etc.
4. **Technology Stack**: Languages, frameworks, and tools used (based on config files)
5. **Project Type**: What kind of project this is (web app, library, CLI, etc.)

Start by listing the contents of {repo_path} and then read the key files.""",

        "structure": f"""You are a helpful assistant that analyzes code repositories.

I have cloned the GitHub repository {owner}/{repo} to a local folder at: {repo_path}

Please analyze the file structure of this LOCAL repository using file system tools.

Use list_dir to explore directories and read_file to examine key files.

1. List ALL directories and files, explaining their purposes
2. Identify the project type (web app, library, CLI tool, etc.)
3. Find and read configuration files, explain what they configure
4. Identify entry points and main source files

Start by listing the contents of {repo_path}""",

        "diagram": f"""You are a helpful assistant that analyzes code repositories and creates Mermaid diagrams.

I have cloned the GitHub repository {owner}/{repo} to a local folder at: {repo_path}

Please analyze this LOCAL repository using file system tools (read_file, list_dir, grep_search).

Your task:
1. Explore the directory structure using list_dir
2. Read key files to understand the architecture (README.md, main source files, config files)
3. Based on your analysis, create a Mermaid flow diagram

CRITICAL MERMAID SYNTAX RULES:
- Each node definition MUST be on a SINGLE LINE
- Node labels should be SHORT (1-5 words max)
- Do NOT put newlines inside square brackets []
- Use simple IDs like A, B, C or short names like React, DOM, etc.
- If you need line breaks in labels, use <br> tag, NOT actual newlines

Output a Mermaid diagram using EXACTLY this format:
```mermaid
graph TD
    A[Short Label] --> B[Another Label]
    B --> C[Third Label]
    C --> D[Fourth Label]
```

CORRECT example:
```mermaid
graph TD
    A[React Core] --> B[Reconciler]
    B --> C[React DOM]
    B --> D[React Native]
```

WRONG example (DO NOT DO THIS):
```mermaid
graph TD
    A[React Core
    Package] --> B[Reconciler]
```

Keep node labels concise. Use actual component/directory names from {owner}/{repo}.
Start by listing the contents of {repo_path}""",

        "dependencies": f"""You are a helpful assistant that analyzes code repositories.

I have cloned the GitHub repository {owner}/{repo} to a local folder at: {repo_path}

Please analyze the dependencies of this LOCAL repository using file system tools.

Use read_file to examine dependency files and grep_search to find imports.

1. Find and READ all dependency files (package.json, requirements.txt, Cargo.toml, go.mod, etc.)
2. List the main dependencies and their purposes
3. Identify any development dependencies
4. Summarize the technology stack

Start by listing the contents of {repo_path} to find dependency files.""",
    }

    prompt = analysis_prompts.get(analysis_type, analysis_prompts["overview"])

    try:
        await session.send({"prompt": prompt})
        await done.wait()
    finally:
        await session.destroy()
        await client.stop()
        # Clean up the cloned repository
        cleanup_repo(repo_path)

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
    print("Repos are cloned locally to temp_repos/ for analysis")
    print("\nStarting server on http://localhost:5002")
    print("=" * 60)
    app.run(debug=True, port=5002)
