from dataclasses import dataclass

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import Settings, get_settings

bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthUser:
    id: str
    email: str | None = None


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    settings: Settings = Depends(get_settings),
) -> AuthUser:
    if credentials is None or credentials.scheme.lower() != 'bearer':
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='로그인이 필요합니다.')

    headers = {
        'apikey': settings.supabase_publishable_key,
        'Authorization': f'Bearer {credentials.credentials}',
    }
    async with httpx.AsyncClient(timeout=8.0) as client:
        response = await client.get(f'{settings.supabase_url}/auth/v1/user', headers=headers)

    if response.status_code != 200:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='유효하지 않은 로그인 세션입니다.')

    payload = response.json()
    user_id = payload.get('id')
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='사용자 정보를 확인할 수 없습니다.')
    return AuthUser(id=str(user_id), email=payload.get('email'))
