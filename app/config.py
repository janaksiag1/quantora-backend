from pathlib import Path
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(Path(__file__).parents[1] / '.env', Path(__file__).parents[1] / '.env.local'), extra='ignore')
    gemini_api_key: SecretStr = SecretStr('')
    gemini_api_key_secondary: SecretStr = SecretStr('')
    gemini_api_key_tertiary: SecretStr = SecretStr('')
    gemini_model: str = 'gemini-3.5-flash-lite'
    gemini_fallback_models: str = 'gemini-3.5-flash'
    agent_models_json: str = ''
    internal_api_token: SecretStr = SecretStr('')
    database_url: str = 'sqlite:///./quantora.db'
    frontend_origin: str = 'http://127.0.0.1:3000'
    vercel_oidc_token: SecretStr = SecretStr('')
    ai_gateway_api_key: SecretStr = SecretStr('')
    ai_gateway_models: str = 'nvidia/nemotron-3.5-lightning-free,reflection/beam-free,poolside/laguna-s-2.1-free'
    openrouter_api_key: SecretStr = SecretStr('')
    openrouter_models: str = 'openrouter/free'
    groq_api_key: SecretStr = SecretStr('')
    groq_model: str = 'qwen/qwen3.8-27b'
    groq_models: str = 'qwen/qwen3.8-27b,openai/gpt-oss-120b,openai/gpt-oss-20b'
    ollama_url: str = ''
    ollama_model: str = 'qwen3:8b'
    ollama_api_key: SecretStr = SecretStr('')
    nvidia_api_key: SecretStr = SecretStr('')
    nvidia_model: str = 'nvidia/llama-3.1-nemotron-70b-instruct'
    nvidia_production_entitled: bool = False
    cloudflare_api_token: SecretStr = SecretStr('')
    cloudflare_account_id: str = ''
    cloudflare_model: str = '@cf/meta/llama-3.1-8b-instruct'
    telegram_bot_token: SecretStr = SecretStr('')
    telegram_chat_id: str = ''
    render_service_url: str = 'https://quantora-backend-pn3o.onrender.com'

settings = Settings()
