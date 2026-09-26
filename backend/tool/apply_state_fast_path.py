from pathlib import Path

path = Path('backend/app/game_service.py')
text = path.read_text(encoding='utf-8')

replacements = []
replacements.append((
"""                    state['npc_talk_targets'] = {}

                    await cur.execute(
""",
"""                    state['npc_talk_targets'] = {}
                    state['initial_evidence_initialized'] = False

                    await cur.execute(
""",
'initialize evidence flag',
))

replacements.append((
"""                    await self._sync_player_inventory_state(
                        cur,
                        {
                            'id': session_id,
                            'player_character_id': str(request.player_character_id),
                        },
                        state,
                    )

                    await cur.execute(
""",
"""                    await self._sync_player_inventory_state(
                        cur,
                        {
                            'id': session_id,
                            'player_character_id': str(request.player_character_id),
                        },
                        state,
                    )
                    state['initial_evidence_initialized'] = True

                    await cur.execute(
""",
'mark evidence initialized',
))

replacements.append((
"""                            \"라운드 종료 시 소지 증거가 있다면 반드시 1개를 탐정에게 제출해야 하며, 제출된 증거는 모두에게 공개됩니다. \"
""",
"""                            \"2·5라운드 종료 후 탐정의 비공개 취조 직전에만 소지 증거 1개를 제출하며, 제출된 증거는 모두에게 공개됩니다. \"
""",
'fix start guidance',
))

old_get = """                await self._ensure_initial_evidence_holdings(
                    cur,
                    str(session['id']),
                    str(session['story_version_id']),
                )

                await cur.execute(
"""
new_get = """                state = deepcopy(_as_dict(session['public_state']))
                if not bool(state.get('initial_evidence_initialized')):
                    # Legacy/self-heal path only. New sessions finish this work
                    # in start_session, so ordinary state reads skip the heavy
                    # initial-evidence CTE and memory INSERTs entirely.
                    await self._ensure_initial_evidence_holdings(
                        cur,
                        str(session['id']),
                        str(session['story_version_id']),
                    )
                    if session['player_character_id']:
                        await self._sync_player_inventory_state(cur, session, state)
                    state['initial_evidence_initialized'] = True
                    session['public_state'] = state
                    await cur.execute(
                        \"\"\"
                        update public.game_sessions
                        set public_state = %s, last_saved_at = now(), updated_at = now()
                        where id = %s
                        \"\"\",
                        (Jsonb(state), session['id']),
                    )
                    await cur.execute(
                        \"\"\"
                        update game_private.session_runtime
                        set state = %s, state_version = state_version + 1, updated_at = now()
                        where session_id = %s
                        \"\"\",
                        (Jsonb(state), session['id']),
                    )

                await cur.execute(
"""
replacements.append((old_get, new_get, 'skip repeated initial evidence repair'))

replacements.append((
"""                state = _as_dict(session['public_state'])
                current_location = str(state.get('current_location') or '')
""",
"""                current_location = str(state.get('current_location') or '')
""",
'reuse state object',
))

for old, new, label in replacements:
    if new in text:
        continue
    if old not in text:
        raise SystemExit(f'{label}: target block not found')
    text = text.replace(old, new, 1)

path.write_text(text, encoding='utf-8')
print('state fast path applied')
