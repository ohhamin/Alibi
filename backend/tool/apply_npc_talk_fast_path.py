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
    "                timeout=6.5,\n",
    "                timeout=5.0,\n",
    'suspect action timeout',
)
agent = replace_once(
    agent,
    "            logger.warning('NPC action selection exceeded 6.5s; using fallback')\n",
    "            logger.warning('NPC action selection exceeded 5.0s; using fallback')\n",
    'suspect action timeout log',
)
agent_path.write_text(agent, encoding='utf-8')


game_path = Path('backend/app/game_service.py')
game = game_path.read_text(encoding='utf-8')
old_memory = '''        await cur.execute(
            """
            select content
            from game_private.agent_memories
            where session_id = %s and character_id = %s
            order by created_at desc
            limit 10
            """,
            (session['id'], target_id),
        )
        target_memories = [row['content'] for row in await cur.fetchall()]
        target_memories.reverse()

        actual_question = (
            question
            or f"{intent} 아까 제 동선이나 제가 여기 있었던 걸 기억하는 게 있나요?"
        )
        reply = await self.agent_service.generate_reply(
            AgentContext(
                world_prompt=target_ctx['world_prompt'],
                character_name=target_ctx['display_name'],
                system_prompt=target_ctx['system_prompt'],
                private_backstory=target_ctx['private_backstory'],
                objective=target_ctx['objective'],
                personality=_as_dict(target_ctx['personality']),
                initial_knowledge=_as_list(target_ctx['initial_knowledge']),
                secrets=_as_list(target_ctx['secrets']),
                lie_policy=_as_dict(target_ctx['lie_policy']),
                known_facts=_as_list(target_ctx['known_facts']),
                false_beliefs=_as_list(target_ctx['false_beliefs']),
                memory_summary=target_ctx['memory_summary'],
                memories=target_memories,
                player_name=actor['display_name'],
                question=actual_question,
            )
        )
'''
new_memory = '''        await cur.execute(
            """
            select left(content, 280) as content
            from game_private.agent_memories
            where session_id = %s and character_id = %s
            order by created_at desc
            limit 2
            """,
            (session['id'], target_id),
        )
        target_memories = [row['content'] for row in await cur.fetchall()]
        target_memories.reverse()

        target_facts = _as_list(target_ctx['known_facts'])
        if len(target_facts) > 5:
            target_facts = [*target_facts[:2], *target_facts[-3:]]
        target_false_beliefs = _as_list(target_ctx['false_beliefs'])[-3:]
        memory_summary = (
            str(target_ctx['memory_summary'])[:400]
            if target_ctx['memory_summary'] else None
        )
        actual_question = (
            question
            or f"{intent} 아까 제 동선이나 제가 여기 있었던 걸 기억하는 게 있나요?"
        )
        target_agent_ctx = AgentContext(
            world_prompt=target_ctx['world_prompt'],
            character_name=target_ctx['display_name'],
            system_prompt=target_ctx['system_prompt'],
            private_backstory=target_ctx['private_backstory'],
            objective=target_ctx['objective'],
            personality=_as_dict(target_ctx['personality']),
            initial_knowledge=_as_list(target_ctx['initial_knowledge'])[:4],
            secrets=_as_list(target_ctx['secrets']),
            lie_policy=_as_dict(target_ctx['lie_policy']),
            known_facts=target_facts,
            false_beliefs=target_false_beliefs,
            memory_summary=memory_summary,
            memories=target_memories,
            player_name=actor['display_name'],
            question=actual_question,
        )

        witnessed_by_player = (
            str(state.get('current_location') or '') == str(location_code)
        )
        if witnessed_by_player:
            try:
                reply = await asyncio.wait_for(
                    self.agent_service.generate_reply(target_agent_ctx),
                    timeout=3.5,
                )
            except TimeoutError:
                reply = self.agent_service._fallback_reply(target_agent_ctx)
        else:
            # Off-screen NPC dialogue still updates memories and social state,
            # but does not spend a second LLM call on text the player cannot see.
            reply = self.agent_service._fallback_reply(target_agent_ctx)
'''
game = replace_once(game, old_memory, new_memory, 'NPC-to-NPC fast reply path')
game_path.write_text(game, encoding='utf-8')
print('NPC talk fast path patch applied')
