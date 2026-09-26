from pathlib import Path

path = Path('backend/app/game_service.py')
text = path.read_text(encoding='utf-8')

old = '''        is_detective = actor['role_label'] == '탐정' or actor['code'] == 'kang-haejin'
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
                world_prompt=actor['world_prompt'],
                character_id=str(actor['id']),
                character_name=actor['display_name'],
                system_prompt=actor['system_prompt'],
                objective=actor['objective'],
                personality=_as_dict(actor['personality']),
                current_location=current_code,
                current_location_name=loc['player_name'],
                adjacent_locations=adjacent_locations,
                same_room_characters=same_room,
                known_facts=known_facts,
                memories=memories,
                is_detective=is_detective,
            )
        )
'''

new = '''        is_detective = actor['role_label'] == '탐정' or actor['code'] == 'kang-haejin'
        if is_detective:
            # Detective keeps the full LLM-driven investigation path. Its wider
            # context is intentional because independent investigation is part
            # of the pressure placed on the player.
            await cur.execute(
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
            choice = await self.agent_service.choose_npc_action(
                NpcActionContext(
                    world_prompt=actor['world_prompt'],
                    character_id=str(actor['id']),
                    character_name=actor['display_name'],
                    system_prompt=actor['system_prompt'],
                    objective=actor['objective'],
                    personality=_as_dict(actor['personality']),
                    current_location=current_code,
                    current_location_name=loc['player_name'],
                    adjacent_locations=adjacent_locations,
                    same_room_characters=same_room,
                    known_facts=_as_list(actor['known_facts']),
                    memories=memories,
                    is_detective=True,
                )
            )
        else:
            # Suspects do not spend an LLM call deciding whether to move/talk/
            # investigate. The strategy is derived from already persisted game
            # state, while actual visible dialogue still uses the LLM.
            talk_targets_state = _as_dict(state.get('npc_talk_targets'))
            actor_talked_to = {
                str(value)
                for value in _as_list(talk_targets_state.get(str(actor['id'])))
                if str(value)
            }
            actor_social = _as_dict(
                _as_dict(state.get('social_state')).get(str(actor['id']))
            )
            cycle = max(1, min(2, int(state.get('action_cycle', 1))))
            round_no = int(session['current_turn'])
            variant = (round_no + sum(ord(ch) for ch in str(actor['code']))) % 3

            def is_regular_suspect(row):
                return not (
                    str(row.get('role_label') or '') == '탐정'
                    or str(row.get('code') or '') == 'kang-haejin'
                )

            def target_score(row):
                target_id = str(row.get('id') or '')
                entry = _as_dict(actor_social.get(target_id))
                relationship = int(entry.get('relationship', 0))
                suspicion = int(entry.get('suspicion', 25))
                if cycle == 1:
                    # First pass: prefer someone relatively cooperative who can
                    # reinforce or challenge the suspect's own alibi.
                    return relationship * 2 - suspicion
                # Second pass: if a talk is still useful, prefer the person the
                # suspect currently distrusts more.
                return suspicion * 2 - relationship

            same_candidates = [
                row for row in same_room
                if is_regular_suspect(row)
                and str(row['id']) not in actor_talked_to
            ]
            move_candidates = []
            for destination in adjacent_locations:
                for row in _as_list(destination.get('characters')):
                    if (
                        is_regular_suspect(row)
                        and str(row.get('id') or '') not in actor_talked_to
                    ):
                        move_candidates.append((destination, row))

            should_talk = bool(same_candidates or move_candidates) and (
                (cycle == 1 and variant != 0)
                or (cycle == 2 and not actor_talked_to and variant == 0)
            )

            if should_talk:
                options = [
                    (None, row, target_score(row) + 4)
                    for row in same_candidates
                ] + [
                    (destination, row, target_score(row))
                    for destination, row in move_candidates
                ]
                destination, target, _ = max(
                    options,
                    key=lambda item: (item[2], str(item[1].get('display_name') or '')),
                )
                target_id = str(target.get('id') or '')
                suspicion = int(
                    _as_dict(actor_social.get(target_id)).get('suspicion', 25)
                )
                if cycle == 1:
                    question = (
                        '제 동선을 확인해 두고 싶어요. '
                        '제가 이 근처에서 움직이던 걸 기억하는 게 있나요?'
                    )
                    intent = '내 알리바이를 확인해 줄 수 있는 사람의 기억을 확보한다.'
                elif suspicion >= 45:
                    question = (
                        '같은 알리바이 얘기는 반복하지 않을게요. '
                        '지금 공개된 정황 중 제 설명과 가장 충돌하는 부분이 뭐라고 봐요?'
                    )
                    intent = '내게 불리한 정황을 먼저 파악해 해명할 준비를 한다.'
                else:
                    question = (
                        '제 입장에서 아직 설명이 부족해 보이는 부분이 있다면 '
                        '어디인지 솔직히 말해줄래요?'
                    )
                    intent = '내 설명의 빈틈을 확인하고 자기방어에 활용한다.'
                choice = {
                    'move_to': (
                        str(destination.get('code')) if destination is not None else None
                    ),
                    'action_type': 'talk',
                    'target_character_id': target_id,
                    'question': question,
                    'intent': intent,
                }
            else:
                move_to = None
                if cycle == 2 and variant == 2 and adjacent_locations:
                    # Occasionally change rooms before searching so suspects do
                    # not become stationary evidence vacuums.
                    move_to = str(adjacent_locations[0].get('code') or '') or None
                choice = {
                    'move_to': move_to,
                    'action_type': 'investigate',
                    'target_character_id': None,
                    'question': None,
                    'intent': '내게 유리하거나 제출하기 좋은 증거를 확보해 자기방어에 대비한다.',
                }
'''

if new in text:
    print('already applied')
elif old not in text:
    raise SystemExit('target block not found')
else:
    path.write_text(text.replace(old, new, 1), encoding='utf-8')
    print('suspect strategy fast path applied')
