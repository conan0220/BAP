"""Desktop release response schema."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ReleaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    platform: str
    version: str
    download_url: str
    sha256: str
    source_tree_sha: str
    published_at: datetime
