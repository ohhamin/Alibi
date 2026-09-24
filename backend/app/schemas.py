from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class StartSessionRequest(BaseModel):
    story_version_id: UUID
    player_character_id: UUID


class ActionRequest(BaseModel):
    action_type: Literal['act', 'ask', 'search', 'inspect', 'move', 'present']
    target_character_id: UUID | None = None
    input_text: str | None = Field(default=None, max_length=1500)
    payload: dict[str, Any] = Field(default_factory=dict)
    client_action_id: UUID | None = None


class AccuseRequest(BaseModel):
    culprit_character_id: UUID
    reasoning: str | None = Field(default=None, max_length=3000)
