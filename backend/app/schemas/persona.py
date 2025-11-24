from pydantic import BaseModel


class PersonaSummary(BaseModel):
    id: str
    reddit_username: str
    display_name: str | None = None

    class Config:
        orm_mode = True
