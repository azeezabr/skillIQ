from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    theirstack_api_key: str
    theirstack_url: str = "https://api.theirstack.com/v1/jobs/search"
    # Spend controls: owned by the job, never taken from the payload (TheirStack bills 1 credit per record).
    page_size: int = 25
    max_pages: int = 20
