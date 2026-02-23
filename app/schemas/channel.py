from pydantic import BaseModel, Field


class CreateChannelRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class ChannelResponse(BaseModel):
    id: str
    name: str
    source: str
