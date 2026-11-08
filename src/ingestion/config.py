import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # not installed on Databricks; env vars / secrets are used there
    pass


@dataclass(frozen=True)
class Settings:
    theirstack_api_key: str
    theirstack_url: str
    databricks_host: str
    databricks_token: str
    catalog: str
    schema: str
    volume: str
    cors_origins: list
    # Spend controls: server-owned, never taken from the request.
    page_size: int = 25
    max_pages: int = 20

    @property
    def volume_root(self) -> str:
        return f"/Volumes/{self.catalog}/{self.schema}/{self.volume}"


def get_settings() -> Settings:
    return Settings(
        theirstack_api_key=os.environ.get("THEIRSTACK_API_KEY", ""),
        theirstack_url=os.environ.get(
            "THEIRSTACK_URL", "https://api.theirstack.com/v1/jobs/search"
        ),
        databricks_host=os.environ.get("DATABRICKS_HOST", ""),
        databricks_token=os.environ.get("DATABRICKS_TOKEN", ""),
        catalog=os.environ.get("DATABRICKS_CATALOG", "dev_catalog"),
        schema=os.environ.get("DATABRICKS_SCHEMA", "landing"),
        volume=os.environ.get("DATABRICKS_VOLUME", "skillediq"),
        cors_origins=[
            o.strip()
            for o in os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",")
            if o.strip()
        ],
    )
