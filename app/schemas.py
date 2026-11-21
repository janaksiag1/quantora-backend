from typing import Annotated, Literal
from pydantic import BaseModel, Field

Ticker = Annotated[str, Field(pattern=r'^[A-Za-z0-9^.&=\-]{1,40}$')]

class ChatRequest(BaseModel):    language: Literal['Auto','English','Hinglish'] = 'English'
    voice: bool = False
    module: Literal['ipo', 'stocks', 'funds', 'crypto'] = 'ipo'    assetName: str = Field(default='', max_length=150)
    prompt: str = Field(min_length=3, max_length=4000)
    symbol: Ticker | None = None
    risk: Literal['Conservative', 'Balanced', 'Growth'] = 'Balanced'
    history: list[dict[str, str]] = Field(default_factory=list, max_length=6)
    portfolio: list[dict] = Field(default_factory=list, max_length=30)

class DebateRequest(BaseModel):    documentUrl: str = Field(default='',max_length=1000)    language: Literal['English','Hinglish'] = 'English'    module: Literal['ipo', 'stocks', 'funds', 'crypto'] = 'ipo'    assetName: str = Field(default='', max_length=200)
    symbol: Ticker | None = None
    subject: str = Field(default='', max_length=2000)
    risk: Literal['Conservative', 'Balanced', 'Growth'] = 'Balanced'class ResearchStageRequest(DebateRequest):
    previousContext: str = Field(default="", max_length=1800)    phase: int = Field(ge=0,le=5)    checkpoint: dict = Field(default_factory=dict)
