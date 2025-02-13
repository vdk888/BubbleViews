from typing import Dict, Any
import json
from pathlib import Path
from pydantic import BaseModel

class RedditConfig(BaseModel):
    client_id: str
    client_secret: str
    user_agent: str
    username: str
    password: str

class TelegramConfig(BaseModel):
    token: str
    chat_id: str

class TwitterConfig(BaseModel):
    bearer_token: str
    api_key: str
    api_secret: str
    access_token: str
    access_token_secret: str

class OpenRouterConfig(BaseModel):
    api_key: str

class Config(BaseModel):
    reddit: RedditConfig
    telegram: TelegramConfig
    twitter: TwitterConfig
    openrouter: OpenRouterConfig

def load_config(config_path: str = "config.json") -> Config:
    """Load configuration from JSON file."""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    
    with open(path) as f:
        config_data = json.load(f)
    
    return Config(**config_data)
