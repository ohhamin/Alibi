from copy import deepcopy
from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .agent_service import (
    AgentContext,
    AgentService,
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
                    state['actions_per_round'] = int(rules.get('actions_per_round', 2))
                    state['actions_remaining'] = int(rules.get('actions_per_round', 2))
                    state['max_rounds'] = int(rules.get('max_rounds', story['max_turns'] or 6))
                    state['current_location'] = starting_location['code']
                    state['current_location_name'] = starting_location['player_name']

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
                        select sc.id, st.location_code
                        from game_private.session_character_states st
                        join public.story_characters sc on sc.id = st.character_id
                        where st.session_id = %s
                          and st.location_code = %s
                          and sc.id <> %s
                        """,
                        (session_id, starting_location['code'], str(request.player_character_id)),
                    )
                    state['known_character_locations'] = {
                        str(row['id']): {
                            'location_code': row['location_code'],
                            'turn_no': 1,
                            'source': 'seen',
                        }
                        for row in await cur.fetchall()
                    }
                    state['inventory_clues'] = []
                    state['world_changes'] = []

                    await cur.execute(
                        "update public.game_sessions set public_state = %s where id = %s",
                        (Jsonb(state), session_id),
                    )
                    await cur.execute(
                        "update game_private.session_runtime set state = %s where session_id = %s",
                        (Jsonb(state), session_id),
                    )

                    opening = story['opening_text'] or f"{story['title']} 사건이 시작되었습니다."
                    await self._insert_message(cur, session_id, turn_id, 'narrator', None, 'narration', opening)
                    await self._insert_message(
                        cur,
                        session_id,
                        turn_id,
                        'system',
                        None,
                        'system',
                        f"당신은 {player['display_name']}({player['role_label']})입니다. 라운드당 핵심 행동은 {state['actions_per_round']}회입니다.",
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
                    select id, code, display_name, role_label, public_bio, avatar_url,
                           is_player_selectable, sort_order
                    from public.story_characters
                    where story_version_id = %s
                    order by sort_order
                    """,
                    (session['story_version_id'],),
                )
                characters = list(await cur.fetchall())

                player_role = None
                if session['player_character_id']:
                    await cur.execute(
                        """
                        select sc.id, sc.display_name, sc.role_label, sc.public_bio,
                               cc.private_backstory, cc.objective, cc.secrets
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
                    select id, location_code, name, description, unlocked_turn, unlocked_at
                    from public.session_locations where session_id = %s
                    order by unlocked_at, id
                    """,
                    (session_id,),
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
                      and st.location_code = %s
                      and (%s is null or sc.id <> %s)
                    order by sc.sort_order
                    """,
                    (
                        session_id,
                        current_location,
                        session['player_character_id'],
                        session['player_character_id'],
                    ),
                )
                visible_characters = list(await cur.fetchall())

                current_location_detail = next(
                    (item for item in locations if item['location_code'] == current_location),
                    None,
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
                    'known_character_locations': _as_dict(state.get('known_character_locations')),
                    'ending': ending,
                    'solution': solution,
                }

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
                    if session['current_phase'] == 'accusation':
                        raise HTTPException(status_code=409, detail='이제 최종 지목을 진행해야 합니다.')

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
                    consumed = False

                    if request.action_type == 'move':
                        consumed = await self._handle_move(
                            cur, session, turn, state, request, client_action_id
                        )
                    elif request.action_type == 'act':
                        consumed = await self._handle_free_action(
                            cur,
                            session,
                            turn,
                            state,
                            request,
                            client_action_id,
                            action_text=(request.input_text or '').strip(),
                        )
                    elif request.action_type in {'search', 'inspect'}:
                        legacy_text = (
                            (request.input_text or '').strip()
                            or ('주변을 꼼꼼히 살펴본다.' if request.action_type == 'search'
                                else '눈에 보이는 것을 자세히 조사한다.')
                        )
                        consumed = await self._handle_free_action(
                            cur,
                            session,
                            turn,
                            state,
                            request,
                            client_action_id,
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
                    else:
                        raise HTTPException(status_code=400, detail='지원하지 않는 행동입니다.')

                    if consumed:
                        remaining = max(0, int(state.get('actions_remaining', 0)) - 1)
                        state['actions_remaining'] = remaining
                        if remaining == 0:
                            await self._advance_round(cur, session, turn, state)

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
                    if session['current_phase'] != 'accusation':
                        raise HTTPException(status_code=409, detail='아직 최종 지목 단계가 아닙니다.')

                    await cur.execute(
                        "select culprit_character_id from game_private.story_solutions where story_version_id = %s",
                        (session['story_version_id'],),
                    )
                    solution = await cur.fetchone()
                    if solution is None or solution['culprit_character_id'] is None:
                        raise HTTPException(status_code=500, detail='정답 데이터가 없습니다.')

                    culprit_id = str(solution['culprit_character_id'])
                    accused_id = str(request.culprit_character_id)
                    player_id = str(session['player_character_id']) if session['player_character_id'] else None

                    await cur.execute(
                        """
                        select id from public.story_characters
                        where id = %s
                          and story_version_id = %s
                          and is_player_selectable = true
                        """,
                        (accused_id, session['story_version_id']),
                    )
                    if await cur.fetchone() is None:
                        raise HTTPException(status_code=400, detail='최종 지목할 수 없는 인물입니다.')
                    if accused_id == player_id:
                        raise HTTPException(status_code=400, detail='자기 자신은 최종 지목할 수 없습니다.')

                    player_is_culprit = player_id == culprit_id
                    accusation_correct = accused_id == culprit_id

                    if player_is_culprit:
                        await cur.execute(
                            "select clue_code from public.session_clues where session_id = %s",
                            (session_id,),
                        )
                        clue_codes = {row['clue_code'] for row in await cur.fetchall()}
                        core = {'clue-body-time', 'clue-bookend', 'clue-contract', 'clue-coffee-receipt'}
                        player_accused = len(core & clue_codes) >= 3
                        ending_code = 'culprit-caught' if player_accused else 'culprit-escape'
                    else:
                        ending_code = 'suspect-innocent-win' if accusation_correct else 'suspect-innocent-fail'

                    await cur.execute(
                        "select id from public.game_turns where session_id = %s order by turn_no desc limit 1",
                        (session_id,),
                    )
                    turn = await cur.fetchone()
                    turn_id = turn['id'] if turn else None

                    await cur.execute(
                        """
                        insert into public.player_actions
                          (client_action_id, session_id, turn_id, action_type, target_character_id, input_text, payload)
                        values (%s, %s, %s, 'accuse', %s, %s, '{}'::jsonb)
                        """,
                        (str(uuid4()), session_id, turn_id, accused_id, request.reasoning),
                    )

                    await cur.execute(
                        """
                        select title, ending_text from game_private.story_endings
                        where story_version_id = %s and code = %s
                        """,
                        (session['story_version_id'], ending_code),
                    )
                    ending = await cur.fetchone()
                    if ending is None:
                        raise HTTPException(status_code=500, detail='엔딩 데이터를 찾을 수 없습니다.')

                    await self._insert_message(
                        cur, session_id, turn_id, 'narrator', None, 'narration',
                        f"{ending['title']}\n{ending['ending_text']}"
                    )
                    await cur.execute(
                        """
                        update public.game_sessions
                        set status = 'completed', current_phase = 'completed', ending_code = %s,
                            completed_at = now(), last_saved_at = now(), updated_at = now()
                        where id = %s
                        """,
                        (ending_code, session_id),
                    )

        return await self.get_session_state(user_id, session_id)

    async def _handle_move(self, cur, session, turn, state, request, client_action_id: str) -> bool:
        location_code = str(request.payload.get('location_code') or '').strip()
        current_code = str(state.get('current_location') or '').strip()
        if not location_code:
            await self._insert_message(
                cur, session['id'], turn['id'], 'system', None, 'system',
                '이동할 장소를 선택해 주세요. 행동은 소모되지 않았습니다.'
            )
            return False
        if location_code == current_code:
            await self._insert_message(
                cur, session['id'], turn['id'], 'system', None, 'system',
                '이미 그 장소에 있습니다. 행동은 소모되지 않았습니다.'
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
                '아직 갈 수 없는 장소입니다. 행동은 소모되지 않았습니다.'
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
                '현재 위치에서 바로 이동할 수 없는 장소입니다. 행동은 소모되지 않았습니다.'
            )
            return False

        await self._insert_action(
            cur,
            client_action_id,
            session['id'],
            turn['id'],
            request,
            payload={'location_code': location_code},
        )
        await self._insert_message(
            cur,
            session['id'],
            turn['id'],
            'player',
            session['player_character_id'],
            'action',
            f"{location['name']}으로 이동한다.",
        )

        player_name = await self._player_name(cur, session)
        await self._record_witnesses(
            cur,
            session,
            turn,
            current_code,
            f"{player_name}이(가) {location['name']} 쪽으로 이동하는 것을 보았다.",
            source_key=f"player-move-leave:{client_action_id}",
        )

        state['current_location'] = location_code
        state['current_location_name'] = location['name']
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
            cur,
            session,
            turn,
            location_code,
            f"{player_name}이(가) {location['name']}으로 들어오는 것을 보았다.",
            source_key=f"player-move-enter:{client_action_id}",
        )
        await self._refresh_known_locations(cur, session, state)

        await self._insert_message(
            cur,
            session['id'],
            turn['id'],
            'narrator',
            None,
            'choice_result',
            f"{location['name']}으로 이동했다.",
        )
        return True

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
            'action',
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
            raise HTTPException(status_code=400, detail='질문 내용을 입력하세요.')
        target_id = str(request.target_character_id)
        if session['player_character_id'] and target_id == str(session['player_character_id']):
            raise HTTPException(status_code=400, detail='플레이어 자신의 캐릭터에게는 질문할 수 없습니다.')

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
            raise HTTPException(status_code=400, detail='대화할 수 없는 인물입니다.')

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

        await self._insert_action(cur, client_action_id, session['id'], turn['id'], request, payload=request.payload)
        await self._insert_message(
            cur, session['id'], turn['id'], 'player', session['player_character_id'], 'dialogue', question
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
                question=question,
            )
        )
        await self._insert_message(cur, session['id'], turn['id'], 'character', target_id, 'dialogue', reply)
        await cur.execute(
            """
            insert into game_private.agent_memories
              (session_id, character_id, turn_id, memory_type, content, source_key, salience, confidence, is_secret)
            values (%s, %s, %s, 'dialogue', %s, %s, 70, 1.0, false)
            """,
            (session['id'], target_id, turn['id'], f"{target['player_name'] or '플레이어'}가 '{question}'라고 물었고 나는 '{reply}'라고 답했다.", client_action_id),
        )
        await self._record_witnesses(
            cur,
            session,
            turn,
            str(state.get('current_location') or ''),
            f"{target['player_name'] or '플레이어'}와 {target['display_name']}이(가) 대화하는 것을 들었다.",
            source_key=f"conversation:{client_action_id}",
            exclude_ids={target_id},
        )
        return True

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
        await self._run_npc_turns(cur, session, turn, state)

        await cur.execute(
            "update public.game_turns set status = 'resolved', closed_at = now() where id = %s",
            (turn['id'],),
        )
        current_round = int(session['current_turn'])
        max_rounds = int(state.get('max_rounds', 6))
        if current_round >= max_rounds:
            if await self._player_is_culprit(cur, session):
                await self._resolve_detective_verdict(cur, session, turn, state)
            else:
                session['current_phase'] = 'accusation'
                state['actions_remaining'] = 0
                await self._insert_message(
                    cur,
                    session['id'],
                    turn['id'],
                    'narrator',
                    None,
                    'narration',
                    '수사 시간이 끝났다. 이제 확보한 정보로 최종 지목을 해야 한다.',
                )
            return

        next_round = current_round + 1
        session['current_turn'] = next_round
        state['round'] = next_round
        state['actions_remaining'] = int(state.get('actions_per_round', 2))

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
        await self._insert_message(
            cur,
            session['id'],
            new_turn_id,
            'narrator',
            None,
            'narration',
            f"라운드 {next_round}이 시작되었다. 행동은 {state['actions_remaining']}회다.",
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
        await cur.execute(
            """
            select rc.world_prompt
            from game_private.story_runtime_configs rc
            where rc.story_version_id = %s
            """,
            (session['story_version_id'],),
        )
        runtime = await cur.fetchone()
        world_prompt = runtime['world_prompt'] if runtime else ''

        await cur.execute(
            """
            select sc.id, sc.display_name, sc.role_label, sc.code,
                   cc.system_prompt, cc.objective,
                   st.location_code, st.known_facts
            from public.story_characters sc
            join game_private.character_configs cc on cc.character_id = sc.id
            join game_private.session_character_states st
              on st.session_id = %s and st.character_id = sc.id
            where sc.story_version_id = %s
              and (%s is null or sc.id <> %s)
            order by sc.sort_order
            """,
            (
                session['id'],
                session['story_version_id'],
                session['player_character_id'],
                session['player_character_id'],
            ),
        )
        actors = list(await cur.fetchall())

        for actor in actors:
            current_code = actor['location_code']
            if not current_code:
                continue

            await cur.execute(
                """
                select player_name, metadata
                from game_private.story_locations
                where story_version_id = %s and code = %s
                """,
                (session['story_version_id'], current_code),
            )
            loc = await cur.fetchone()
            if loc is None:
                continue
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
                (
                    session['id'],
                    session['story_version_id'],
                    adjacent_codes or ['__none__'],
                ),
            )
            adjacent_locations = list(await cur.fetchall())

            await cur.execute(
                """
                select sc.id, sc.display_name, sc.role_label
                from game_private.session_character_states st
                join public.story_characters sc on sc.id = st.character_id
                where st.session_id = %s
                  and st.location_code = %s
                  and sc.id <> %s
                order by sc.sort_order
                """,
                (session['id'], current_code, actor['id']),
            )
            same_room = list(await cur.fetchall())

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
                    world_prompt=world_prompt,
                    character_id=str(actor['id']),
                    character_name=actor['display_name'],
                    system_prompt=actor['system_prompt'],
                    objective=actor['objective'],
                    current_location=current_code,
                    current_location_name=loc['player_name'],
                    adjacent_locations=adjacent_locations,
                    same_room_characters=same_room,
                    known_facts=_as_list(actor['known_facts']),
                    memories=memories,
                    is_detective=is_detective,
                )
            )

            action_type = str(choice.get('action_type') or 'observe')
            intent = str(choice.get('intent') or '주변을 살핀다.')

            if action_type == 'move':
                target_code = str(choice.get('target_location_code') or '')
                valid_codes = {row['code'] for row in adjacent_locations}
                if target_code not in valid_codes:
                    action_type = 'observe'
                else:
                    await cur.execute(
                        """
                        update game_private.session_character_states
                        set location_code = %s, last_turn_processed = %s, updated_at = now()
                        where session_id = %s and character_id = %s
                        """,
                        (target_code, session['current_turn'], session['id'], actor['id']),
                    )
                    await cur.execute(
                        """
                        select player_name from game_private.story_locations
                        where story_version_id = %s and code = %s
                        """,
                        (session['story_version_id'], target_code),
                    )
                    target_loc = await cur.fetchone()
                    target_name = target_loc['player_name'] if target_loc else target_code
                    await self._insert_internal_event(
                        cur,
                        session,
                        'npc_move',
                        actor_character_id=actor['id'],
                        payload={
                            'from': current_code,
                            'to': target_code,
                            'intent': intent,
                        },
                    )
                    if state.get('current_location') in {current_code, target_code}:
                        known = deepcopy(_as_dict(state.get('known_character_locations')))
                        known[str(actor['id'])] = {
                            'location_code': target_code,
                            'turn_no': int(session['current_turn']),
                            'source': 'seen',
                        }
                        state['known_character_locations'] = known
                        text = (
                            f"{actor['display_name']}이(가) {target_name} 쪽으로 이동했다."
                            if state.get('current_location') == current_code
                            else f"{actor['display_name']}이(가) {target_name}에 들어왔다."
                        )
                        await self._insert_message(
                            cur, session['id'], turn['id'], 'narrator', None, 'npc_action', text
                        )
                    await self._record_npc_action_memories(
                        cur,
                        session,
                        turn,
                        actor,
                        current_code,
                        target_code,
                        f"{actor['display_name']}이(가) {target_name}으로 이동했다.",
                    )
                    continue

            if action_type == 'investigate':
                await self._npc_investigate(cur, session, turn, state, actor, current_code, intent)
            elif action_type == 'talk':
                target_id = str(choice.get('target_character_id') or '')
                valid_targets = {str(row['id']) for row in same_room}
                if target_id not in valid_targets:
                    action_type = 'observe'
                else:
                    target = next(row for row in same_room if str(row['id']) == target_id)
                    content = f"{actor['display_name']}이(가) {target['display_name']}에게 말을 걸었다."
                    await self._insert_internal_event(
                        cur,
                        session,
                        'npc_talk',
                        actor_character_id=actor['id'],
                        target_character_id=target_id,
                        payload={'location_code': current_code, 'intent': intent},
                    )
                    await self._remember(
                        cur,
                        session['id'],
                        actor['id'],
                        turn['id'],
                        'dialogue',
                        content,
                        f"npc-talk:{session['current_turn']}:{actor['id']}:{target_id}",
                    )
                    await self._remember(
                        cur,
                        session['id'],
                        target_id,
                        turn['id'],
                        'dialogue',
                        content,
                        f"npc-talk-heard:{session['current_turn']}:{actor['id']}:{target_id}",
                    )
                    if state.get('current_location') == current_code:
                        await self._insert_message(
                            cur, session['id'], turn['id'], 'narrator', None, 'npc_action', content
                        )
                    continue

            if action_type == 'observe':
                content = f"{actor['display_name']}이(가) {loc['player_name']}에서 주변 상황을 살폈다."
                await self._insert_internal_event(
                    cur,
                    session,
                    'npc_observe',
                    actor_character_id=actor['id'],
                    payload={'location_code': current_code, 'intent': intent},
                )
                await self._remember(
                    cur,
                    session['id'],
                    actor['id'],
                    turn['id'],
                    'observation',
                    content,
                    f"npc-observe:{session['current_turn']}:{actor['id']}",
                )
                if state.get('current_location') == current_code:
                    await self._insert_message(
                        cur, session['id'], turn['id'], 'narrator', None, 'npc_action', content
                    )

        await self._refresh_known_locations(cur, session, state)

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
        if state.get('current_location') == location_code:
            await self._insert_message(
                cur, session['id'], turn['id'], 'narrator', None, 'npc_action', content
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
            session['current_phase'] = 'accusation'
            return

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
        ending_code = 'culprit-caught' if caught else 'culprit-escape'
        reasoning = str(verdict.get('reasoning') or '').strip()
        accused_name = accused['display_name'] if accused else '알 수 없는 인물'

        await self._insert_message(
            cur,
            session['id'],
            turn['id'],
            'character',
            detective['id'],
            'dialogue',
            f"제 최종 지목은 {accused_name}입니다. {reasoning}".strip(),
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
