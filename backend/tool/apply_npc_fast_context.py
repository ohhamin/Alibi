from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    if old not in text:
        raise SystemExit(f'{label}: target block not found')
    return text.replace(old, new, 1)


agent_path = Path('backend/app/agent_service.py')
agent = agent_path.read_text(encoding='utf-8')
if not agent.startswith('import asyncio\n'):
    agent = 'import asyncio\n' + agent

old_guidance = '''            role_guidance = """
당신은 탐정이 아니라 살인 사건의 용의자다. 가장 중요한 목표는 '범인을 밝혀내는 것'보다 현재 상황에서 자신이 범인으로 몰리지 않도록 자신의 입장을 지키는 것이다.

용의자 행동 원칙:
- 자신의 알리바이를 강화할 수 있는 사람, 시간대, 증거를 우선 신경 쓴다.
- 다른 사람에게 말을 걸 때는 수사관처럼 '당신은 어디 있었죠?', '무엇을 봤죠?'를 반복하지 않는다.
- 대신 자신의 동선을 확인받는 질문을 선호한다. 예: '그때 제가 홀에 있던 거 보셨죠?', '제가 행사 정리하던 시간 기억나요?', '아까 제가 창고 쪽에 있었던 거 봤나요?'
- 공개되거나 자신이 알고 있는 증거가 자신에게 유리하면 그 의미를 확인하거나 다른 사람에게 상기시키려 한다.
- 자신에게 불리한 증거가 있다면 그 증거가 왜 그렇게 보이는지 해명할 기회를 만들거나, 당장 제출하기 좋은 다른 증거를 찾으려 할 수 있다.
- 다른 사람을 의심하거나 질문할 수는 있지만 목적은 대체로 자신의 알리바이 구축, 자기방어, 불리한 정황의 해명이다.
- 사건 전체를 재구성하거나 모든 사람의 동선을 조사하는 '작은 탐정'처럼 행동하지 않는다.
- investigate는 범인을 찾기 위한 광범위한 수색보다 자신에게 도움이 될 증거 또는 라운드 종료 때 제출할 수 있는 증거를 확보하려는 목적이 자연스럽다.
""".strip()
'''
new_guidance = '''            role_guidance = """
당신은 탐정이 아니라 살인 사건의 용의자다. 우선 목표는 자신이 범인으로 몰리지 않게 입장을 지키는 것이다.
- 알리바이를 강화할 사람·시간대·증거를 우선한다.
- 수사관처럼 모두의 동선을 캐묻지 말고, 자신의 동선 확인·해명·자기방어에 집중한다.
- 이미 확인한 질문은 반복하지 않고, 최근 답변이나 증거를 바탕으로 후속 행동을 고른다.
- 유리한 증거는 활용하고 불리한 증거는 해명하거나 다른 제출 후보를 확보하려 한다.
- investigate는 광범위한 범인 수색보다 자신에게 도움이 될 증거 확보가 우선이다.
""".strip()
'''
agent = replace_once(agent, old_guidance, new_guidance, 'compact suspect role guidance')

old_payload = '''        payload = {
            'current_location': {
                'code': ctx.current_location,
                'name': ctx.current_location_name,
            },
            'adjacent_locations': ctx.adjacent_locations,
            'same_room_characters': ctx.same_room_characters,
            'known_facts': ctx.known_facts,
            'recent_memories': ctx.memories,
            'personality': ctx.personality,
            'is_detective': ctx.is_detective,
        }
        return await self._json_response(instructions, json.dumps(payload, ensure_ascii=False, default=str), fallback)
'''
new_payload = '''        payload = {
            'current_location': {
                'code': ctx.current_location,
                'name': ctx.current_location_name,
            },
            'adjacent_locations': ctx.adjacent_locations,
            'same_room_characters': ctx.same_room_characters,
            'known_facts': ctx.known_facts,
            'recent_memories': ctx.memories,
            'context_mode': 'full' if ctx.is_detective else 'compact',
        }
        serialized = json.dumps(payload, ensure_ascii=False, default=str)
        if ctx.is_detective:
            return await self._json_response(instructions, serialized, fallback)
        try:
            return await asyncio.wait_for(
                self._json_response(instructions, serialized, fallback),
                timeout=6.5,
            )
        except TimeoutError:
            logger.warning('NPC action selection exceeded 6.5s; using fallback')
            return fallback
'''
agent = replace_once(agent, old_payload, new_payload, 'fast suspect action selection')
agent_path.write_text(agent, encoding='utf-8')


game_path = Path('backend/app/game_service.py')
game = game_path.read_text(encoding='utf-8')
old_memories = '''        await cur.execute(
            """
            select left(content, 650) as content
            from game_private.agent_memories
            where session_id = %s and character_id = %s
            order by created_at desc
            limit 5
            """,
            (session['id'], actor['id']),
        )
        memories = [row['content'] for row in await cur.fetchall()]
        memories.reverse()

        is_detective = actor['role_label'] == '탐정' or actor['code'] == 'kang-haejin'
        choice = await self.agent_service.choose_npc_action(
            NpcActionContext(
'''
new_memories = '''        is_detective = actor['role_label'] == '탐정' or actor['code'] == 'kang-haejin'
        memory_char_limit = 650 if is_detective else 280
        memory_limit = 5 if is_detective else 2
        await cur.execute(
            """
            select left(content, %s) as content
            from game_private.agent_memories
            where session_id = %s and character_id = %s
            order by created_at desc
            limit %s
            """,
            (memory_char_limit, session['id'], actor['id'], memory_limit),
        )
        memories = [row['content'] for row in await cur.fetchall()]
        memories.reverse()

        known_facts = _as_list(actor['known_facts'])
        if not is_detective and len(known_facts) > 5:
            known_facts = [*known_facts[:2], *known_facts[-3:]]

        choice = await self.agent_service.choose_npc_action(
            NpcActionContext(
'''
game = replace_once(game, old_memories, new_memories, 'compact NPC memory query')
game = game.replace("                known_facts=_as_list(actor['known_facts']),\n                memories=memories,\n                is_detective=is_detective,", "                known_facts=known_facts,\n                memories=memories,\n                is_detective=is_detective,", 1)
game_path.write_text(game, encoding='utf-8')

print('NPC fast context patch applied')
