from pathlib import Path

path = Path(__file__).resolve().parents[1] / 'app' / 'enhanced_game_service.py'
text = path.read_text()
original = text

import_old = "from .game_service import GameService, _as_dict, _as_list\nfrom .schemas import FinalVoteRequest, StartSessionRequest\n"
import_new = "from .game_service import GameService, _as_dict, _as_list\nfrom .story_events import run_story_events\nfrom .schemas import FinalVoteRequest, StartSessionRequest\n"
if import_new not in text:
    if import_old not in text:
        raise SystemExit('missing import anchor')
    text = text.replace(import_old, import_new, 1)

start_old = '''                        await self._ensure_social_state(
                            cur,
                            row['story_version_id'],
                            state,
                        )
                        await cur.execute(
                            "update public.game_sessions set public_state = %s where id = %s",
'''
start_new = '''                        await self._ensure_social_state(
                            cur,
                            row['story_version_id'],
                            state,
                        )
                        await run_story_events(
                            self,
                            cur,
                            {
                                'id': session_id,
                                'story_version_id': row['story_version_id'],
                                'player_character_id': row['player_character_id'],
                                'current_turn': int(session.get('current_turn') or 1),
                            },
                            None,
                            state,
                        )
                        await cur.execute(
                            "update public.game_sessions set public_state = %s where id = %s",
'''
if start_new not in text:
    if start_old not in text:
        raise SystemExit('missing start-session event anchor')
    text = text.replace(start_old, start_new, 1)

free_action_method = '''    async def _handle_free_action(
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
        consumed = await super()._handle_free_action(
            cur,
            session,
            turn,
            state,
            request,
            client_action_id,
            action_text=action_text,
        )
        if consumed:
            await run_story_events(self, cur, session, turn, state)
        return consumed

'''
conversation_anchor = '    async def _continue_conversation(\n'
if free_action_method not in text:
    if conversation_anchor not in text:
        raise SystemExit('missing conversation anchor')
    text = text.replace(conversation_anchor, free_action_method + conversation_anchor, 1)

publish_old = '''        if clue is None:
            return None
        await self._ensure_social_state(cur, session['story_version_id'], state)
'''
publish_new = '''        if clue is None:
            return None
        await run_story_events(self, cur, session, turn, state)
        await self._ensure_social_state(cur, session['story_version_id'], state)
'''
if publish_new not in text:
    if publish_old not in text:
        raise SystemExit('missing publish-evidence event anchor')
    text = text.replace(publish_old, publish_new, 1)

advance_old = '''        if current_round < max_rounds:
            await super()._advance_round(cur, session, turn, state)
            return
'''
advance_new = '''        if current_round < max_rounds:
            await super()._advance_round(cur, session, turn, state)
            await run_story_events(self, cur, session, turn, state)
            return
'''
if advance_new not in text:
    if advance_old not in text:
        raise SystemExit('missing advance-round event anchor')
    text = text.replace(advance_old, advance_new, 1)

if text == original:
    print('already patched')
else:
    path.write_text(text)
    print('patched', path)
