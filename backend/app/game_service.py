from copy import deepcopy
from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .agent_service import (
    AgentContext,
    AgentService,
    ConversationReplyContext,
    DetectiveBonusContext,
    DetectiveVerdictContext,
    GameMasterContext,
    NpcActionContext,
)
from .db import pool
from .schemas import AccuseRequest, ActionRequest, StartSessionRequest


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


class GameService:
    def __init__(self, agent_service: AgentService):
        self.agent_service = agent_service

    async def list_stories(self) -> list[dict[str, Any]]:
        query = """
        select
          s.id as story_id, s.slug, s.title, s.synopsis, s.cover_image_url,
          s.difficulty, s.estimated_minutes,
          sv.id as story_version_id, sv.version_no, sv.label, sv.opening_text,
          sv.player_briefing, sv.max_turns,
          coalesce(
            jsonb_agg(
              jsonb_build_object(
                'id', sc.id,
                'code', sc.code,
                'display_name', sc.display_name,
                'role_label', sc.role_label,
                'public_bio', sc.public_bio,
                'avatar_url', sc.avatar_url,
                'is_player_selectable', sc.is_player_selectable,
                'sort_order', sc.sort_order
              ) order by sc.sort_order
            ) filter (where sc.id is not null), '[]'::jsonb
          ) as characters
        from public.stories s
        join public.story_versions sv on sv.story_id = s.id
        left join public.story_characters sc on sc.story_version_id = sv.id
        where s.status = 'published' and sv.status = 'published'
        group by s.id, sv.id
        order by s.published_at desc nulls last, s.created_at desc, sv.version_no desc;
        """
        async with pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(query)
                return list(await cur.fetchall())

    async def list_sessions(self, user_id: str) -> list[dict[str, Any]]:
        query = """
        select gs.id, gs.story_version_id, gs.player_character_id, gs.player_mode, gs.status,
               gs.current_turn, gs.current_phase, gs.public_state, gs.started_at, gs.last_saved_at,
               s.title as story_title, sc.display_name as player_name, sc.role_label as player_role
        from public.game_sessions gs
        join public.story_versions sv on sv.id = gs.story_version_id
        join public.stories s on s.id = sv.story_id
        left join public.story_characters sc on sc.id = gs.player_character_id
        where gs.user_id = %s
        order by gs.last_saved_at desc;
        """
        async with pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(query, (user_id,))
                return list(await cur.fetchall())

    async def delete_session(self, user_id: str, session_id: str) -> dict[str, bool]:
        async with pool.connection() as conn:
            async with conn.transaction():
                async with conn.cursor(row_factory=dict_row) as cur:
                    await cur.execute(
                        "delete from public.game_sessions where id = %s and user_id = %s returning id",
                        (session_id, user_id),
                    )
                    deleted = await cur.fetchone()
                    if deleted is None:
                        raise HTTPException(status_code=404, detail='삭제할 저장 게임을 찾을 수 없습니다.')
        return {'deleted': True}

    async def start_session(self, user_id: str, request: StartSessionRequest) -> dict[str, Any]:
        async with pool.connection() as conn:
            async with conn.transaction():
                async with conn.cursor(row_factory=dict_row) as cur:
                    await cur.execute(
                        """
                        select sv.id as story_version_id, sv.opening_text, sv.max_turns,
                               s.title, rc.world_prompt, rc.narrator_prompt, rc.director_prompt,
                               rc.initial_state, rc.turn_rules, rc.starting_location_id
                        from public.story_versions sv
                        join public.stories s on s.id = sv.story_id
                        join game_private.story_runtime_configs rc on rc.story_version_id = sv.id
                        where sv.id = %s and sv.status = 'published' and s.status = 'published'
                        """,
                        (str(request.story_version_id),),
                    )
                    story = await cur.fetchone()
                    if story is None:
                        raise HTTPException(status_code=404, detail='플레이 가능한 스토리를 찾을 수 없습니다.')

                    await cur.execute(
                        """
                        select sc.id, sc.display_name, sc.role_label, sc.public_bio, sc.story_version_id,
                               cc.private_backstory, cc.objective, cc.secrets
                        from public.story_characters sc
                        join game_private.character_configs cc on cc.character_id = sc.id
                        where sc.id = %s and sc.story_version_id = %s and sc.is_player_selectable = true
                        """,
                        (str(request.player_character_id), str(request.story_version_id)),
                    )
                    player = await cur.fetchone()
                    if player is None:
                        raise HTTPException(status_code=400, detail='선택할 수 없는 캐릭터입니다.')

                    await cur.execute(
                        "select code, player_name from game_private.story_locations where id = %s",
                        (story['starting_location_id'],),
                    )
                    starting_location = await cur.fetchone()
                    if starting_location is None:
                        raise HTTPException(status_code=500, detail='시작 장소 설정이 없습니다.')

                    state = deepcopy(_as_dict(story['initial_state']))
                    rules = _as_dict(story['turn_rules'])
                    state['round'] = 1
                    state['actions_per_round'] = 2
                    state['action_rule_version'] = 2
                    state['actions_remaining'] = 0
                    state['movement_remaining'] = 0
                    state['active_conversation'] = None
                    state['player_turn_key'] = None
                    state['max_rounds'] = int(rules.get('max_rounds', story['max_turns'] or 6))
                    state['current_location'] = starting_location['code']
                    state['current_location_name'] = starting_location['player_name']
                    state['inventory_clues'] = []
                    state['world_changes'] = []
                    state['pending_npc_question'] = None
                    state['detective_bonus_done_round'] = 0

                    await cur.execute(
                        """
                        insert into public.game_sessions
                          (user_id, story_version_id, player_mode, player_character_id,
                           status, current_turn, current_phase, public_state)
                        values (%s, %s, 'suspect', %s, 'active', 1, 'investigation', %s)
                        returning id
                        """,
                        (user_id, str(request.story_version_id), str(request.player_character_id), Jsonb(state)),
                    )
                    session_id = (await cur.fetchone())['id']

                    await cur.execute(
                        """
                        insert into public.game_turns (session_id, turn_no, status)
                        values (%s, 1, 'open') returning id
                        """,
                        (session_id,),
                    )
                    turn_id = (await cur.fetchone())['id']
                    turn = {'id': turn_id, 'turn_no': 1, 'status': 'open'}

                    await cur.execute(
                        """
                        insert into game_private.session_runtime
                          (session_id, story_version_id, current_scene, director_summary, state, state_version)
                        values (%s, %s, %s, null, %s, 1)
                        """,
                        (session_id, str(request.story_version_id), starting_location['code'], Jsonb(state)),
                    )

                    await cur.execute(
                        """
                        insert into public.session_locations
                          (session_id, location_code, name, description, unlocked_turn)
                        select %s, code, player_name, player_description, 1
                        from game_private.story_locations
                        where story_version_id = %s and is_initially_available = true
                        on conflict do nothing
                        """,
                        (session_id, str(request.story_version_id)),
                    )

                    await cur.execute(
                        """
                        insert into game_private.session_character_states
                          (session_id, story_version_id, character_id, location_code, current_goal,
                           emotional_state, suspicion_map, known_facts, false_beliefs, memory_summary, state,
                           last_turn_processed)
                        select
                          %s,
                          sc.story_version_id,
                          sc.id,
                          case
                            when sc.id = %s then %s
                            else coalesce(nullif(cc.relationship_seed->>'initial_location', ''), %s)
                          end,
                          cc.objective,
                          '{}'::jsonb,
                          '{}'::jsonb,
                          cc.initial_knowledge,
                          '[]'::jsonb,
                          null,
                          '{}'::jsonb,
                          0
                        from public.story_characters sc
                        join game_private.character_configs cc on cc.character_id = sc.id
                        where sc.story_version_id = %s
                        on conflict (session_id, character_id) do nothing
                        """,
                        (
                            session_id,
                            str(request.player_character_id),
                            starting_location['code'],
                            starting_location['code'],
                            str(request.story_version_id),
                        ),
                    )

                    await cur.execute(
                        """
                        select sc.id, sc.display_name, sc.role_label, sc.sort_order
                        from public.story_characters sc
                        where sc.story_version_id = %s
                        order by sc.sort_order
                        """,
                        (str(request.story_version_id),),
                    )
                    ordered = list(await cur.fetchall())
                    state['actor_order'] = [str(row['id']) for row in ordered]
                    state['turn_order'] = [
                        {
                            'id': str(row['id']),
                            'name': row['display_name'],
                            'role': row['role_label'],
                            'sort_order': row['sort_order'],
                        }
                        for row in ordered
                    ]
                    state['actor_index'] = 0

                    await cur.execute(
                        """
                        select sc.id, st.location_code
                        from game_private.session_character_states st
                        join public.story_characters sc on sc.id = st.character_id
                        where st.session_id = %s
                        """,
                        (session_id,),
                    )
                    state['known_character_locations'] = {
                        str(row['id']): {
                            'location_code': row['location_code'],
                            'turn_no': 1,
                            'source': 'cctv',
                        }
                        for row in await cur.fetchall()
                    }

                    opening = story['opening_text'] or f"{story['title']} 사건이 시작되었습니다."
                    await self._insert_message(cur, session_id, turn_id, 'narrator', None, 'narration', opening)
                    await self._insert_message(
                        cur,
                        session_id,
                        turn_id,
                        'system',
                        None,
                        'system',
                        (
                            f"당신은 {player['display_name']}({player['role_label']})입니다. "
                            "모든 인물은 위에서부터 한 번씩 행동합니다. 당신 차례에는 주행동 2회를 할 수 있고, 각 주행동 전마다 인접 장소 1칸을 무료로 이동할 수 있습니다."
                        ),
                    )

                    session = {
                        'id': session_id,
                        'story_version_id': str(request.story_version_id),
                        'player_character_id': str(request.player_character_id),
                        'current_turn': 1,
                        'current_phase': 'investigation',
                        'status': 'active',
                    }
                    await self._advance_turn_sequence(cur, session, turn, state)

                    await cur.execute(
                        """
                        update public.game_sessions
                        set public_state = %s, current_turn = %s, current_phase = %s,
                            last_saved_at = now(), updated_at = now()
                        where id = %s
                        """,
                        (Jsonb(state), session['current_turn'], session['current_phase'], session_id),
                    )
                    await cur.execute(
                        """
                        update game_private.session_runtime
                        set current_scene = %s, state = %s, state_version = state_version + 1, updated_at = now()
                        where session_id = %s
                        """,
                        (state.get('current_location'), Jsonb(state), session_id),
                    )

        return await self.get_session_state(user_id, str(session_id))

    async def get_session_state(self, user_id: str, session_id: str) -> dict[str, Any]:
        async with pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    select gs.*, s.title as story_title, sv.opening_text, sv.player_briefing, sv.max_turns
                    from public.game_sessions gs
                    join public.story_versions sv on sv.id = gs.story_version_id
                    join public.stories s on s.id = sv.story_id
                    where gs.id = %s and gs.user_id = %s
                    """,
                    (session_id, user_id),
                )
                session = await cur.fetchone()
                if session is None:
                    raise HTTPException(status_code=404, detail='게임 세션을 찾을 수 없습니다.')

                await cur.execute(
                    """
                    select sc.id, sc.code, sc.display_name, sc.role_label, sc.public_bio, sc.avatar_url,
                           sc.is_player_selectable, sc.sort_order, cc.personality
                    from public.story_characters sc
                    join game_private.character_configs cc on cc.character_id = sc.id
                    where sc.story_version_id = %s
                    order by sc.sort_order
                    """,
                    (session['story_version_id'],),
                )
                characters = list(await cur.fetchall())

                player_role = None
                if session['player_character_id']:
                    await cur.execute(
                        """
                        select sc.id, sc.display_name, sc.role_label, sc.public_bio,
                               cc.private_backstory, cc.objective, cc.secrets, cc.personality,
                               cc.relationship_seed
                        from public.story_characters sc
                        join game_private.character_configs cc on cc.character_id = sc.id
                        where sc.id = %s
                        """,
                        (session['player_character_id'],),
                    )
                    player_role = await cur.fetchone()

                await cur.execute(
                    """
                    select sm.id, sm.sequence_no, sm.turn_id, sm.speaker_type,
                           sm.speaker_character_id, sm.message_kind, sm.content, sm.created_at,
                           sc.display_name as speaker_name
                    from public.session_messages sm
                    left join public.story_characters sc on sc.id = sm.speaker_character_id
                    where sm.session_id = %s
                    order by sm.sequence_no
                    """,
                    (session_id,),
                )
                messages = list(await cur.fetchall())

                await cur.execute(
                    """
                    select id, clue_code, title, content, category, discovered_turn, discovered_at
                    from public.session_clues where session_id = %s
                    order by discovered_at, id
                    """,
                    (session_id,),
                )
                clues = list(await cur.fetchall())

                await cur.execute(
                    """
                    select sl.id, sl.location_code, sl.name, sl.description,
                           sl.unlocked_turn, sl.unlocked_at,
                           coalesce(l.metadata->'adjacent', '[]'::jsonb) as adjacent
                    from public.session_locations sl
                    join game_private.story_locations l
                      on l.story_version_id = %s and l.code = sl.location_code
                    where sl.session_id = %s
                    order by sl.unlocked_at, sl.id
                    """,
                    (session['story_version_id'], session_id),
                )
                locations = list(await cur.fetchall())

                await cur.execute(
                    """
                    select id, turn_no, status, summary, opened_at, closed_at
                    from public.game_turns
                    where session_id = %s
                    order by turn_no desc limit 1
                    """,
                    (session_id,),
                )
                turn = await cur.fetchone()

                ending = None
                solution = None
                if session['status'] == 'completed' and session['ending_code']:
                    await cur.execute(
                        """
                        select code, title, ending_text, is_success
                        from game_private.story_endings
                        where story_version_id = %s and code = %s
                        """,
                        (session['story_version_id'], session['ending_code']),
                    )
                    ending = await cur.fetchone()
                    await cur.execute(
                        """
                        select sc.display_name as culprit_name, ss.canonical_explanation
                        from game_private.story_solutions ss
                        left join public.story_characters sc on sc.id = ss.culprit_character_id
                        where ss.story_version_id = %s
                        """,
                        (session['story_version_id'],),
                    )
                    solution = await cur.fetchone()

                state = _as_dict(session['public_state'])
                current_location = str(state.get('current_location') or '')

                await cur.execute(
                    """
                    select sc.id, sc.code, sc.display_name, sc.role_label, sc.avatar_url,
                           st.location_code
                    from game_private.session_character_states st
                    join public.story_characters sc on sc.id = st.character_id
                    where st.session_id = %s
                    order by sc.sort_order
                    """,
                    (session_id,),
                )
                character_locations = list(await cur.fetchall())
                visible_characters = [
                    row
                    for row in character_locations
                    if row['location_code'] == current_location
                    and str(row['id']) != str(session['player_character_id'])
                ]

                current_location_detail = next(
                    (item for item in locations if item['location_code'] == current_location),
                    None,
                )

                await cur.execute(
                    """
                    select pa.id, pa.action_type, pa.input_text, pa.payload, pa.created_at,
                           gt.turn_no, tc.display_name as target_name
                    from public.player_actions pa
                    join public.game_turns gt on gt.id = pa.turn_id
                    left join public.story_characters tc on tc.id = pa.target_character_id
                    where pa.session_id = %s
                    order by pa.created_at, pa.id
                    """,
                    (session_id,),
                )
                player_action_history = list(await cur.fetchall())

                inventory_codes = [
                    str(code) for code in _as_list(state.get('inventory_clues')) if str(code)
                ]
                inventory_items: list[dict[str, Any]] = []
                if inventory_codes:
                    await cur.execute(
                        """
                        select clue_code, title, content, category
                        from public.session_clues
                        where session_id = %s and clue_code = any(%s)
                        order by discovered_at
                        """,
                        (session_id, inventory_codes),
                    )
                    inventory_items = list(await cur.fetchall())

                known_locations = _as_dict(state.get('known_character_locations'))
                character_dossiers: list[dict[str, Any]] = []
                for character in characters:
                    character_id = str(character['id'])
                    known_location = _as_dict(known_locations.get(character_id))
                    known_location_code = str(
                        known_location.get('location_code') or ''
                    )
                    known_location_name = next(
                        (
                            str(location['name'])
                            for location in locations
                            if str(location['location_code']) == known_location_code
                        ),
                        '',
                    )

                    known_statements: list[str] = []
                    for message in messages:
                        if (
                            str(message.get('speaker_character_id') or '') != character_id
                            or str(message.get('speaker_type') or '') != 'character'
                        ):
                            continue
                        statement = str(message.get('content') or '').strip()
                        if statement and statement not in known_statements:
                            known_statements.append(statement)

                    related_clues: list[dict[str, Any]] = []
                    character_name = str(character['display_name'])
                    for clue in clues:
                        clue_title = str(clue.get('title') or '')
                        clue_content = str(clue.get('content') or '')
                        if character_name not in clue_title and character_name not in clue_content:
                            continue
                        related_clues.append(
                            {
                                'clue_code': clue.get('clue_code'),
                                'title': clue_title,
                                'content': clue_content,
                            }
                        )

                    character_dossiers.append(
                        {
                            'id': character_id,
                            'code': character['code'],
                            'display_name': character['display_name'],
                            'role_label': character['role_label'],
                            'public_bio': character['public_bio'],
                            'avatar_url': character['avatar_url'],
                            'is_player': character_id == str(session['player_character_id']),
                            'known_location_code': known_location_code or None,
                            'known_location_name': known_location_name or None,
                            'known_statements': known_statements[-8:],
                            'related_clues': related_clues,
                        }
                    )

                return {
                    'session': session,
                    'current_turn': turn,
                    'characters': characters,
                    'player_role': player_role,
                    'messages': messages,
                    'clues': clues,
                    'locations': locations,
                    'current_location_detail': current_location_detail,
                    'visible_characters': visible_characters,
                    'character_locations': character_locations,
                    'character_dossiers': character_dossiers,
                    'known_character_locations': _as_dict(state.get('known_character_locations')),
                    'pending_npc_question': state.get('pending_npc_question'),
                    'active_conversation': state.get('active_conversation'),
                    'inventory_items': inventory_items,
                    'player_action_history': player_action_history,
                    'current_actor_id': state.get('current_actor_id'),
                    'current_actor_name': state.get('current_actor_name'),
                    'detective_verdict': state.get('detective_verdict'),
                    'ending': ending,
                    'solution': solution,
                }

    async def advance_game(self, user_id: str, session_id: str) -> dict[str, Any]:
        async with pool.connection() as conn:
            async with conn.transaction():
                async with conn.cursor(row_factory=dict_row) as cur:
                    await cur.execute(
                        "select * from public.game_sessions where id = %s and user_id = %s for update",
                        (session_id, user_id),
                    )
                    session = await cur.fetchone()
                    if session is None:
                        raise HTTPException(status_code=404, detail='게임 세션을 찾을 수 없습니다.')
                    if session['status'] != 'active':
                        return await self.get_session_state(user_id, session_id)

                    await cur.execute(
                        """
                        select * from public.game_turns
                        where session_id = %s and turn_no = %s and status = 'open'
                        for update
                        """,
                        (session_id, session['current_turn']),
                    )
                    turn = await cur.fetchone()
                    if turn is None:
                        raise HTTPException(status_code=409, detail='현재 진행 가능한 턴이 없습니다.')

                    state = deepcopy(_as_dict(session['public_state']))
                    await self._ensure_turn_order(cur, session, state)
                    if _as_dict(state.get('active_conversation')) or _as_dict(state.get('pending_npc_question')):
                        return await self.get_session_state(user_id, session_id)
                    if str(state.get('current_actor_id') or '') == str(session['player_character_id']):
                        return await self.get_session_state(user_id, session_id)

                    await self._advance_turn_sequence(cur, session, turn, state)

                    await cur.execute(
                        """
                        update public.game_sessions
                        set public_state = %s, current_turn = %s, current_phase = %s,
                            last_saved_at = now(), updated_at = now()
                        where id = %s
                        """,
                        (Jsonb(state), session['current_turn'], session['current_phase'], session_id),
                    )
                    await cur.execute(
                        """
                        update game_private.session_runtime
                        set current_scene = %s, state = %s, state_version = state_version + 1, updated_at = now()
                        where session_id = %s
                        """,
                        (state.get('current_location'), Jsonb(state), session_id),
                    )

        return await self.get_session_state(user_id, session_id)
    async def perform_action(self, user_id: str, session_id: str, request: ActionRequest) -> dict[str, Any]:
        client_action_id = str(request.client_action_id or uuid4())
        async with pool.connection() as conn:
            async with conn.transaction():
                async with conn.cursor(row_factory=dict_row) as cur:
                    await cur.execute(
                        "select * from public.game_sessions where id = %s and user_id = %s for update",
                        (session_id, user_id),
                    )
                    session = await cur.fetchone()
                    if session is None:
                        raise HTTPException(status_code=404, detail='게임 세션을 찾을 수 없습니다.')
                    if session['status'] != 'active':
                        raise HTTPException(status_code=409, detail='이미 종료된 게임입니다.')

                    await cur.execute(
                        "select id from public.player_actions where session_id = %s and client_action_id = %s",
                        (session_id, client_action_id),
                    )
                    if await cur.fetchone():
                        return await self.get_session_state(user_id, session_id)

                    await cur.execute(
                        """
                        select * from public.game_turns
                        where session_id = %s and turn_no = %s and status = 'open'
                        for update
                        """,
                        (session_id, session['current_turn']),
                    )
                    turn = await cur.fetchone()
                    if turn is None:
                        raise HTTPException(status_code=409, detail='현재 진행 가능한 턴이 없습니다.')

                    state = deepcopy(_as_dict(session['public_state']))
                    await self._ensure_turn_order(cur, session, state)

                    conversation = _as_dict(state.get('active_conversation'))
                    if conversation:
                        if request.action_type == 'reply':
                            ended = await self._continue_conversation(
                                cur, session, turn, state, request, client_action_id, conversation
                            )
                        elif request.action_type == 'conversation_present':
                            ended = await self._present_in_conversation(
                                cur, session, turn, state, request, client_action_id, conversation
                            )
                        elif request.action_type == 'end_conversation':
                            await self._end_conversation(
                                cur, session, turn, state, request, client_action_id, conversation
                            )
                            ended = True
                        else:
                            raise HTTPException(
                                status_code=409,
                                detail='진행 중인 대화를 먼저 이어가거나 종료해 주세요.',
                            )
                        if ended:
                            await self._finish_conversation_turn(cur, session, turn, state, conversation)
                    else:
                        pending = _as_dict(state.get('pending_npc_question'))
                        if pending:
                            if request.action_type != 'reply':
                                raise HTTPException(
                                    status_code=409,
                                    detail=f"{pending.get('actor_name', '인물')}의 질문에 먼저 답해야 합니다.",
                                )
                            await self._handle_reply(
                                cur, session, turn, state, request, client_action_id, pending
                            )
                            await self._advance_turn_sequence(cur, session, turn, state)
                        else:
                            if str(state.get('current_actor_id') or '') != str(session['player_character_id']):
                                await self._advance_turn_sequence(cur, session, turn, state)
                            if _as_dict(state.get('active_conversation')):
                                pass
                            elif str(state.get('current_actor_id') or '') != str(session['player_character_id']):
                                raise HTTPException(status_code=409, detail='아직 당신의 차례가 아닙니다.')
                            else:
                                consumed = False
                                if request.action_type == 'move':
                                    consumed = await self._handle_move(
                                        cur, session, turn, state, request, client_action_id
                                    )
                                elif request.action_type == 'act':
                                    consumed = await self._handle_free_action(
                                        cur, session, turn, state, request, client_action_id,
                                        action_text=(request.input_text or '').strip(),
                                    )
                                elif request.action_type in {'search', 'inspect'}:
                                    legacy_text = (
                                        (request.input_text or '').strip()
                                        or ('주변을 꼼꼼히 살펴본다.' if request.action_type == 'search'
                                            else '눈에 보이는 것을 자세히 조사한다.')
                                    )
                                    consumed = await self._handle_free_action(
                                        cur, session, turn, state, request, client_action_id,
                                        action_text=legacy_text,
                                    )
                                elif request.action_type == 'ask':
                                    consumed = await self._handle_ask(
                                        cur, session, turn, state, request, client_action_id
                                    )
                                elif request.action_type == 'present':
                                    consumed = await self._handle_present(
                                        cur, session, turn, state, request, client_action_id
                                    )
                                elif request.action_type in {'reply', 'conversation_present', 'end_conversation'}:
                                    raise HTTPException(status_code=409, detail='현재 진행 중인 대화가 없습니다.')
                                else:
                                    raise HTTPException(status_code=400, detail='지원하지 않는 행동입니다.')

                                if consumed:
                                    state['actions_remaining'] = max(
                                        0, int(state.get('actions_remaining', 2)) - 1
                                    )
                                    if not _as_dict(state.get('active_conversation')):
                                        if int(state.get('actions_remaining', 0)) > 0:
                                            state['movement_remaining'] = 1
                                            state['current_actor_id'] = str(session['player_character_id'])
                                            state['current_actor_name'] = await self._player_name(cur, session)
                                        else:
                                            state['movement_remaining'] = 0
                                            state['actor_index'] = int(state.get('actor_index', 0)) + 1
                                            state['current_actor_id'] = None
                                            state['current_actor_name'] = None
                                            await self._set_actor_preview(session, state)

                    await cur.execute(
                        """
                        update public.game_sessions
                        set public_state = %s, current_turn = %s, current_phase = %s,
                            last_saved_at = now(), updated_at = now()
                        where id = %s
                        """,
                        (Jsonb(state), session['current_turn'], session['current_phase'], session_id),
                    )
                    await cur.execute(
                        """
                        update game_private.session_runtime
                        set current_scene = %s, state = %s, state_version = state_version + 1, updated_at = now()
                        where session_id = %s
                        """,
                        (state.get('current_location'), Jsonb(state), session_id),
                    )

        return await self.get_session_state(user_id, session_id)

    async def accuse(self, user_id: str, session_id: str, request: AccuseRequest) -> dict[str, Any]:
        raise HTTPException(
            status_code=409,
            detail='최종 범인 지목은 수사 종료 시 AI 탐정이 수행합니다.',
        )

    async def _handle_move(self, cur, session, turn, state, request, client_action_id: str) -> bool:
        if int(state.get('movement_remaining', 0)) <= 0:
            await self._insert_message(
                cur, session['id'], turn['id'], 'system', None, 'system',
                '이번 차례의 무료 이동은 이미 사용했습니다.'
            )
            return False

        location_code = str(request.payload.get('location_code') or '').strip()
        current_code = str(state.get('current_location') or '').strip()
        if not location_code:
            await self._insert_message(
                cur, session['id'], turn['id'], 'system', None, 'system',
                '이동할 장소를 선택해 주세요.'
            )
            return False
        if location_code == current_code:
            await self._insert_message(
                cur, session['id'], turn['id'], 'system', None, 'system',
                '이미 그 장소에 있습니다.'
            )
            return False

        await cur.execute(
            """
            select sl.location_code, sl.name, sl.description, l.metadata
            from public.session_locations sl
            join game_private.story_locations l
              on l.story_version_id = %s and l.code = sl.location_code
            where sl.session_id = %s and sl.location_code = %s
            """,
            (session['story_version_id'], session['id'], location_code),
        )
        location = await cur.fetchone()
        if location is None:
            await self._insert_message(
                cur, session['id'], turn['id'], 'system', None, 'system',
                '아직 갈 수 없는 장소입니다.'
            )
            return False

        await cur.execute(
            """
            select metadata
            from game_private.story_locations
            where story_version_id = %s and code = %s
            """,
            (session['story_version_id'], current_code),
        )
        current_location = await cur.fetchone()
        adjacent = _as_list(_as_dict(current_location['metadata']).get('adjacent')) if current_location else []
        if location_code not in adjacent:
            await self._insert_message(
                cur, session['id'], turn['id'], 'system', None, 'system',
                '한 번에는 연결된 장소 한 칸만 이동할 수 있습니다.'
            )
            return False

        await self._insert_action(
            cur, client_action_id, session['id'], turn['id'], request,
            payload={'location_code': location_code, 'free_move': True},
        )
        player_name = await self._player_name(cur, session)
        await self._record_witnesses(
            cur, session, turn, current_code,
            f"{player_name}이(가) {location['name']} 쪽으로 이동하는 것을 보았다.",
            source_key=f"player-move-leave:{client_action_id}",
        )

        state['current_location'] = location_code
        state['current_location_name'] = location['name']
        state['movement_remaining'] = 0
        if session['player_character_id']:
            await cur.execute(
                """
                update game_private.session_character_states
                set location_code = %s, updated_at = now()
                where session_id = %s and character_id = %s
                """,
                (location_code, session['id'], session['player_character_id']),
            )

        await self._record_witnesses(
            cur, session, turn, location_code,
            f"{player_name}이(가) {location['name']}으로 들어오는 것을 보았다.",
            source_key=f"player-move-enter:{client_action_id}",
        )
        await self._refresh_known_locations(cur, session, state)
        await self._insert_message(
            cur, session['id'], turn['id'], 'narrator', None, 'choice_result',
            f"{location['name']}으로 한 칸 이동했다. 주행동은 아직 남아 있다.",
        )
        return False

    async def _handle_free_action(
        self,
        cur,
        session,
        turn,
        state,
        request,
        client_action_id: str,
        *,
        action_text: str,
    ) -> bool:
        if not action_text:
            await self._insert_message(
                cur, session['id'], turn['id'], 'system', None, 'system',
                '무엇을 할지 입력해 주세요. 행동은 소모되지 않았습니다.'
            )
            return False

        location_code = str(state.get('current_location') or '').strip()
        await cur.execute(
            """
            select l.code, l.player_name, l.player_description, l.metadata, rc.world_prompt
            from game_private.story_locations l
            join game_private.story_runtime_configs rc on rc.story_version_id = l.story_version_id
            where l.story_version_id = %s and l.code = %s
            """,
            (session['story_version_id'], location_code),
        )
        location = await cur.fetchone()
        if location is None:
            await self._insert_message(
                cur, session['id'], turn['id'], 'system', None, 'system',
                '현재 장소 정보를 확인할 수 없습니다. 행동은 소모되지 않았습니다.'
            )
            return False

        await cur.execute(
            """
            select sc.id, sc.code, sc.display_name, sc.role_label
            from game_private.session_character_states st
            join public.story_characters sc on sc.id = st.character_id
            where st.session_id = %s
              and st.location_code = %s
              and (%s is null or sc.id <> %s)
            order by sc.sort_order
            """,
            (
                session['id'],
                location_code,
                session['player_character_id'],
                session['player_character_id'],
            ),
        )
        same_room = list(await cur.fetchall())

        await cur.execute(
            """
            select clue_code, title, content
            from public.session_clues
            where session_id = %s
            order by discovered_at
            """,
            (session['id'],),
        )
        discovered = list(await cur.fetchall())
        discovered_codes = {row['clue_code'] for row in discovered}

        await cur.execute(
            """
            select
              c.code,
              c.player_title,
              c.player_text,
              c.reveal_rule,
              c.metadata,
              exists (
                select 1 from game_private.internal_events ie
                where ie.session_id = %s
                  and ie.event_type in ('clue_hidden', 'clue_taken')
                  and ie.payload->>'clue_code' = c.code
              ) as suppressed
            from game_private.story_clues c
            join game_private.story_locations l on l.id = c.location_id
            where c.story_version_id = %s
              and l.code = %s
              and coalesce((c.reveal_rule->>'min_round')::int, 1) <= %s
            order by c.importance desc, c.created_at
            """,
            (session['id'], session['story_version_id'], location_code, session['current_turn']),
        )
        clue_rows = list(await cur.fetchall())
        hidden_candidates: list[dict[str, Any]] = []
        clue_map: dict[str, dict[str, Any]] = {}
        same_room_codes = {str(row.get('code') or '') for row in same_room}
        for clue in clue_rows:
            reveal_rule = _as_dict(clue['reveal_rule'])
            required_character = str(reveal_rule.get('character') or '').strip()
            if required_character and required_character not in same_room_codes:
                continue
            metadata = _as_dict(clue['metadata'])
            terms = _as_list(metadata.get('interaction_terms'))
            if not terms:
                terms = [clue['player_title']]
            item = {
                'code': clue['code'],
                'title': clue['player_title'],
                'interaction_terms': terms,
                'discovered': clue['code'] in discovered_codes,
                'suppressed': bool(clue['suppressed']),
            }
            hidden_candidates.append(item)
            clue_map[clue['code']] = clue

        ctx = GameMasterContext(
            world_prompt=location['world_prompt'],
            player_name=await self._player_name(cur, session),
            round_no=int(session['current_turn']),
            location_code=location_code,
            location_name=location['player_name'],
            location_description=location['player_description'],
            action_text=action_text,
            same_room_characters=same_room,
            discovered_clues=[
                {'code': row['clue_code'], 'title': row['title']}
                for row in discovered
            ],
            hidden_candidates=hidden_candidates,
        )
        decision = await self.agent_service.interpret_game_action(ctx)
        if decision.get('allowed') is not True:
            reason = str(decision.get('reason') or '현재 상황에서는 할 수 없는 행동입니다.')
            await self._insert_message(
                cur,
                session['id'],
                turn['id'],
                'system',
                None,
                'system',
                f"할 수 없는 행동입니다. {reason} 행동은 소모되지 않았습니다.",
            )
            return False

        kind = str(decision.get('kind') or 'interact')
        clue_code = str(decision.get('clue_code') or '').strip() or None
        clue = clue_map.get(clue_code) if clue_code else None

        if kind in {'hide', 'alter', 'take'}:
            if clue is None or clue_code not in discovered_codes:
                await self._insert_message(
                    cur,
                    session['id'],
                    turn['id'],
                    'system',
                    None,
                    'system',
                    '조작하거나 가져가려는 대상을 먼저 확인해야 합니다. 행동은 소모되지 않았습니다.',
                )
                return False
            if bool(clue.get('suppressed')):
                await self._insert_message(
                    cur,
                    session['id'],
                    turn['id'],
                    'system',
                    None,
                    'system',
                    '그 대상은 현재 이 장소에서 다시 조작할 수 없습니다. 행동은 소모되지 않았습니다.',
                )
                return False

        await self._insert_action(
            cur,
            client_action_id,
            session['id'],
            turn['id'],
            request,
            payload={
                **_as_dict(request.payload),
                'gm_kind': kind,
                'clue_code': clue_code,
                'location_code': location_code,
            },
        )
        await self._insert_message(
            cur,
            session['id'],
            turn['id'],
            'player',
            session['player_character_id'],
            'choice_result',
            action_text,
        )

        result_text = '행동을 시도했지만 새롭게 확인되는 사실은 없었다.'
        if clue is not None and kind in {'interact', 'inspect', 'use'} and clue_code not in discovered_codes:
            await cur.execute(
                """
                insert into public.session_clues
                  (session_id, clue_code, title, content, category, discovered_turn)
                select %s, c.code, c.player_title, c.player_text, c.category, %s
                from game_private.story_clues c
                where c.story_version_id = %s and c.code = %s
                on conflict (session_id, clue_code) do nothing
                """,
                (session['id'], session['current_turn'], session['story_version_id'], clue_code),
            )
            result_text = f"{clue['player_title']}을(를) 확인했다. {clue['player_text']}"
        elif clue is not None and kind == 'take':
            inventory = _as_list(state.get('inventory_clues'))
            if clue_code not in inventory:
                inventory.append(clue_code)
            state['inventory_clues'] = inventory
            await self._insert_internal_event(
                cur,
                session,
                'clue_taken',
                actor_character_id=session['player_character_id'],
                payload={'clue_code': clue_code, 'location_code': location_code, 'action_text': action_text},
            )
            result_text = f"{clue['player_title']}을(를) 챙겼다. 이 장소에서는 더 이상 그대로 남아 있지 않는다."
        elif clue is not None and kind == 'hide':
            await self._insert_internal_event(
                cur,
                session,
                'clue_hidden',
                actor_character_id=session['player_character_id'],
                payload={'clue_code': clue_code, 'location_code': location_code, 'action_text': action_text},
            )
            result_text = f"{clue['player_title']}을(를) 눈에 띄지 않게 숨겼다."
        elif clue is not None and kind == 'alter':
            await self._insert_internal_event(
                cur,
                session,
                'clue_altered',
                actor_character_id=session['player_character_id'],
                payload={'clue_code': clue_code, 'location_code': location_code, 'action_text': action_text},
            )
            result_text = f"{clue['player_title']}에 손을 대어 상태를 바꿨다. 조작 흔적이 남을 수도 있다."
        elif kind == 'stage':
            await self._insert_internal_event(
                cur,
                session,
                'scene_staged',
                actor_character_id=session['player_character_id'],
                payload={'location_code': location_code, 'action_text': action_text},
            )
            result_text = '현장을 의도한 모습으로 연출했다. 다른 인물이 보면 이 행동 자체를 기억할 수 있다.'

        narration = await self.agent_service.narrate_game_action(
            ctx,
            allowed=True,
            result_text=result_text,
        )
        await self._insert_message(
            cur, session['id'], turn['id'], 'narrator', None, 'choice_result', narration
        )

        await self._record_witnesses(
            cur,
            session,
            turn,
            location_code,
            f"{ctx.player_name}이(가) '{action_text}' 행동을 하는 것을 보았다.",
            source_key=f"player-action:{client_action_id}",
        )
        return True

    async def _handle_ask(self, cur, session, turn, state, request, client_action_id: str) -> bool:
        if request.target_character_id is None:
            raise HTTPException(status_code=400, detail='대화할 인물을 선택하세요.')
        question = (request.input_text or '').strip()
        if not question:
            raise HTTPException(status_code=400, detail='첫 질문을 입력하세요.')

        target_id = str(request.target_character_id)
        if session['player_character_id'] and target_id == str(session['player_character_id']):
            raise HTTPException(status_code=400, detail='자기 자신과 대화할 수 없습니다.')

        await cur.execute(
            """
            select sc.id, sc.display_name, st.location_code
            from public.story_characters sc
            join game_private.session_character_states st
              on st.session_id = %s and st.character_id = sc.id
            where sc.id = %s and sc.story_version_id = %s
            """,
            (session['id'], target_id, session['story_version_id']),
        )
        target = await cur.fetchone()
        if target is None:
            raise HTTPException(status_code=400, detail='대화할 수 없는 인물입니다.')
        location_code = str(state.get('current_location') or '')
        if target['location_code'] != location_code:
            await self._insert_message(
                cur, session['id'], turn['id'], 'system', None, 'system',
                f"{target['display_name']}은(는) 현재 이 장소에 없습니다.",
            )
            return False

        await self._insert_action(
            cur, client_action_id, session['id'], turn['id'], request, payload=request.payload
        )
        await self._insert_message(
            cur, session['id'], turn['id'], 'player', session['player_character_id'], 'dialogue', question
        )

        agent_ctx = await self._agent_context_for_character(
            cur, session, target_id, question
        )
        result = await self.agent_service.generate_conversation_reply(
            ConversationReplyContext(
                agent=agent_ctx,
                history=[{'speaker': 'player', 'text': question}],
                exchange_no=1,
                max_exchanges=3,
            )
        )
        reply = str(result.get('reply') or '').strip()
        await self._insert_message(
            cur, session['id'], turn['id'], 'character', target_id, 'dialogue', reply
        )
        transcript = f"플레이어: {question}\n{target['display_name']}: {reply}"
        await self._remember(
            cur, session['id'], target_id, turn['id'], 'dialogue', transcript,
            f"conversation:{client_action_id}", salience=75,
        )
        await self._record_witnesses(
            cur, session, turn, location_code, transcript,
            source_key=f"conversation-witness:{client_action_id}",
            exclude_ids={target_id},
        )

        ended = bool(result.get('end_conversation'))
        if ended:
            await self._insert_message(
                cur, session['id'], turn['id'], 'system', None, 'system',
                f"{target['display_name']}이(가) 대화를 마무리했다.",
            )
            return True

        state['active_conversation'] = {
            'id': client_action_id,
            'source': 'player_initiated',
            'actor_id': target_id,
            'actor_name': target['display_name'],
            'location_code': location_code,
            'exchange_count': 1,
            'max_exchanges': 3,
            'history': [
                {'speaker': 'player', 'text': question},
                {'speaker': target['display_name'], 'text': reply},
            ],
        }
        return True

    async def _agent_context_for_character(self, cur, session, character_id: str, question: str) -> AgentContext:
        await cur.execute(
            """
            select sc.id, sc.display_name,
                   cc.system_prompt, cc.private_backstory, cc.objective,
                   cc.personality, cc.initial_knowledge, cc.secrets, cc.lie_policy,
                   st.known_facts, st.false_beliefs, st.memory_summary,
                   rc.world_prompt, pc.display_name as player_name
            from public.story_characters sc
            join game_private.character_configs cc on cc.character_id = sc.id
            join game_private.session_character_states st
              on st.session_id = %s and st.character_id = sc.id
            join game_private.story_runtime_configs rc on rc.story_version_id = sc.story_version_id
            left join public.story_characters pc on pc.id = %s
            where sc.id = %s and sc.story_version_id = %s
            """,
            (session['id'], session['player_character_id'], character_id, session['story_version_id']),
        )
        row = await cur.fetchone()
        if row is None:
            raise HTTPException(status_code=400, detail='대화 상대 정보를 찾을 수 없습니다.')
        await cur.execute(
            """
            select content from game_private.agent_memories
            where session_id = %s and character_id = %s
            order by created_at desc limit 10
            """,
            (session['id'], character_id),
        )
        memories = [item['content'] for item in await cur.fetchall()]
        memories.reverse()
        return AgentContext(
            world_prompt=row['world_prompt'],
            character_name=row['display_name'],
            system_prompt=row['system_prompt'],
            private_backstory=row['private_backstory'],
            objective=row['objective'],
            personality=_as_dict(row['personality']),
            initial_knowledge=_as_list(row['initial_knowledge']),
            secrets=_as_list(row['secrets']),
            lie_policy=_as_dict(row['lie_policy']),
            known_facts=_as_list(row['known_facts']),
            false_beliefs=_as_list(row['false_beliefs']),
            memory_summary=row['memory_summary'],
            memories=memories,
            player_name=row['player_name'] or '플레이어',
            question=question,
        )

    async def _continue_conversation(
        self, cur, session, turn, state, request, client_action_id: str, conversation: dict[str, Any]
    ) -> bool:
        text = (request.input_text or '').strip()
        if not text:
            raise HTTPException(status_code=400, detail='대화 내용을 입력해 주세요.')
        actor_id = str(conversation.get('actor_id') or '')
        actor_name = str(conversation.get('actor_name') or '인물')
        location_code = str(conversation.get('location_code') or state.get('current_location') or '')

        await self._insert_action(
            cur, client_action_id, session['id'], turn['id'], request,
            payload={'conversation_id': conversation.get('id'), 'free_reply': True},
        )
        await self._insert_message(
            cur, session['id'], turn['id'], 'player', session['player_character_id'], 'dialogue', text
        )

        history = list(_as_list(conversation.get('history')))
        history.append({'speaker': 'player', 'text': text})
        exchange_no = int(conversation.get('exchange_count', 0)) + 1
        agent_ctx = await self._agent_context_for_character(cur, session, actor_id, text)
        result = await self.agent_service.generate_conversation_reply(
            ConversationReplyContext(
                agent=agent_ctx, history=history, exchange_no=exchange_no, max_exchanges=3
            )
        )
        reply = str(result.get('reply') or '').strip()
        await self._insert_message(
            cur, session['id'], turn['id'], 'character', actor_id, 'dialogue', reply
        )
        history.append({'speaker': actor_name, 'text': reply})
        transcript = f"플레이어: {text}\n{actor_name}: {reply}"
        await self._remember(
            cur, session['id'], actor_id, turn['id'], 'dialogue', transcript,
            f"conversation-followup:{client_action_id}", salience=75,
        )
        if conversation.get('source') == 'detective_bonus':
            await self._broadcast_memory(
                cur, session, turn, transcript,
                source_key=f"detective-dialogue:{client_action_id}",
            )
        elif location_code:
            await self._record_witnesses(
                cur, session, turn, location_code, transcript,
                source_key=f"conversation-followup-witness:{client_action_id}",
                exclude_ids={actor_id},
            )

        ended = bool(result.get('end_conversation')) or exchange_no >= 3
        if ended:
            state['active_conversation'] = None
            await self._insert_message(
                cur, session['id'], turn['id'], 'system', None, 'system',
                f"{actor_name}과(와)의 대화가 끝났다.",
            )
            return True

        conversation['history'] = history
        conversation['exchange_count'] = exchange_no
        state['active_conversation'] = conversation
        return False

    async def _present_in_conversation(
        self, cur, session, turn, state, request, client_action_id: str, conversation: dict[str, Any]
    ) -> bool:
        clue_code = str(request.payload.get('clue_code') or '').strip()
        inventory = {str(code) for code in _as_list(state.get('inventory_clues'))}
        if not clue_code or clue_code not in inventory:
            raise HTTPException(status_code=400, detail='현재 가지고 있는 물건만 대화 중에 제시할 수 있습니다.')
        await cur.execute(
            """
            select clue_code, title, content, category
            from public.session_clues
            where session_id = %s and clue_code = %s
            """,
            (session['id'], clue_code),
        )
        clue = await cur.fetchone()
        if clue is None:
            raise HTTPException(status_code=400, detail='제시할 물건을 찾을 수 없습니다.')

        actor_id = str(conversation.get('actor_id') or '')
        actor_name = str(conversation.get('actor_name') or '인물')
        location_code = str(conversation.get('location_code') or state.get('current_location') or '')
        statement = f"'{clue['title']}'을(를) 꺼내 보여준다."
        await self._insert_action(
            cur, client_action_id, session['id'], turn['id'], request,
            payload={'conversation_id': conversation.get('id'), 'clue_code': clue_code, 'free_reply': True},
        )
        await self._insert_message(
            cur, session['id'], turn['id'], 'player', session['player_character_id'], 'dialogue', statement
        )

        history = list(_as_list(conversation.get('history')))
        history.append({'speaker': 'player', 'text': statement})
        exchange_no = int(conversation.get('exchange_count', 0)) + 1
        agent_ctx = await self._agent_context_for_character(
            cur, session, actor_id,
            f"플레이어가 물건 '{clue['title']}'을 보여줬다. 내용: {clue['content']}",
        )
        result = await self.agent_service.generate_conversation_reply(
            ConversationReplyContext(
                agent=agent_ctx, history=history, exchange_no=exchange_no, max_exchanges=3,
                presented_item={'title': clue['title'], 'content': clue['content'], 'code': clue_code},
            )
        )
        reply = str(result.get('reply') or '').strip()
        await self._insert_message(
            cur, session['id'], turn['id'], 'character', actor_id, 'dialogue', reply
        )
        history.append({'speaker': actor_name, 'text': reply})
        transcript = f"플레이어가 {clue['title']}을(를) 제시했다. {actor_name}: {reply}"
        await self._remember(
            cur, session['id'], actor_id, turn['id'], 'evidence', transcript,
            f"conversation-evidence:{client_action_id}", salience=90,
        )
        if conversation.get('source') == 'detective_bonus':
            await self._broadcast_memory(
                cur, session, turn, transcript,
                source_key=f"detective-evidence-dialogue:{client_action_id}",
            )
        elif location_code:
            await self._record_witnesses(
                cur, session, turn, location_code, transcript,
                source_key=f"conversation-evidence-witness:{client_action_id}",
                exclude_ids={actor_id},
            )

        ended = bool(result.get('end_conversation')) or exchange_no >= 3
        if ended:
            state['active_conversation'] = None
            await self._insert_message(
                cur, session['id'], turn['id'], 'system', None, 'system',
                f"{actor_name}과(와)의 대화가 끝났다.",
            )
            return True
        conversation['history'] = history
        conversation['exchange_count'] = exchange_no
        state['active_conversation'] = conversation
        return False

    async def _end_conversation(
        self, cur, session, turn, state, request, client_action_id: str, conversation: dict[str, Any]
    ) -> None:
        actor_name = str(conversation.get('actor_name') or '인물')
        await self._insert_action(
            cur, client_action_id, session['id'], turn['id'], request,
            payload={'conversation_id': conversation.get('id'), 'free_reply': True},
        )
        await self._insert_message(
            cur, session['id'], turn['id'], 'system', None, 'system',
            f"{actor_name}과(와)의 대화를 그만두었다.",
        )
        state['active_conversation'] = None

    async def _finish_conversation_turn(self, cur, session, turn, state, conversation: dict[str, Any]) -> None:
        source = str(conversation.get('source') or '')

        if source == 'player_initiated':
            if int(state.get('actions_remaining', 0)) > 0:
                state['movement_remaining'] = 1
                state['current_actor_id'] = str(session['player_character_id'])
                state['current_actor_name'] = await self._player_name(cur, session)
                return
            state['movement_remaining'] = 0
            state['actor_index'] = int(state.get('actor_index', 0)) + 1
            state['current_actor_id'] = None
            state['current_actor_name'] = None
            await self._set_actor_preview(session, state)
            return

        if source == 'npc_initiated':
            state['actor_index'] = int(state.get('actor_index', 0)) + 1
            state['current_actor_id'] = None
            state['current_actor_name'] = None
            await self._set_actor_preview(session, state)
            return

        if source == 'detective_bonus':
            await self._advance_round(cur, session, turn, state)
            await self._set_actor_preview(session, state)
            return

        await self._set_actor_preview(session, state)
    async def _handle_present(self, cur, session, turn, state, request, client_action_id: str) -> bool:
        if request.target_character_id is None:
            raise HTTPException(status_code=400, detail='증거를 제시할 인물을 선택하세요.')
        clue_code = str(request.payload.get('clue_code') or '').strip()
        if not clue_code:
            raise HTTPException(status_code=400, detail='제시할 증거가 필요합니다.')

        target_id = str(request.target_character_id)
        if session['player_character_id'] and target_id == str(session['player_character_id']):
            raise HTTPException(status_code=400, detail='자기 자신에게 증거를 제시할 수 없습니다.')

        await cur.execute(
            """
            select clue_code, title, content
            from public.session_clues
            where session_id = %s and clue_code = %s
            """,
            (session['id'], clue_code),
        )
        clue = await cur.fetchone()
        if clue is None:
            raise HTTPException(status_code=400, detail='아직 발견하지 않은 증거입니다.')

        await cur.execute(
            """
            select sc.id, sc.display_name, cc.system_prompt, cc.private_backstory, cc.objective,
                   cc.personality, cc.initial_knowledge, cc.secrets, cc.lie_policy,
                   st.known_facts, st.false_beliefs, st.memory_summary,
                   rc.world_prompt,
                   pc.display_name as player_name
            from public.story_characters sc
            join game_private.character_configs cc on cc.character_id = sc.id
            join game_private.session_character_states st
              on st.session_id = %s and st.character_id = sc.id
            join game_private.story_runtime_configs rc on rc.story_version_id = sc.story_version_id
            left join public.story_characters pc on pc.id = %s
            where sc.id = %s and sc.story_version_id = %s
            """,
            (session['id'], session['player_character_id'], target_id, session['story_version_id']),
        )
        target = await cur.fetchone()
        if target is None:
            raise HTTPException(status_code=400, detail='증거를 제시할 수 없는 인물입니다.')

        await cur.execute(
            """
            select location_code from game_private.session_character_states
            where session_id = %s and character_id = %s
            """,
            (session['id'], target_id),
        )
        target_state = await cur.fetchone()
        if target_state is None or target_state['location_code'] != state.get('current_location'):
            await self._insert_message(
                cur,
                session['id'],
                turn['id'],
                'system',
                None,
                'system',
                f"{target['display_name']}은(는) 현재 이 장소에 없습니다. 행동은 소모되지 않았습니다.",
            )
            return False

        await cur.execute(
            """
            select content from game_private.agent_memories
            where session_id = %s and character_id = %s
            order by created_at desc limit 8
            """,
            (session['id'], target_id),
        )
        memories = [row['content'] for row in await cur.fetchall()]
        memories.reverse()

        await self._insert_action(
            cur,
            client_action_id,
            session['id'],
            turn['id'],
            request,
            payload={'clue_code': clue_code},
        )
        prompt = (
            f"플레이어가 증거 '{clue['title']}'을 제시했다. "
            f"증거 내용은 '{clue['content']}'이다. "
            "이 증거를 직접 확인한 상황으로 받아들이고, 설정된 거짓말 정책과 알고 있는 사실 범위 안에서 반응하라."
        )
        reply = await self.agent_service.generate_reply(
            AgentContext(
                world_prompt=target['world_prompt'],
                character_name=target['display_name'],
                system_prompt=target['system_prompt'],
                private_backstory=target['private_backstory'],
                objective=target['objective'],
                personality=_as_dict(target['personality']),
                initial_knowledge=_as_list(target['initial_knowledge']),
                secrets=_as_list(target['secrets']),
                lie_policy=_as_dict(target['lie_policy']),
                known_facts=_as_list(target['known_facts']),
                false_beliefs=_as_list(target['false_beliefs']),
                memory_summary=target['memory_summary'],
                memories=memories,
                player_name=target['player_name'] or '플레이어',
                question=prompt,
            )
        )
        await self._insert_message(
            cur,
            session['id'],
            turn['id'],
            'system',
            None,
            'choice_result',
            f"{target['display_name']}에게 증거 '{clue['title']}'을 제시했다.",
        )
        await self._insert_message(
            cur, session['id'], turn['id'], 'character', target_id, 'dialogue', reply
        )
        await cur.execute(
            """
            insert into game_private.agent_memories
              (session_id, character_id, turn_id, memory_type, content, source_key, salience, confidence, is_secret)
            values (%s, %s, %s, 'evidence', %s, %s, 85, 1.0, false)
            """,
            (
                session['id'],
                target_id,
                turn['id'],
                f"플레이어가 증거 '{clue['title']}'을 제시했고 나는 '{reply}'라고 반응했다.",
                client_action_id,
            ),
        )
        return True

    async def _advance_round(self, cur, session, turn, state) -> None:
        current_round = int(session['current_turn'])

        if int(state.get('detective_bonus_done_round', 0)) != current_round:
            await self._detective_bonus_action(cur, session, turn, state)
            state['detective_bonus_done_round'] = current_round
            if _as_dict(state.get('active_conversation')) or _as_dict(state.get('pending_npc_question')):
                return

        await cur.execute(
            "update public.game_turns set status = 'resolved', closed_at = now() where id = %s",
            (turn['id'],),
        )

        max_rounds = int(state.get('max_rounds', 6))
        if current_round >= max_rounds:
            await self._resolve_detective_verdict(cur, session, turn, state)
            return

        next_round = current_round + 1
        session['current_turn'] = next_round
        state['round'] = next_round
        state['actor_index'] = 0
        state['actions_remaining'] = 0
        state['movement_remaining'] = 0
        state['player_turn_key'] = None
        state['active_conversation'] = None
        state['current_actor_id'] = None
        state['current_actor_name'] = None
        state['pending_npc_question'] = None

        if next_round >= 3:
            await cur.execute(
                """
                insert into public.session_locations
                  (session_id, location_code, name, description, unlocked_turn)
                select %s, code, player_name, player_description, %s
                from game_private.story_locations
                where story_version_id = %s and code = 'back-alley'
                on conflict do nothing
                """,
                (session['id'], next_round, session['story_version_id']),
            )

        await cur.execute(
            "insert into public.game_turns (session_id, turn_no, status) values (%s, %s, 'open') returning id",
            (session['id'], next_round),
        )
        new_turn_id = (await cur.fetchone())['id']
        turn['id'] = new_turn_id
        turn['turn_no'] = next_round
        turn['status'] = 'open'
        await self._insert_message(
            cur,
            session['id'],
            new_turn_id,
            'narrator',
            None,
            'narration',
            f"라운드 {next_round}이 시작되었다. 인물들이 순서대로 행동한다.",
        )
        if next_round == 3:
            await self._insert_message(
                cur,
                session['id'],
                new_turn_id,
                'narrator',
                None,
                'system',
                '폭우가 조금 잦아들었다. 북카페 뒤 비상문을 통해 후문 골목으로 이동할 수 있다.',
            )
        await self._refresh_known_locations(cur, session, state)

    async def _run_npc_turns(self, cur, session, turn, state) -> None:
        await self._advance_turn_sequence(cur, session, turn, state)

    async def _ensure_turn_order(self, cur, session, state) -> None:
        order = _as_list(state.get('actor_order'))
        if order:
            state['actions_per_round'] = 2
            state.setdefault('active_conversation', None)
            state.setdefault('movement_remaining', 0)
            state.setdefault('player_turn_key', None)

            if int(state.get('action_rule_version', 0)) < 2:
                player_id = str(session['player_character_id']) if session['player_character_id'] else ''
                player_index = next(
                    (idx for idx, value in enumerate(order) if str(value) == player_id),
                    -1,
                )
                if int(state.get('actor_index', 0)) == player_index:
                    await cur.execute(
                        """
                        select count(*) as cnt
                        from public.player_actions pa
                        join public.game_turns gt on gt.id = pa.turn_id
                        where pa.session_id = %s
                          and gt.turn_no = %s
                          and pa.action_type = any(%s)
                        """,
                        (
                            session['id'],
                            session['current_turn'],
                            ['act', 'ask', 'search', 'inspect', 'present'],
                        ),
                    )
                    completed = int((await cur.fetchone())['cnt'])
                    state['actions_remaining'] = max(0, 2 - completed)
                    state['movement_remaining'] = 1 if state['actions_remaining'] > 0 else 0
                state['action_rule_version'] = 2
            return
        await cur.execute(
            """
            select id, display_name, role_label, sort_order
            from public.story_characters
            where story_version_id = %s
            order by sort_order
            """,
            (session['story_version_id'],),
        )
        rows = list(await cur.fetchall())
        state['actor_order'] = [str(row['id']) for row in rows]
        state['turn_order'] = [
            {
                'id': str(row['id']),
                'name': row['display_name'],
                'role': row['role_label'],
                'sort_order': row['sort_order'],
            }
            for row in rows
        ]
        player_id = str(session['player_character_id']) if session['player_character_id'] else ''
        state['actor_index'] = next(
            (idx for idx, value in enumerate(state['actor_order']) if value == player_id),
            0,
        )
        state['actions_per_round'] = 2
        state['actions_remaining'] = 2
        state['movement_remaining'] = 1
        state['player_turn_key'] = None
        state['active_conversation'] = None
        state['pending_npc_question'] = None
        state['detective_bonus_done_round'] = int(state.get('detective_bonus_done_round', 0))

    async def _advance_turn_sequence(self, cur, session, turn, state) -> None:
        await self._ensure_turn_order(cur, session, state)
        if _as_dict(state.get('active_conversation')) or _as_dict(state.get('pending_npc_question')):
            return

        order = [str(value) for value in _as_list(state.get('actor_order'))]
        index = int(state.get('actor_index', 0))
        if index >= len(order):
            await self._advance_round(cur, session, turn, state)
            await self._set_actor_preview(session, state)
            return

        actor_id = order[index]
        turn_info = next(
            (
                row for row in _as_list(state.get('turn_order'))
                if str(_as_dict(row).get('id') or '') == actor_id
            ),
            {},
        )
        state['current_actor_id'] = actor_id
        state['current_actor_name'] = _as_dict(turn_info).get('name')

        if actor_id == str(session['player_character_id']):
            turn_key = f"{session['current_turn']}:{index}"
            if state.get('player_turn_key') != turn_key:
                state['player_turn_key'] = turn_key
                state['actions_remaining'] = 1
                state['movement_remaining'] = 1
            return

        await self._run_single_npc_turn(cur, session, turn, state, actor_id)
        if _as_dict(state.get('active_conversation')):
            return
        state['actor_index'] = index + 1
        state['actions_remaining'] = 0
        await self._set_actor_preview(session, state)

    async def _set_actor_preview(self, session, state) -> None:
        order = [str(value) for value in _as_list(state.get('actor_order'))]
        index = int(state.get('actor_index', 0))
        if index >= len(order):
            state['current_actor_id'] = None
            state['current_actor_name'] = '라운드 정리'
            return
        actor_id = order[index]
        turn_info = next(
            (
                row for row in _as_list(state.get('turn_order'))
                if str(_as_dict(row).get('id') or '') == actor_id
            ),
            {},
        )
        state['current_actor_id'] = actor_id
        state['current_actor_name'] = _as_dict(turn_info).get('name')

    async def _run_single_npc_turn(self, cur, session, turn, state, actor_id: str) -> None:
        await cur.execute(
            """
            select sc.id, sc.display_name, sc.role_label, sc.code,
                   cc.system_prompt, cc.objective, cc.personality,
                   st.location_code, st.known_facts,
                   rc.world_prompt
            from public.story_characters sc
            join game_private.character_configs cc on cc.character_id = sc.id
            join game_private.session_character_states st
              on st.session_id = %s and st.character_id = sc.id
            join game_private.story_runtime_configs rc on rc.story_version_id = sc.story_version_id
            where sc.id = %s and sc.story_version_id = %s
            """,
            (session['id'], actor_id, session['story_version_id']),
        )
        actor = await cur.fetchone()
        if actor is None or not actor['location_code']:
            return

        current_code = str(actor['location_code'])
        await cur.execute(
            """
            select code, player_name, metadata
            from game_private.story_locations
            where story_version_id = %s and code = %s
            """,
            (session['story_version_id'], current_code),
        )
        loc = await cur.fetchone()
        if loc is None:
            return
        adjacent_codes = _as_list(_as_dict(loc['metadata']).get('adjacent'))

        await cur.execute(
            """
            select l.code, l.player_name
            from game_private.story_locations l
            join public.session_locations sl
              on sl.session_id = %s and sl.location_code = l.code
            where l.story_version_id = %s and l.code = any(%s)
            order by l.player_name
            """,
            (session['id'], session['story_version_id'], adjacent_codes or ['__none__']),
        )
        adjacent_locations = list(await cur.fetchall())

        await cur.execute(
            """
            select sc.id, sc.code, sc.display_name, sc.role_label, st.location_code
            from game_private.session_character_states st
            join public.story_characters sc on sc.id = st.character_id
            where st.session_id = %s
            order by sc.sort_order
            """,
            (session['id'],),
        )
        positions = list(await cur.fetchall())
        same_room = [
            row for row in positions
            if str(row['location_code']) == current_code and str(row['id']) != str(actor['id'])
        ]
        for destination in adjacent_locations:
            destination['characters'] = [
                {
                    'id': str(row['id']),
                    'display_name': row['display_name'],
                    'role_label': row['role_label'],
                }
                for row in positions
                if str(row['location_code']) == str(destination['code'])
                and str(row['id']) != str(actor['id'])
            ]

        await cur.execute(
            """
            select content
            from game_private.agent_memories
            where session_id = %s and character_id = %s
            order by created_at desc
            limit 8
            """,
            (session['id'], actor['id']),
        )
        memories = [row['content'] for row in await cur.fetchall()]
        memories.reverse()

        is_detective = actor['role_label'] == '탐정' or actor['code'] == 'kang-haejin'
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
                is_detective=is_detective,
            )
        )

        player_location = str(state.get('current_location') or '')
        move_to = str(choice.get('move_to') or '').strip()
        valid_move_codes = {str(row['code']) for row in adjacent_locations}
        if move_to and move_to in valid_move_codes:
            origin_code = current_code
            origin_name = loc['player_name']
            target_loc = next(row for row in adjacent_locations if str(row['code']) == move_to)
            target_name = target_loc['player_name']
            await cur.execute(
                """
                update game_private.session_character_states
                set location_code = %s, last_turn_processed = %s, updated_at = now()
                where session_id = %s and character_id = %s
                """,
                (move_to, session['current_turn'], session['id'], actor['id']),
            )
            exact_move = f"{actor['display_name']}이(가) {origin_name}에서 {target_name}(으)로 이동했다."
            await self._insert_internal_event(
                cur, session, 'npc_move', actor_character_id=actor['id'],
                payload={'from': origin_code, 'to': move_to, 'intent': choice.get('intent')},
            )
            await self._record_npc_action_memories(
                cur, session, turn, actor, origin_code, move_to, exact_move
            )
            if player_location in {origin_code, move_to}:
                await self._insert_message(
                    cur, session['id'], turn['id'], 'narrator', None, 'narration', exact_move
                )
            current_code = move_to
            loc = {'code': move_to, 'player_name': target_name}
            for row in positions:
                if str(row['id']) == str(actor['id']):
                    row['location_code'] = move_to
            same_room = [
                row for row in positions
                if str(row['location_code']) == current_code and str(row['id']) != str(actor['id'])
            ]

        action_type = str(choice.get('action_type') or 'observe')
        intent = str(choice.get('intent') or '주변 상황을 살핀다.')

        if action_type == 'investigate':
            await self._npc_investigate(cur, session, turn, state, actor, current_code, intent)
            return

        if action_type == 'talk':
            target_id = str(choice.get('target_character_id') or '')
            valid_targets = {str(row['id']) for row in same_room}
            if target_id in valid_targets:
                target = next(row for row in same_room if str(row['id']) == target_id)
                if target_id == str(session['player_character_id']):
                    question = str(choice.get('question') or '').strip()
                    if not question:
                        question = f"{intent} 지금 네가 아는 걸 말해줄래?"
                    await self._insert_internal_event(
                        cur, session, 'npc_asks_player',
                        actor_character_id=actor['id'], target_character_id=target_id,
                        payload={'location_code': current_code, 'question': question, 'intent': intent},
                    )
                    await self._insert_message(
                        cur, session['id'], turn['id'], 'character', actor['id'], 'dialogue', question
                    )
                    state['active_conversation'] = {
                        'id': f"npc:{session['current_turn']}:{actor['id']}",
                        'source': 'npc_initiated',
                        'actor_id': str(actor['id']),
                        'actor_name': actor['display_name'],
                        'location_code': current_code,
                        'exchange_count': 0,
                        'max_exchanges': 3,
                        'history': [{'speaker': actor['display_name'], 'text': question}],
                    }
                    await self._record_witnesses(
                        cur, session, turn, current_code,
                        f"{actor['display_name']}: {question}",
                        source_key=f"npc-question:{session['current_turn']}:{actor['id']}",
                        exclude_ids={str(actor['id'])},
                    )
                    return
                await self._npc_talk(
                    cur, session, turn, state, actor, target, current_code, intent
                )
                return
            action_type = 'observe'

        content = f"{actor['display_name']}이(가) {loc['player_name']}에서 주변 상황을 살폈다."
        await self._insert_internal_event(
            cur, session, 'npc_observe', actor_character_id=actor['id'],
            payload={'location_code': current_code, 'intent': intent},
        )
        await self._remember(
            cur, session['id'], actor['id'], turn['id'], 'observation', content,
            f"npc-observe:{session['current_turn']}:{actor['id']}",
        )
        await self._insert_message(
            cur, session['id'], turn['id'], 'narrator', None, 'narration',
            content if player_location == current_code else f"{actor['display_name']}이(가) 행동을 했다.",
        )

    async def _handle_reply(
        self,
        cur,
        session,
        turn,
        state,
        request,
        client_action_id: str,
        pending: dict[str, Any],
    ) -> None:
        reply = (request.input_text or '').strip()
        if not reply:
            raise HTTPException(status_code=400, detail='답변 내용을 입력해 주세요.')

        await self._insert_action(
            cur,
            client_action_id,
            session['id'],
            turn['id'],
            request,
            payload={'reply_to': pending.get('actor_id'), 'source': pending.get('source')},
        )
        await self._insert_message(
            cur,
            session['id'],
            turn['id'],
            'player',
            session['player_character_id'],
            'dialogue',
            reply,
        )

        actor_id = str(pending.get('actor_id') or '')
        actor_name = str(pending.get('actor_name') or '인물')
        question = str(pending.get('question') or '')
        if actor_id:
            await self._remember(
                cur,
                session['id'],
                actor_id,
                turn['id'],
                'testimony',
                f"플레이어에게 '{question}'라고 물었고 '{reply}'라고 답했다.",
                f"player-reply:{session['current_turn']}:{client_action_id}",
                salience=85,
            )

        location_code = str(pending.get('location_code') or state.get('current_location') or '')
        if pending.get('source') == 'detective_bonus':
            public_text = f"공개 추가 수사에서 플레이어가 '{reply}'라고 답했다."
            await self._broadcast_memory(
                cur,
                session,
                turn,
                public_text,
                source_key=f"detective-public-reply:{session['current_turn']}:{client_action_id}",
            )
            await self._insert_message(
                cur, session['id'], turn['id'], 'narrator', None, 'narration', public_text
            )
        elif location_code:
            await self._record_witnesses(
                cur,
                session,
                turn,
                location_code,
                f"{actor_name}의 질문에 플레이어가 '{reply}'라고 답했다.",
                source_key=f"player-reply-witness:{session['current_turn']}:{client_action_id}",
                exclude_ids={actor_id},
            )

        state['pending_npc_question'] = None

    async def _detective_bonus_action(self, cur, session, turn, state) -> None:
        await cur.execute(
            """
            select sc.id, sc.display_name, sc.code, sc.role_label,
                   st.known_facts, cc.system_prompt, cc.personality,
                   rc.world_prompt
            from public.story_characters sc
            join game_private.session_character_states st
              on st.session_id = %s and st.character_id = sc.id
            join game_private.character_configs cc on cc.character_id = sc.id
            join game_private.story_runtime_configs rc on rc.story_version_id = sc.story_version_id
            where sc.story_version_id = %s
              and (sc.role_label = '탐정' or sc.code = 'kang-haejin')
            order by sc.sort_order
            limit 1
            """,
            (session['id'], session['story_version_id']),
        )
        detective = await cur.fetchone()
        if detective is None:
            return

        await cur.execute(
            """
            select content from game_private.agent_memories
            where session_id = %s and character_id = %s
            order by created_at desc limit 15
            """,
            (session['id'], detective['id']),
        )
        memories = [row['content'] for row in await cur.fetchall()]
        memories.reverse()

        await cur.execute(
            """
            select id, display_name, role_label
            from public.story_characters
            where story_version_id = %s and id <> %s
            order by sort_order
            """,
            (session['story_version_id'], detective['id']),
        )
        characters = list(await cur.fetchall())

        await cur.execute(
            """
            select sl.location_code as code, sl.name
            from public.session_locations sl
            where sl.session_id = %s
            order by sl.unlocked_at, sl.id
            """,
            (session['id'],),
        )
        locations = list(await cur.fetchall())

        choice = await self.agent_service.choose_detective_bonus_action(
            DetectiveBonusContext(
                world_prompt=detective['world_prompt'],
                detective_name=detective['display_name'],
                known_facts=_as_list(detective['known_facts']),
                memories=memories,
                characters=characters,
                locations=locations,
            )
        )
        action_type = str(choice.get('action_type') or 'investigate')

        if action_type == 'ask':
            target_id = str(choice.get('target_character_id') or '')
            valid_ids = {str(row['id']) for row in characters}
            if target_id not in valid_ids and characters:
                target_id = str(characters[0]['id'])
            target = next((row for row in characters if str(row['id']) == target_id), None)
            if target is None:
                return
            question = str(choice.get('question') or '').strip()
            if not question:
                question = '이번 사건에서 당신이 직접 본 것과 들은 것을 시간 순서대로 말해 주세요.'

            if target_id == str(session['player_character_id']):
                message = f"[탐정 추가 수사] {detective['display_name']}: {question}"
                await self._insert_message(
                    cur, session['id'], turn['id'], 'character', detective['id'], 'dialogue', message
                )
                await self._broadcast_memory(
                    cur,
                    session,
                    turn,
                    message,
                    source_key=f"detective-bonus-question:{session['current_turn']}",
                )
                state['active_conversation'] = {
                    'id': f"detective:{session['current_turn']}",
                    'source': 'detective_bonus',
                    'actor_id': str(detective['id']),
                    'actor_name': detective['display_name'],
                    'location_code': None,
                    'exchange_count': 0,
                    'max_exchanges': 3,
                    'history': [{'speaker': detective['display_name'], 'text': question}],
                }
                return

            await cur.execute(
                """
                select sc.id, sc.display_name,
                       cc.system_prompt, cc.private_backstory, cc.objective,
                       cc.personality, cc.initial_knowledge, cc.secrets, cc.lie_policy,
                       st.known_facts, st.false_beliefs, st.memory_summary,
                       rc.world_prompt
                from public.story_characters sc
                join game_private.character_configs cc on cc.character_id = sc.id
                join game_private.session_character_states st
                  on st.session_id = %s and st.character_id = sc.id
                join game_private.story_runtime_configs rc on rc.story_version_id = sc.story_version_id
                where sc.id = %s and sc.story_version_id = %s
                """,
                (session['id'], target_id, session['story_version_id']),
            )
            target_ctx = await cur.fetchone()
            if target_ctx is None:
                return
            await cur.execute(
                """
                select content from game_private.agent_memories
                where session_id = %s and character_id = %s
                order by created_at desc limit 10
                """,
                (session['id'], target_id),
            )
            target_memories = [row['content'] for row in await cur.fetchall()]
            target_memories.reverse()
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
                    player_name=detective['display_name'],
                    question=question,
                )
            )
            public_text = (
                f"[탐정 추가 수사] {detective['display_name']}이(가) "
                f"{target_ctx['display_name']}에게 '{question}'라고 물었다. "
                f"{target_ctx['display_name']}: {reply}"
            )
            await self._remember(
                cur,
                session['id'],
                detective['id'],
                turn['id'],
                'testimony',
                f"{target_ctx['display_name']}의 공개 진술: {reply}",
                f"detective-bonus-testimony:{session['current_turn']}:{target_id}",
                salience=95,
            )
            await self._broadcast_memory(
                cur,
                session,
                turn,
                public_text,
                source_key=f"detective-bonus-public:{session['current_turn']}:{target_id}",
            )
            await self._insert_message(
                cur, session['id'], turn['id'], 'narrator', None, 'narration', public_text
            )
            return

        target_code = str(choice.get('target_location_code') or '')
        valid_codes = {str(row['code']) for row in locations}
        if target_code not in valid_codes and locations:
            target_code = str(locations[0]['code'])
        target_loc = next((row for row in locations if str(row['code']) == target_code), None)
        if target_loc is None:
            return

        await cur.execute(
            """
            select c.code, c.player_title, c.player_text, c.category
            from game_private.story_clues c
            join game_private.story_locations l on l.id = c.location_id
            where c.story_version_id = %s
              and l.code = %s
              and coalesce((c.reveal_rule->>'min_round')::int, 1) <= %s
              and not exists (
                select 1 from game_private.internal_events ie
                where ie.session_id = %s
                  and ie.event_type in ('clue_hidden', 'clue_taken')
                  and ie.payload->>'clue_code' = c.code
              )
              and not exists (
                select 1 from game_private.agent_memories am
                where am.session_id = %s
                  and am.character_id = %s
                  and am.source_key = 'detective-bonus-clue:' || c.code
              )
            order by c.importance desc, c.created_at
            limit 1
            """,
            (
                session['story_version_id'],
                target_code,
                session['current_turn'],
                session['id'],
                session['id'],
                detective['id'],
            ),
        )
        clue = await cur.fetchone()
        if clue:
            fact = f"{clue['player_title']}: {clue['player_text']}"
            await self._remember(
                cur,
                session['id'],
                detective['id'],
                turn['id'],
                'clue',
                fact,
                f"detective-bonus-clue:{clue['code']}",
                salience=100,
            )
            await cur.execute(
                """
                insert into public.session_clues
                  (session_id, clue_code, title, content, category, discovered_turn)
                values (%s, %s, %s, %s, %s, %s)
                on conflict (session_id, clue_code) do nothing
                """,
                (
                    session['id'], clue['code'], clue['player_title'],
                    clue['player_text'], clue['category'], session['current_turn'],
                ),
            )
            public_text = (
                f"[탐정 추가 수사] {detective['display_name']}이(가) "
                f"{target_loc['name']}을(를) 조사해 {clue['player_title']}을(를) 확인했다. "
                f"{clue['player_text']}"
            )
        else:
            public_text = (
                f"[탐정 추가 수사] {detective['display_name']}이(가) "
                f"{target_loc['name']}을(를) 추가 조사했지만 새로운 단서는 확인하지 못했다."
            )
        await self._broadcast_memory(
            cur,
            session,
            turn,
            public_text,
            source_key=f"detective-bonus-investigate:{session['current_turn']}:{target_code}",
        )
        await self._insert_message(
            cur, session['id'], turn['id'], 'narrator', None, 'narration', public_text
        )

    async def _broadcast_memory(
        self,
        cur,
        session,
        turn,
        content: str,
        *,
        source_key: str,
    ) -> None:
        await cur.execute(
            """
            select character_id
            from game_private.session_character_states
            where session_id = %s
            """,
            (session['id'],),
        )
        for row in await cur.fetchall():
            await self._remember(
                cur,
                session['id'],
                row['character_id'],
                turn['id'],
                'public_investigation',
                content,
                source_key,
                salience=90,
            )

    async def _npc_talk(
        self,
        cur,
        session,
        turn,
        state,
        actor,
        target,
        location_code: str,
        intent: str,
    ) -> None:
        target_id = str(target['id'])
        await cur.execute(
            """
            select sc.id, sc.display_name,
                   cc.system_prompt, cc.private_backstory, cc.objective,
                   cc.personality, cc.initial_knowledge, cc.secrets, cc.lie_policy,
                   st.known_facts, st.false_beliefs, st.memory_summary,
                   rc.world_prompt
            from public.story_characters sc
            join game_private.character_configs cc on cc.character_id = sc.id
            join game_private.session_character_states st
              on st.session_id = %s and st.character_id = sc.id
            join game_private.story_runtime_configs rc
              on rc.story_version_id = sc.story_version_id
            where sc.id = %s and sc.story_version_id = %s
            """,
            (session['id'], target_id, session['story_version_id']),
        )
        target_ctx = await cur.fetchone()
        if target_ctx is None:
            return

        await cur.execute(
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

        question = (
            f"{intent} "
            "사건과 관련해서 네가 직접 본 것, 들은 것, 기억하는 동선을 말해 줘. "
            "확실하지 않은 것은 확실한 척하지 마."
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
                question=question,
            )
        )

        exchange = (
            f"{actor['display_name']}이(가) {target_ctx['display_name']}에게 사건에 대해 물었고, "
            f"{target_ctx['display_name']}은(는) '{reply}'라고 답했다."
        )
        await self._insert_internal_event(
            cur,
            session,
            'npc_talk',
            actor_character_id=actor['id'],
            target_character_id=target_id,
            payload={
                'location_code': location_code,
                'intent': intent,
                'reply': reply,
            },
        )
        await self._remember(
            cur,
            session['id'],
            actor['id'],
            turn['id'],
            'testimony',
            f"{target_ctx['display_name']}의 진술: {reply}",
            f"npc-testimony:{session['current_turn']}:{actor['id']}:{target_id}",
            salience=80,
        )
        await self._remember(
            cur,
            session['id'],
            target_id,
            turn['id'],
            'dialogue',
            exchange,
            f"npc-talk-heard:{session['current_turn']}:{actor['id']}:{target_id}",
            salience=65,
        )
        await self._record_witnesses(
            cur,
            session,
            turn,
            location_code,
            exchange,
            source_key=f"npc-talk-witness:{session['current_turn']}:{actor['id']}:{target_id}",
            exclude_ids={str(actor['id']), target_id},
        )

        await self._insert_message(
            cur,
            session['id'],
            turn['id'],
            'narrator',
            None,
            'narration',
            exchange if state.get('current_location') == location_code
            else f"{actor['display_name']}이(가) 행동을 했다.",
        )

    async def _npc_investigate(self, cur, session, turn, state, actor, location_code: str, intent: str) -> None:
        await cur.execute(
            """
            select c.code, c.player_title, c.player_text
            from game_private.story_clues c
            join game_private.story_locations l on l.id = c.location_id
            where c.story_version_id = %s
              and l.code = %s
              and coalesce((c.reveal_rule->>'min_round')::int, 1) <= %s
              and (
                c.reveal_rule->>'character' is null
                or exists (
                  select 1
                  from game_private.session_character_states st2
                  join public.story_characters sc2 on sc2.id = st2.character_id
                  where st2.session_id = %s
                    and st2.location_code = %s
                    and sc2.code = c.reveal_rule->>'character'
                )
              )
              and not exists (
                select 1 from game_private.internal_events ie
                where ie.session_id = %s
                  and ie.event_type in ('clue_hidden', 'clue_taken')
                  and ie.payload->>'clue_code' = c.code
              )
              and not exists (
                select 1 from game_private.agent_memories am
                where am.session_id = %s
                  and am.character_id = %s
                  and am.source_key = 'npc-clue:' || c.code
              )
            order by c.importance desc, c.created_at
            limit 1
            """,
            (
                session['story_version_id'],
                location_code,
                session['current_turn'],
                session['id'],
                location_code,
                session['id'],
                session['id'],
                actor['id'],
            ),
        )
        clue = await cur.fetchone()
        if clue is None:
            content = f"{actor['display_name']}이(가) 주변을 조사했지만 새로운 단서를 찾지 못했다."
        else:
            content = f"{actor['display_name']}이(가) {clue['player_title']}을(를) 확인했다."
            fact = f"{clue['player_title']}: {clue['player_text']}"
            await self._remember(
                cur,
                session['id'],
                actor['id'],
                turn['id'],
                'clue',
                fact,
                f"npc-clue:{clue['code']}",
                salience=90,
            )
            facts = _as_list(actor['known_facts'])
            if fact not in facts:
                facts.append(fact)
                actor['known_facts'] = facts
                await cur.execute(
                    """
                    update game_private.session_character_states
                    set known_facts = %s, last_turn_processed = %s, updated_at = now()
                    where session_id = %s and character_id = %s
                    """,
                    (Jsonb(facts), session['current_turn'], session['id'], actor['id']),
                )

        await self._insert_internal_event(
            cur,
            session,
            'npc_investigate',
            actor_character_id=actor['id'],
            payload={'location_code': location_code, 'intent': intent, 'result': content},
        )
        await self._insert_message(
            cur,
            session['id'],
            turn['id'],
            'narrator',
            None,
            'narration',
            content if state.get('current_location') == location_code
            else f"{actor['display_name']}이(가) 행동을 했다.",
        )
        await self._record_witnesses(
            cur,
            session,
            turn,
            location_code,
            content,
            source_key=f"npc-investigate:{session['current_turn']}:{actor['id']}",
            exclude_ids={str(actor['id'])},
        )

    async def _resolve_detective_verdict(self, cur, session, turn, state) -> None:
        await cur.execute(
            """
            select sc.id, sc.display_name, st.known_facts, rc.world_prompt
            from public.story_characters sc
            join game_private.session_character_states st
              on st.session_id = %s and st.character_id = sc.id
            join game_private.story_runtime_configs rc on rc.story_version_id = sc.story_version_id
            where sc.story_version_id = %s
              and (sc.role_label = '탐정' or sc.code = 'kang-haejin')
            order by sc.sort_order
            limit 1
            """,
            (session['id'], session['story_version_id']),
        )
        detective = await cur.fetchone()
        if detective is None:
            raise HTTPException(status_code=500, detail='탐정 캐릭터가 없습니다.')

        await cur.execute(
            """
            select content
            from game_private.agent_memories
            where session_id = %s and character_id = %s
            order by created_at
            """,
            (session['id'], detective['id']),
        )
        memories = [row['content'] for row in await cur.fetchall()]

        await cur.execute(
            """
            select id, display_name, role_label
            from public.story_characters
            where story_version_id = %s
              and is_player_selectable = true
              and id <> %s
            order by sort_order
            """,
            (session['story_version_id'], detective['id']),
        )
        candidates = list(await cur.fetchall())
        verdict = await self.agent_service.choose_detective_verdict(
            DetectiveVerdictContext(
                world_prompt=detective['world_prompt'],
                detective_name=detective['display_name'],
                known_facts=_as_list(detective['known_facts']),
                memories=memories,
                candidates=candidates,
            )
        )
        valid_ids = {str(row['id']) for row in candidates}
        accused_id = str(verdict.get('accused_character_id') or '')
        if accused_id not in valid_ids and candidates:
            accused_id = str(candidates[0]['id'])
        accused = next((row for row in candidates if str(row['id']) == accused_id), None)

        await cur.execute(
            "select culprit_character_id from game_private.story_solutions where story_version_id = %s",
            (session['story_version_id'],),
        )
        solution = await cur.fetchone()
        culprit_id = str(solution['culprit_character_id']) if solution and solution['culprit_character_id'] else ''
        caught = accused_id == culprit_id
        player_id = str(session['player_character_id']) if session['player_character_id'] else ''
        player_is_culprit = player_id == culprit_id
        if player_is_culprit:
            ending_code = 'culprit-caught' if caught else 'culprit-escape'
        else:
            ending_code = 'suspect-innocent-win' if caught else 'suspect-innocent-fail'

        reasoning = str(verdict.get('reasoning') or '').strip()
        accused_name = accused['display_name'] if accused else '알 수 없는 인물'
        state['detective_verdict'] = {
            'detective_name': detective['display_name'],
            'accused_character_id': accused_id,
            'accused_name': accused_name,
            'reasoning': reasoning,
        }
        await self._insert_message(
            cur,
            session['id'],
            turn['id'],
            'character',
            detective['id'],
            'dialogue',
            f"최종 지목은 {accused_name}입니다. {reasoning}".strip(),
        )

        await cur.execute(
            """
            select title, ending_text
            from game_private.story_endings
            where story_version_id = %s and code = %s
            """,
            (session['story_version_id'], ending_code),
        )
        ending = await cur.fetchone()
        if ending:
            await self._insert_message(
                cur,
                session['id'],
                turn['id'],
                'narrator',
                None,
                'narration',
                f"{ending['title']}\n{ending['ending_text']}",
            )

        await cur.execute(
            """
            update public.game_sessions
            set status = 'completed', current_phase = 'completed', ending_code = %s,
                completed_at = now(), last_saved_at = now(), updated_at = now()
            where id = %s
            """,
            (ending_code, session['id']),
        )
        session['status'] = 'completed'
        session['current_phase'] = 'completed'
        state['actions_remaining'] = 0
        state['current_actor_id'] = None
        state['current_actor_name'] = None

    async def _player_is_culprit(self, cur, session) -> bool:
        if session['player_character_id'] is None:
            return False
        await cur.execute(
            """
            select 1
            from game_private.story_solutions
            where story_version_id = %s and culprit_character_id = %s
            """,
            (session['story_version_id'], session['player_character_id']),
        )
        return await cur.fetchone() is not None

    async def _refresh_known_locations(self, cur, session, state) -> None:
        location_code = str(state.get('current_location') or '')
        await cur.execute(
            """
            select sc.id, st.location_code
            from game_private.session_character_states st
            join public.story_characters sc on sc.id = st.character_id
            where st.session_id = %s
              and st.location_code = %s
              and (%s is null or sc.id <> %s)
            """,
            (
                session['id'],
                location_code,
                session['player_character_id'],
                session['player_character_id'],
            ),
        )
        known = deepcopy(_as_dict(state.get('known_character_locations')))
        for row in await cur.fetchall():
            known[str(row['id'])] = {
                'location_code': row['location_code'],
                'turn_no': int(session['current_turn']),
                'source': 'seen',
            }
        state['known_character_locations'] = known

    async def _record_witnesses(
        self,
        cur,
        session,
        turn,
        location_code: str,
        content: str,
        *,
        source_key: str,
        exclude_ids: set[str] | None = None,
    ) -> None:
        exclude = exclude_ids or set()
        await cur.execute(
            """
            select character_id
            from game_private.session_character_states
            where session_id = %s and location_code = %s
            """,
            (session['id'], location_code),
        )
        for row in await cur.fetchall():
            character_id = str(row['character_id'])
            if session['player_character_id'] and character_id == str(session['player_character_id']):
                continue
            if character_id in exclude:
                continue
            await self._remember(
                cur,
                session['id'],
                character_id,
                turn['id'],
                'observation',
                content,
                source_key,
                salience=70,
            )

    async def _record_npc_action_memories(
        self,
        cur,
        session,
        turn,
        actor,
        origin_code: str,
        target_code: str,
        content: str,
    ) -> None:
        for code, suffix in ((origin_code, 'leave'), (target_code, 'enter')):
            await self._record_witnesses(
                cur,
                session,
                turn,
                code,
                content,
                source_key=f"npc-move:{session['current_turn']}:{actor['id']}:{suffix}",
                exclude_ids={str(actor['id'])},
            )

    async def _remember(
        self,
        cur,
        session_id,
        character_id,
        turn_id,
        memory_type: str,
        content: str,
        source_key: str,
        *,
        salience: int = 70,
    ) -> None:
        await cur.execute(
            """
            insert into game_private.agent_memories
              (session_id, character_id, turn_id, memory_type, content, source_key, salience, confidence, is_secret)
            select %s, %s, %s, %s, %s, %s, %s, 1.0, false
            where not exists (
                select 1 from game_private.agent_memories
                where session_id = %s and character_id = %s and source_key = %s
            )
            """,
            (
                session_id,
                character_id,
                turn_id,
                memory_type,
                content,
                source_key,
                salience,
                session_id,
                character_id,
                source_key,
            ),
        )

    async def _insert_internal_event(
        self,
        cur,
        session,
        event_type: str,
        *,
        actor_character_id=None,
        target_character_id=None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        await cur.execute(
            """
            insert into game_private.internal_events
              (session_id, turn_no, event_type, actor_character_id, target_character_id, payload)
            values (%s, %s, %s, %s, %s, %s)
            """,
            (
                session['id'],
                session['current_turn'],
                event_type,
                actor_character_id,
                target_character_id,
                Jsonb(payload or {}),
            ),
        )

    async def _player_name(self, cur, session) -> str:
        if not session['player_character_id']:
            return '플레이어'
        await cur.execute(
            "select display_name from public.story_characters where id = %s",
            (session['player_character_id'],),
        )
        row = await cur.fetchone()
        return row['display_name'] if row else '플레이어'

    async def _insert_action(self, cur, client_action_id, session_id, turn_id, request, payload) -> None:
        await cur.execute(
            """
            insert into public.player_actions
              (client_action_id, session_id, turn_id, action_type, target_character_id, input_text, payload)
            values (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                client_action_id,
                session_id,
                turn_id,
                request.action_type,
                str(request.target_character_id) if request.target_character_id else None,
                request.input_text,
                Jsonb(payload or {}),
            ),
        )

    async def _insert_message(self, cur, session_id, turn_id, speaker_type, speaker_character_id, message_kind, content) -> None:
        await cur.execute(
            """
            insert into public.session_messages
              (session_id, turn_id, speaker_type, speaker_character_id, message_kind, content)
            values (%s, %s, %s, %s, %s, %s)
            """,
            (session_id, turn_id, speaker_type, speaker_character_id, message_kind, content),
        )
