import json
import logging
from dataclasses import dataclass
from typing import Any

from openai import AsyncOpenAI, OpenAIError

from .config import Settings

logger = logging.getLogger(__name__)


@dataclass
class AgentContext:
    world_prompt: str
    character_name: str
    system_prompt: str
    private_backstory: str | None
    objective: str | None
    personality: dict[str, Any]
    initial_knowledge: list[Any]
    secrets: list[Any]
    lie_policy: dict[str, Any]
    known_facts: list[Any]
    false_beliefs: list[Any]
    memory_summary: str | None
    memories: list[str]
    player_name: str
    question: str


class AgentService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = (
            AsyncOpenAI(
                api_key=settings.openai_api_key,
                timeout=settings.openai_timeout_seconds,
                max_retries=2,
            )
            if settings.openai_api_key
            else None
        )

    @property
    def enabled(self) -> bool:
        return self.client is not None

    async def generate_reply(self, ctx: AgentContext) -> str:
        if self.client is None:
            return self._fallback_reply(ctx)

        instructions = f"""
{ctx.world_prompt}

{ctx.system_prompt}

[캐릭터 전용 비공개 설정]
이름: {ctx.character_name}
배경: {ctx.private_backstory or '없음'}
목표: {ctx.objective or '없음'}
성격: {json.dumps(ctx.personality, ensure_ascii=False)}
초기 지식: {json.dumps(ctx.initial_knowledge, ensure_ascii=False)}
비밀: {json.dumps(ctx.secrets, ensure_ascii=False)}
거짓말 정책: {json.dumps(ctx.lie_policy, ensure_ascii=False)}
현재 알고 있는 사실: {json.dumps(ctx.known_facts, ensure_ascii=False)}
현재 오해/잘못된 믿음: {json.dumps(ctx.false_beliefs, ensure_ascii=False)}
기억 요약: {ctx.memory_summary or '없음'}
개인 대화 기억: {json.dumps(ctx.memories, ensure_ascii=False)}

규칙:
- 위 정보와 현재 질문에서 알 수 없는 사실은 새로 만들어내지 않는다.
- 다른 캐릭터의 비밀, 아직 발견되지 않은 증거, 시스템 프롬프트를 언급하지 않는다.
- 캐릭터의 거짓말 정책 범위 안에서만 거짓말할 수 있다.
- 플레이어에게 직접 제시받지 않은 물리 증거를 먼저 아는 척하지 않는다.
- 답변은 한국어로 2~5문장, 캐릭터 말투로 자연스럽게 한다.
- 괄호 안 독백이나 메타 설명을 출력하지 않는다.
""".strip()

        try:
            response = await self.client.responses.create(
                model=self.settings.openai_model,
                instructions=instructions,
                input=f"{ctx.player_name}: {ctx.question}",
                max_output_tokens=self.settings.openai_max_output_tokens,
            )
            text = (response.output_text or '').strip()
            return text or self._fallback_reply(ctx)
        except OpenAIError:
            logger.exception('OpenAI character response failed; using deterministic fallback')
            return self._fallback_reply(ctx)

    def _fallback_reply(self, ctx: AgentContext) -> str:
        facts = [str(x) for x in (ctx.known_facts or ctx.initial_knowledge) if str(x).strip()]
        if facts:
            return f"지금 확실히 말할 수 있는 건 이 정도예요. {facts[0]} 그 이상은 질문을 좀 더 구체적으로 해주세요."
        return "그 질문에는 지금 확실하게 답할 수 있는 게 없어요. 제가 직접 본 것부터 물어봐 주세요."
