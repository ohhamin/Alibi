from copy import deepcopy
from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .agent_service import AgentContext, AgentService
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
                        select %s, sc.story_version_id, sc.id, %s, cc.objective,
                               '{}'::jsonb, '{}'::jsonb, cc.initial_knowledge, '[]'::jsonb, null, '{}'::jsonb, 0
                        from public.story_characters sc
                        join game_private.character_configs cc on cc.character_id = sc.id
                        where sc.story_version_id = %s
                        on conflict (session_id, character_id) do nothing
                        """,
                        (session_id, starting_location['code'], str(request.story_version_id)),
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

                return {
                    'session': session,
                    'current_turn': turn,
                    'characters': characters,
                    'player_role': player_role,
                    'messages': messages,
                    'clues': clues,
                    'locations': locations,
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
                    consumed = 0

                    if request.action_type == 'move':
                        await self._handle_move(cur, session, turn, state, request, client_action_id)
                    elif request.action_type in {'search', 'inspect'}:
                        await self._handle_investigate(cur, session, turn, state, request, client_action_id)
                        consumed = 1
                    elif request.action_type == 'ask':
                        await self._handle_ask(cur, session, turn, state, request, client_action_id)
                        consumed = 1
                    else:
                        raise HTTPException(status_code=400, detail='지원하지 않는 행동입니다.')

                    if consumed:
                        remaining = max(0, int(state.get('actions_remaining', 0)) - consumed)
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
                    player_is_culprit = player_id == culprit_id
                    accusation_correct = accused_id == culprit_id
