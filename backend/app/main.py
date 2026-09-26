from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .agent_service import AgentService
from .auth import AuthUser, get_current_user
from .config import get_settings
from .db import close_pool, open_pool
from .enhanced_game_service import EnhancedGameService
from .schemas import AccuseRequest, ActionRequest, FinalVoteRequest, StartSessionRequest


settings = get_settings()
agent_service = AgentService(settings)
game_service = EnhancedGameService(agent_service)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await open_pool()
    yield
    await close_pool()


app = FastAPI(title=settings.app_name, version='0.3.0', lifespan=lifespan)
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
async def create_session(
    request: StartSessionRequest,
    user: AuthUser = Depends(get_current_user),
):
    return await game_service.start_session(user.id, request)


@app.get('/api/v1/sessions/{session_id}')
async def session_state(
    session_id: str,
    user: AuthUser = Depends(get_current_user),
):
    return await game_service.get_session_state(user.id, session_id)


@app.delete('/api/v1/sessions/{session_id}')
async def remove_session(
    session_id: str,
    user: AuthUser = Depends(get_current_user),
):
    return await game_service.delete_session(user.id, session_id)


@app.post('/api/v1/sessions/{session_id}/actions')
async def action(
    session_id: str,
    request: ActionRequest,
    user: AuthUser = Depends(get_current_user),
):
    return await game_service.perform_action(user.id, session_id, request)


@app.post('/api/v1/sessions/{session_id}/advance')
async def advance(
    session_id: str,
    user: AuthUser = Depends(get_current_user),
):
    return await game_service.advance_game(user.id, session_id)


@app.post('/api/v1/sessions/{session_id}/final-vote')
async def final_vote(
    session_id: str,
    request: FinalVoteRequest,
    user: AuthUser = Depends(get_current_user),
):
    return await game_service.submit_final_vote(user.id, session_id, request)


@app.post('/api/v1/sessions/{session_id}/accuse')
async def accuse(
    session_id: str,
    request: AccuseRequest,
    user: AuthUser = Depends(get_current_user),
):
    return await game_service.accuse(user.id, session_id, request)
