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
      