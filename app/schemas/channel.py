from typing import Literal

from pydantic import BaseModel, Field


class CreateChannelRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class ChannelResponse(BaseModel):
    id: str
    name: str
    source: str
    exists: bool
    sync_status: Literal["sync_queued", "sync_in_progress"] | None = None
