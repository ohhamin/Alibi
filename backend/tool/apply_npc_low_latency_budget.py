from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    if old not in text:
        raise SystemExit(f'{label}: target block not found')
    return text.replace(old, new, 1)


agent_path = Path('backend/app/agent_service.py')
agent = agent_path.read_text(encoding='utf-8')
agent = replace_once(
    agent,
    "    async def generate_reply(self, ctx: AgentContext) -> str:\n",
    "    async def generate_reply(\n        self, ctx: AgentContext, *, max_output_tokens: int = 180\n    ) -> str:\n",
    'generate_reply token budget',
)
agent = replace_once(
    agent,
    "                max_output_tokens=min(self.settings.openai_max_output_tokens, 180),\n",
    "                max_output_tokens=min(self.settings.openai_max_output_tokens, max_output_tokens),\n",
    'generate_reply output budget',
)
agent = replace_once(
    agent,
    "        fallback: dict[str, Any],\n    ) -> dict[str, Any]:\n",
    "        fallback: dict[str, Any],\n        max_output_tokens: int = 280,\n    ) -> dict[str, Any]:\n",
    'json response token budget arg',
)
agent = replace_once(
    agent,
    "                max_output_tokens=min(self.settings.openai_max_output_tokens, 280),\n",
    "                max_output_tokens=min(self.settings.openai_max_output_tokens, max_output_tokens),\n",
    'json response output budget',
)
agent = replace_once(
    agent,
    "                self._json_response(instructions, serialized, fallback),\n                timeout=5.0,\n",
    "                self._json_response(\n                    instructions, serialized, fallback, max_output_tokens=140\n                ),\n                timeout=4.0,\n",
    'suspect action low latency call',
)
agent = replace_once(
    agent,
    "            logger.warning('NPC action selection exceeded 5.0s; using fallback')\n",
    "            logger.warning('NPC action selection exceeded 4.0s; using fallback')\n",
    'suspect action timeout log',
)
agent_path.write_text(agent, encoding='utf-8')


game_path = Path('backend/app/game_service.py')
game = game_path.read_text(encoding='utf-8')
game = replace_once(
    game,
    "                    self.agent_service.generate_reply(target_agent_ctx),\n                    timeout=3.5,\n",
    "                    self.agent_service.generate_reply(\n                        target_agent_ctx, max_output_tokens=90\n                    ),\n                    timeout=2.8,\n",
    'visible npc talk low latency reply',
)
game_path.write_text(game, encoding='utf-8')
print('NPC low latency token budget patch applied')
