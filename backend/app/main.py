from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from psycopg.types.json import Jsonb

from .agent_service import AgentService
from .auth import AuthUser, get_current_user
from .config import get_settings
from .db import close_pool, open_pool, pool
from .game_service import GameService
from .schemas import AccuseRequest, ActionRequest, StartSessionRequest


class InterrogationEvidenceGameService(GameService):
    """Only force evidence disclosure immediately before detective interrogations."""

    mandatory_submission_rounds = {2, 5}

    async def _clear_stale_submission(
        self,
        user_id: str,
        session_id: str,
    ) -> None:
        """Release old round-end prompts created by the previous rule set."""
        async with pool.connection() as conn:
            async with conn.transaction():
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        select current_turn, public_state
                        from public.game_sessions
                        where id = %s and user_id = %s and status = 'active'
                        """,
                        (session_id, user_id),
                    )
                    row = await cur.fetchone()
                    if row is None:
                        return

                    current_round = int(row[0])
                    state = row[1] if isinstance(row[1], dict) else {}
                    pending = state.get('pending_evidence_submission')
                    if (
                        current_round in self.mandatory_submission_rounds
                        or not isinstance(pending, dict)
                        or not pending
                    ):
                        return

                    state = dict(state)
                    state['pending_evidence_submission'] = None
                    state['round_submission_done_round'] = current_round
                    await cur.execute(
                        """
                        update public.game_sessions
                        set public_state = %s, last_saved_at = now(), updated_at = now()
                        where id = %s and user_id = %s
                        """,
                        (Jsonb(state), session_id, user_id),
                    )
                    await cur.execute(
                        """
                        update game_private.session_runtime
                        set state = %s, state_version = state_version + 1,
                            updated_at = now()
                        where session_id = %s
                        """,
                        (Jsonb(state), session_id),
                    )

    async def get_session_state(self, user_id: str, session_id: str):
        await self._clear_stale_submission(user_id, session_id)
        return await super().get_session_state(user_id, session_id)

    async def advance_game(self, user_id: str, session_id: str):
        await self._clear_stale_submission(user_id, session_id)
        return await super().advance_game(user_id, session_id)

    async def perform_action(
        self,
        user_id: str,
        session_id: str,
        request: ActionRequest,
    ):
        await self._clear_stale_submission(user_id, session_id)
        return await super().perform_action(user_id, session_id, request)

    async def start_session(
        self,
        user_id: str,
        request: StartSessionRequest,
    ):
        result = await super().start_session(user_id, request)
        session = result.get('session') or {}
        session_id = str(session.get('id') or '')
        if not session_id:
            return result

        async with pool.connection() as conn:
            async with conn.transaction():
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        update public.session_messages
                        set content = replace(
                          content,
                          '라운드 종료 시 소지 증거가 있다면 반드시 1개를 탐정에게 제출해야 하며, 제출된 증거는 모두에게 공개됩니다.',
                          '2라운드와 5라운드 종료 후 탐정의 비공개 취조가 시작되기 전에, 소지 증거가 있다면 반드시 1개를 탐정에게 제출해야 합니다. 제출된 증거는 모두에게 공개되며, 그 외 라운드에는 강제 제출이 없습니다.'
                        )
                        where session_id = %s
                          and speaker_type = 'system'
                          and content like '%%라운드 종료 시 소지 증거%%'
                        """,
                        (session_id,),
                    )
        return await self.get_session_state(user_id, session_id)

    async def _auto_submit_npc_evidence(self, cur, session, turn, state) -> None:
        await cur.execute(
            """
            select sc.id, sc.code, sc.display_name
            from public.story_characters sc
            where sc.story_version_id = %s
              and sc.is_player_selectable = true
              and (%s is null or sc.id <> %s)
            order by sc.sort_order
            """,
            (
                session['story_version_id'],
                session['player_character_id'],
                session['player_character_id'],
            ),
        )
        suspects = list(await cur.fetchall())
        for suspect in suspects:
            await cur.execute(
                """
                select h.clue_code, c.player_title, c.metadata
                from game_private.session_evidence_holdings h
                join game_private.story_clues c
                  on c.story_version_id = %s and c.code = h.clue_code
                where h.session_id = %s
                  and h.holder_character_id = %s
                  and h.status = 'held'
                order by
                  case
                    when c.metadata->>'supports_alibi_for' = %s then 0
                    when coalesce(c.metadata->>'suspect_code', '') <> ''
                         and c.metadata->>'suspect_code' <> %s then 1
                    when coalesce(c.metadata->>'suspect_code', '') = '' then 2
                    when c.metadata->>'suspect_code' = %s then 9
                    else 3
                  end,
                  random()
                limit 1
                """,
                (
                    session['story_version_id'],
                    session['id'],
                    suspect['id'],
                    suspect['code'],
                    suspect['code'],
                    suspect['code'],
                ),
            )
            clue = await cur.fetchone()
            if clue is None:
                continue

            metadata = clue['metadata'] if isinstance(clue['metadata'], dict) else {}
            supports_self = (
                str(metadata.get('supports_alibi_for') or '')
                == str(suspect['code'])
            )
            implicates = str(metadata.get('suspect_code') or '')
            if supports_self:
                opinion = '제 동선을 확인하는 데 도움이 될 수 있는 자료라서 제출합니다.'
            elif implicates and implicates != str(suspect['code']):
                opinion = '다른 사람의 동선과 정황을 확인하는 데 필요해 보여 제출합니다.'
            elif implicates == str(suspect['code']):
                opinion = '제가 가진 자료이므로 숨기지 않고 제출하겠습니다.'
            else:
                opinion = '수사에 도움이 될 수 있어 제가 가진 자료를 제출합니다.'

            await self._publish_evidence(
                cur,
                session,
                turn,
                state,
                str(clue['clue_code']),
                str(suspect['id']),
                opinion=opinion,
                source='round_submission',
            )

    async def _prepare_round_end_submissions(self, cur, session, turn, state) -> bool:
        current_round = int(session['current_turn'])

        if current_round not in self.mandatory_submission_rounds:
            state['round_submission_done_round'] = current_round
            state['pending_evidence_submission'] = None
            return True

        if int(state.get('round_submission_done_round', 0)) == current_round:
            return True

        await self._auto_submit_npc_evidence(cur, session, turn, state)

        player_id = str(session.get('player_character_id') or '')
        if player_id:
            await cur.execute(
                """
                select count(*) as cnt
                from game_private.session_evidence_holdings
                where session_id = %s
                  and holder_character_id = %s
                  and status = 'held'
                """,
                (session['id'], player_id),
            )
            held_count = int((await cur.fetchone())['cnt'])
            if held_count > 0:
                pending = state.get('pending_evidence_submission')
                if not isinstance(pending, dict) or not pending:
                    state['pending_evidence_submission'] = {
                        'round': current_round,
                        'required': True,
                        'context': 'detective_interrogation',
                        'message': (
                            '탐정의 비공개 취조가 시작되기 전, 소지한 증거 중 '
                            '1개를 제출해야 합니다.'
                        ),
                    }
                    await self._insert_message(
                        cur,
                        session['id'],
                        turn['id'],
                        'system',
                        None,
                        'system',
                        (
                            '탐정 취조 전 증거 제출: 소지한 증거 중 1개를 '
                            '탐정에게 제출하세요. 제출한 증거와 의견은 모두에게 '
                            '공개됩니다. 나머지 증거는 계속 비공개로 보유할 수 있습니다.'
                        ),
                    )
                return False

        state['round_submission_done_round'] = current_round
        state['pending_evidence_submission'] = None
        return True


