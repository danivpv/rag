from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    s3_bucket_name: str
    bedrock_region: str
    bedrock_embed_model_id: str
    bedrock_generate_model_id: str


settings = Settings()  # ty:ignore[missing-argument]
