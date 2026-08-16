import os
import shutil
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()  # Load environment variables from .env file

# Patch orchestral-ai's image-renderer.js to fix subdirectory image display.
# The upstream file uses _extractFilename() which strips all path components,
# causing images saved in subdirectories to return 404. Our patched version
# preserves the workspace-relative path so any depth is served correctly.
def _apply_image_renderer_patch():
    try:
        import orchestral
        target = Path(orchestral.__file__).parent / "ui" / "web" / "static" / "js" / "image-renderer.js"
        patch = Path(__file__).parent / "static" / "js" / "image-renderer.js"
        if patch.exists() and target.exists():
            shutil.copy2(patch, target)
    except Exception as e:
        print(f"[ASTER] Warning: could not apply image-renderer patch: {e}")

_apply_image_renderer_patch()

from orchestral import Agent
from orchestral.tools import (
    RunCommandTool,
    WriteFileTool,
    ReadFileTool,
    EditFileTool,
    FileSearchTool,
    TodoWrite,
    TodoRead,
    DisplayImageTool
)
from orchestral.tools.hooks import DangerousCommandHook
from orchestral.prompts import RICH_UI_SYSTEM_PROMPT
from orchestral.llm import Claude
# from orchestral.llm import GPT

from aster_toolkit import (
    RunTaurexModelTool,
    SetTaurexPaths,
    SimulateTaurexRetrieval,
    PlotCornerPosteriors,
    GetExoplanetParameters,
    DownloadDataset, 
    FindExoplanetsByCondition
)

base_directory = 'workspace'
os.makedirs(base_directory, exist_ok=True)

tools = [
    # File and command tools
    RunCommandTool(base_directory=base_directory, persistent=True),
    WriteFileTool(base_directory=base_directory),
    ReadFileTool(base_directory=base_directory, show_line_numbers=True),
    EditFileTool(base_directory=base_directory),
    FileSearchTool(base_directory=base_directory),
    TodoRead(),
    TodoWrite(initial_todos='- [ ] Sample todo item'),
    DisplayImageTool,

    # TauREx modeling tools
    SetTaurexPaths,
    RunTaurexModelTool(base_directory=base_directory),
    SimulateTaurexRetrieval(base_directory=base_directory),
    PlotCornerPosteriors(base_directory=base_directory),

    # Data acquisition tools
    GetExoplanetParameters(),
    DownloadDataset(base_directory=base_directory),
    FindExoplanetsByCondition()
]

hooks = [DangerousCommandHook()]

# Load ASTER system prompt
with open('aster_system_prompt.md', 'r') as f:
    aster_prompt = f.read()

system_prompt = f'{RICH_UI_SYSTEM_PROMPT}\n\n{aster_prompt}'

agent = Agent(
    llm=Claude(model="claude-haiku-4-5"),
    # llm=GPT(model="gpt-4.1-mini"),
    tools=tools,
    tool_hooks=hooks,
    system_prompt=system_prompt
)

from orchestral.ui.app import server as app_server

app_server.run_server(agent, host='localhost', port=8000)