settings = get_settings()
agent_service = AgentService(settings)
game_service = InterrogationEvidenceGameService(agent_service)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await open_pool()
    yield
    await close_pool()


app = FastAPI(title=settings.app_name, version='0.2.0', lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=settings.cors_origin_list != ['*'],
    allow_methods=['*'],
    allow_headers=['*'],
)


@app.get('/health')
async def health() -> dict[str, str | bool]:
    return {
        'status': 'ok',
        'environment': settings.environment,
        'openai_configured': agent_service.enabled,
    }


@app.get('/api/v1/stories')
async def stories(_: AuthUser = Depends(get_current_user)):
    return {'items': await game_service.list_stories()}


@app.get('/api/v1/sessions')
async def sessions(user: AuthUser = Depends(get_current_user)):
    return {'items': await game_service.list_sessions(user.id)}


@app.post('/api/v1/sessions')
async def create_session(request: StartSessionRequest, user: AuthUser = Depends(get_current_user)):
    return await game_service.start_session(user.id, request)


@app.get('/api/v1/sessions/{session_id}')
async def session_state(session_id: str, user: AuthUser = Depends(get_current_user)):
    return await game_service.get_session_state(user.id, session_id)


@app.delete('/api/v1/sessions/{session_id}')
async def remove_session(session_id: str, user: AuthUser = Depends(get_current_user)):
    return await game_service.delete_session(user.id, session_id)


@app.post('/api/v1/sessions/{session_id}/actions')
async def action(session_id: str, request: ActionRequest, user: AuthUser = Depends(get_current_user)):
    return await game_service.perform_action(user.id, session_id, request)


@app.post('/api/v1/sessions/{session_id}/advance')
async def advance(session_id: str, user: AuthUser = Depends(get_current_user)):
    return await game_service.advance_game(user.id, session_id)


@app.post('/api/v1/sessions/{session_id}/accuse')
async def accuse(session_id: str, request: AccuseRequest, user: AuthUser = Depends(get_current_user)):
    return await game_service.accuse(user.id, session_id, request)
