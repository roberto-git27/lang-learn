from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Both required, no defaults: they must come from .env (see .env.example).
    database_url: str
    anthropic_api_key: str

    # Two models (D-09): a cheap one for the negotiation chat, a stronger one
    # for the content that gets stored (exercise generation, term meanings).
    claude_chat_model: str = "claude-haiku-5-5"
    claude_generation_model: str = "claude-sonnet-5-5"

    # Effort replaces temperature on the 5.5 models (non-default sampling
    # parameters are rejected). Thinking always counts toward max_tokens.
    claude_chat_effort: str = "low"
    claude_generation_effort: str = "medium"

    # Studio import fallback (D-08): maps .md the parser cannot read to the
    # format, never authors content — a cheap model is enough.
    claude_parse_model: str = "claude-haiku-5-5"
    claude_parse_effort: str = "low"


settings = Settings()
