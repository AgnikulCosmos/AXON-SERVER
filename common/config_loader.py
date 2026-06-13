import os
import logging
from pathlib import Path
from dotenv import load_dotenv

logger = logging.getLogger("orchestrator")

def load_environment():
    # Find AXON-SERVER root directory
    base_dir = Path(__file__).resolve().parent.parent
    
    # 1. Load the primary .env file to get APP_ENV
    env_path = base_dir / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path, override=True)
    
    # 2. Resolve APP_ENV (defaults to local)
    app_env = os.getenv("APP_ENV", "local").lower().strip()
    if app_env not in ("local", "test", "prod"):
        logger.warning(f"Invalid APP_ENV: '{app_env}'. Defaulting to 'local'.")
        app_env = "local"
        
    # 3. Load the environment-specific variables
    specific_env_name = f".env.{app_env}"
    specific_env_path = base_dir / specific_env_name
    
    if specific_env_path.exists():
        print(f"[Config Loader] Configuring environment '{app_env}' using {specific_env_name}", flush=True)
        load_dotenv(dotenv_path=specific_env_path, override=True)
    else:
        print(f"[Config Loader] Specific environment file {specific_env_name} not found at {specific_env_path}", flush=True)
    
    print(f"[Config Loader] Final resolved FRAPPE_URL: '{os.getenv('FRAPPE_URL')}'", flush=True)

# Load environments immediately upon import
load_environment()
