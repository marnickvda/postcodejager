"""Run the Postcodejager web app: python -m postcodejager."""
import os

import uvicorn

from .app import create_app
from .config import apply_dotenv, load_settings
from .postcodes import load_pc4
from .storage import Store


def build_app():
    apply_dotenv()
    settings = load_settings()
    os.makedirs(settings.data_dir, exist_ok=True)
    store = Store(settings.db_path)

    cache: dict = {}

    def index_provider():
        if "idx" not in cache:
            cache["idx"] = load_pc4(settings.pc4_path)
        return cache["idx"]

    return create_app(settings, store, index_provider)


def main() -> None:
    uvicorn.run(build_app(), host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
