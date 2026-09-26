from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    if old not in text:
        raise SystemExit(f'{label}: target block not found')
    return text.replace(old, new, 1)


game_path = Path('backend/app/game_service.py')
game = game_path.read_text(encoding='utf-8')
old_loop = """        for suspect in suspects:
            suspect_id = str(suspect['id'])
            if suspect_id == player_id:
                continue
            source_key = f\"private-interrogation:{current_round}:{suspect_id}\"
            await cur.execute(
                \"\"\"
                select 1
                from game_private.agent_memories
                where session_id = %s
                  and character_id = %s
                  and source_key = %s
                \"\"\",
                (session['id'], detective['id'], source_key),
            )
            if await cur.fetchone():
                continue

            compact_question = (
                f\"{question} \"
                \"한 번의 답변 안에 다음 세 가지를 함께 말하세요: \"
                \"① 본인의 시간대별 동선과 근거, \"
                \"② 공개 증거와 충돌하거나 해명할 점, \"
                \"③ 현재 의심하는 사람과 이유 및 본인에게 불리한 사실이 있다면 그 설명.\"
            )
            target_ctx = await self._agent_context_for_character(
                cur, session, suspect_id, compact_question
            )
            target_ctx.player_name = detective['display_name']
            reply = await self.agent_service.generate_reply(target_ctx)
            transcript = (
                f\"{suspect['display_name']} 비공개 취조\\n\"
                f\"탐정: {compact_question}\\n\"
                f\"{suspect['display_name']}: {reply}\"
            )
            await self._remember(
                cur,
                session['id'],
                detective['id'],
                turn['id'],
                'private_interrogation',
                transcript,
                source_key,
                salience=100,
            )
            await self._remember(
                cur,
                session['id'],
                suspect_id,
                turn['id'],
                'private_interrogation',
                transcript,
                f\"private-interrogation-self:{current_round}:{suspect_id}\",
                salience=80,
            )

"""
new_loop = """        pending_interrogations: list[tuple[dict[str, Any], str, str, str, AgentContext]] = []
        for suspect in suspects:
            suspect_id = str(suspect['id'])
            if suspect_id == player_id:
                continue
            source_key = f\"private-interrogation:{current_round}:{suspect_id}\"
            await cur.execute(
                \"\"\"
                select 1
                from game_private.agent_memories
                where session_id = %s
                  and character_id = %s
                  and source_key = %s
                \"\"\",
                (session['id'], detective['id'], source_key),
            )
            if await cur.fetchone():
                continue

            compact_question = (
                f\"{question} \"
                \"한 번의 답변 안에 다음 세 가지를 함께 말하세요: \"
                \"① 본인의 시간대별 동선과 근거, \"
                \"② 공개 증거와 충돌하거나 해명할 점, \"
                \"③ 현재 의심하는 사람과 이유 및 본인에게 불리한 사실이 있다면 그 설명.\"
            )
            target_ctx = await self._agent_context_for_character(
                cur, session, suspect_id, compact_question
            )
            target_ctx.player_name = detective['display_name']
            pending_interrogations.append(
                (suspect, suspect_id, source_key, compact_question, target_ctx)
            )

        if pending_interrogations:
            replies = await asyncio.gather(
                *(
                    self.agent_service.generate_reply(item[4])
                    for item in pending_interrogations
                ),
                return_exceptions=True,
            )
            for item, reply in zip(pending_interrogations, replies):
                suspect, suspect_id, source_key, compact_question, _ = item
                if isinstance(reply, BaseException):
                    reply = '지금 기억나는 범위에서 말씀드리겠습니다.'
                transcript = (
                    f\"{suspect['display_name']} 비공개 취조\\n\"
                    f\"탐정: {compact_question}\\n\"
                    f\"{suspect['display_name']}: {reply}\"
                )
                await self._remember(
                    cur,
                    session['id'],
                    detective['id'],
                    turn['id'],
                    'private_interrogation',
                    transcript,
                    source_key,
                    salience=100,
                )
                await self._remember(
                    cur,
                    session['id'],
                    suspect_id,
                    turn['id'],
                    'private_interrogation',
                    transcript,
                    f\"private-interrogation-self:{current_round}:{suspect_id}\",
                    salience=80,
                )

"""
game = replace_once(game, old_loop, new_loop, 'parallel detective interrogations')
game_path.write_text(game, encoding='utf-8')

enhanced_path = Path('backend/app/enhanced_game_service.py')
enhanced = enhanced_path.read_text(encoding='utf-8')
old_state = """        async with pool.connection() as conn:
            async with conn.transaction():
                async with conn.cursor(row_factory=dict_row) as cur:
                    before = deepcopy(_as_dict(state.get('social_state')))
                    await self._ensure_social_state(
                        cur,
                        session['story_version_id'],
                        state,
                    )
                    if before != _as_dict(state.get('social_state')):
                        changed = True
                    if changed:
                        await cur.execute(
                            \"\"\"
                            update public.game_sessions
                            set public_state = %s, updated_at = now()
                            where id = %s and user_id = %s
                            \"\"\",
                            (Jsonb(state), session_id, user_id),
                        )
                        await cur.execute(
                            \"\"\"
                            update game_private.session_runtime
                            set state = %s, state_version = state_version + 1, updated_at = now()
                            where session_id = %s
                            \"\"\",
                            (Jsonb(state), session_id),
                        )

"""
new_state = """        social = _as_dict(state.get('social_state'))
        turn_rows = [_as_dict(item) for item in _as_list(state.get('turn_order'))]
        suspect_ids = [
            str(item.get('id') or '')
            for item in turn_rows
            if str(item.get('id') or '') and str(item.get('role') or '') != '탐정'
        ]
        needs_social_repair = (
            not suspect_ids
            or any(
                actor_id not in social
                or any(
                    target_id != actor_id
                    and target_id not in _as_dict(social.get(actor_id))
                    for target_id in suspect_ids
                )
                for actor_id in suspect_ids
            )
        )

        if needs_social_repair or changed:
            async with pool.connection() as conn:
                async with conn.transaction():
                    async with conn.cursor(row_factory=dict_row) as cur:
                        if needs_social_repair:
                            before = deepcopy(_as_dict(state.get('social_state')))
                            await self._ensure_social_state(
                                cur,
                                session['story_version_id'],
                                state,
                            )
                            if before != _as_dict(state.get('social_state')):
                                changed = True
                        if changed:
                            await cur.execute(
                                \"\"\"
                                update public.game_sessions
                                set public_state = %s, updated_at = now()
                                where id = %s and user_id = %s
                                \"\"\",
                                (Jsonb(state), session_id, user_id),
                            )
                            await cur.execute(
                                \"\"\"
                                update game_private.session_runtime
                                set state = %s, state_version = state_version + 1, updated_at = now()
                                where session_id = %s
                                \"\"\",
                                (Jsonb(state), session_id),
                            )

"""
enhanced = replace_once(enhanced, old_state, new_state, 'lazy social state repair')
enhanced_path.write_text(enhanced, encoding='utf-8')
print('round latency hardening patch applied')
