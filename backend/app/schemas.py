from pydantic import BaseModel, Field


class ThreadCreate(BaseModel):
    title: str = "New chat"


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
