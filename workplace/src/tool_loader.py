# tool_loader.py
import importlib.util
import difflib
import sys
from pathlib import Path
from typing import Optional
import httpx
from langchain_core.tools import tool

# TOOLS_DIR = Path(__file__).parent / "../tools"
# TOOLS_DIR.mkdir(exist_ok=True)

SCRIPT_DIR = Path(__file__).parent
TOOLS_DIR = (SCRIPT_DIR / "../tools").resolve()
TOOLS_DIR.mkdir(exist_ok=True)



def find_existing_tool(platform_name: str, action: str = "profile_finder") -> Optional[Path]:
    """Finds an existing tool file matching platform and action keywords.
    
    Handles non-deterministic filenames like:
    - facebook_profile_finder.py
    - fb_profile_finder.py
    - facebook_finder.py
    """
    if not TOOLS_DIR.exists():
        return None

    platform = platform_name.lower()
    python_files = list(TOOLS_DIR.glob("*.py"))
    
    if not python_files:
        return None

    # Tier 1: Exact expected filename match
    exact_name = f"{platform}_{action}.py"
    for file in python_files:
        if file.name.lower() == exact_name:
            return file

    # Tier 2: Keyword overlap (Must contain platform AND key action term)
    for file in python_files:
        filename = file.name.lower()
        # Handle platform aliases (e.g., 'fb' or 'facebook')
        matches_platform = platform in filename or (platform == "facebook" and "fb" in filename)
        matches_action = "finder" in filename or "profile" in filename
        
        if matches_platform and matches_action:
            return file

    # Tier 3: Fuzzy sequence matching fallback (cutoff threshold at 0.6)
    file_map = {f.name.lower(): f for f in python_files}
    matches = difflib.get_close_matches(exact_name, file_map.keys(), n=1, cutoff=0.6)
    
    if matches:
        return file_map[matches[0]]

    return None

# results = find_existing_tool(platform_name="linkedin")
# print(results)
# print(f"Tools DIR: {TOOLS_DIR}")


def load_module_from_file(file_path: Path): 
    """Dynamically load/reload a Python module from disk."""
    module_name = file_path.stem
    
    # Invalidate Python cache to force reading latest changes from disk
    importlib.invalidate_caches()
    
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load spec for module at {file_path}")
    
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def create_langchain_tool_adapter(platform_name: str, file_path: Path):
    """Import the raw python file and wrap its main function into a standard LangChain Tool."""
    module = load_module_from_file(file_path)
    
    # Locate the target function (e.g., facebook_profile_finder or linkedin_profile_finder)
    target_func_name = f"{platform_name.lower()}_profile_finder"
    raw_func = getattr(module, target_func_name, None)
    
    if not raw_func:
        raise AttributeError(f"Module {file_path.name} does not export function '{target_func_name}'")

    # Define dynamic LangChain tool wrapper
    @tool(f"fetch_{platform_name.lower()}_profile")
    def dynamic_profile_finder(biodata: dict, **kwargs) -> dict:
        """Fetches and scrapes profile data from the web using biodata JSON context."""
        target_biodata = biodata if isinstance(biodata, dict) and biodata else kwargs
        
        if not target_biodata.get('name'):
            first = target_biodata.get('first_name', "")
            last = target_biodata.get('last_name', '')
            
            if first or last:
                target_biodata['name'] = f"{first} {last}".strip()
        
        # Instantiate HTTP client required by generated tools
        with httpx.Client(timeout=60.0) as client:
            result = raw_func(biodata_json=target_biodata, settings=None, http_client=client)
            return result

    return dynamic_profile_finder