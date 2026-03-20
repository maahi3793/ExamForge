import os
from dotenv import load_dotenv

# Load .env from project root
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(ROOT_DIR, '.env')
load_dotenv(ENV_PATH)


def get_config():
    """Load configuration from environment variables."""
    return {
        "gemini_key": os.environ.get("GEMINI_API_KEY", ""),
        "secret_key": os.environ.get("SECRET_KEY", "examforge-default-secret"),
    }
