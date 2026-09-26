from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    if old not in text:
        raise SystemExit(f'{label}: target block not found')
    return text.replace(old, new, 1)


game_path = Path('backend/app/game_service.py')
game = game_path.read_text(encoding='utf-8')
game_old = """            state['action_cycle'] = cycle
            state['actor_index'] = len(order)
            await self._advance_round(cur, session, turn, state)
            await self._set_actor_preview(session, state)
            if (
                not _as_dict(state.get('active_conversation'))
                and not _as_dict(state.get('pending_npc_question'))
                and not _as_dict(state.get('pending_evidence_submission'))
            ):
                await self._advance_turn_sequence(cur, session, turn, state)
            return
"""
game_new = """            state['action_cycle'] = cycle
            state['actor_index'] = len(order)
            round_before = int(session['current_turn'])
            await self._advance_round(cur, session, turn, state)
            await self._set_actor_preview(session, state)

            # Continue automatically only when a new round was actually opened.
            # End-of-round gates intentionally keep the same round and must
            # return control to the client instead of recursing indefinitely.
            round_advanced = int(session['current_turn']) != round_before
            blocked = bool(
                _as_dict(state.get('active_conversation'))
                or _as_dict(state.get('pending_npc_question'))
                or _as_dict(state.get('pending_evidence_submission'))
                or _as_dict(state.get('pending_final_vote'))
            )
            completed = (
                str(session.get('status') or '') == 'completed'
                or bool(_as_dict(state.get('detective_verdict')))
            )
            if round_advanced and not blocked and not completed:
                await self._advance_turn_sequence(cur, session, turn, state)
            return
"""
game = replace_once(game, game_old, game_new, 'round recursion guard')
game_path.write_text(game, encoding='utf-8')

agent_path = Path('backend/app/agent_service.py')
agent = agent_path.read_text(encoding='utf-8')
conversation_old = """                max_output_tokens=min(self.settings.openai_max_output_tokens, 180),
            )
            raw = (response.output_text or '').strip()
"""
conversation_new = """                max_output_tokens=min(self.settings.openai_max_output_tokens, 280),
            )
            raw = (response.output_text or '').strip()
"""
# First occurrence is generate_conversation_reply.
agent = replace_once(agent, conversation_old, conversation_new, 'conversation output budget')
agent = agent.replace(
    "logger.exception('OpenAI conversation response failed; using fallback')",
    "logger.warning('OpenAI conversation response failed; using fallback')",
    1,
)
json_old = """                max_output_tokens=min(self.settings.openai_max_output_tokens, 180),
            )
            raw = (response.output_text or '').strip()
            if raw.startswith('```'):
                raw = raw.split('\\n', 1)[1] if '\\n' in raw else raw
                raw = raw.rsplit('```', 1)[0].strip()
            json_start = raw.find('{')
"""
json_new = """                max_output_tokens=min(self.settings.openai_max_output_tokens, 280),
            )
            raw = (response.output_text or '').strip()
            if raw.startswith('```'):
                raw = raw.split('\\n', 1)[1] if '\\n' in raw else raw
                raw = raw.rsplit('```', 1)[0].strip()
            json_start = raw.find('{')
"""
agent = replace_once(agent, json_old, json_new, 'structured output budget')
agent = agent.replace(
    """            logger.warning(\n                'OpenAI structured response failed; using deterministic fallback',\n                exc_info=True,\n            )\n""",
    """            logger.warning(\n                'OpenAI structured response failed; using deterministic fallback'\n            )\n""",
    1,
)
agent_path.write_text(agent, encoding='utf-8')

enhanced_path = Path('backend/app/enhanced_game_service.py')
enhanced = enhanced_path.read_text(encoding='utf-8')
ending_old = """        caught = accused_id == culprit_id
        player_id = str(session.get('player_character_id') or '')
        player_is_culprit = player_id == culprit_id
        if player_is_culprit:
            ending_code = 'culprit-caught' if caught else 'culprit-escape'
        else:
            ending_code = 'suspect-innocent-win' if caught else 'suspect-innocent-fail'

        reasoning = str(verdict.get('reasoning') or '').strip()
"""
ending_new = """        player_id = str(session.get('player_character_id') or '')
        player_is_culprit = player_id == culprit_id
        success = accused_id != player_id
        if player_is_culprit:
            ending_code = 'culprit-escape' if success else 'culprit-caught'
        else:
            ending_code = 'suspect-innocent-win' if success else 'suspect-innocent-fail'

        reasoning = str(verdict.get('reasoning') or '').strip()
"""
enhanced = replace_once(enhanced, ending_old, ending_new, 'player outcome ending code')
enhanced = enhanced.replace(
    """        success = accused_id != player_id
        state['player_outcome'] = {
""",
    """        state['player_outcome'] = {
""",
    1,
)
enhanced_path.write_text(enhanced, encoding='utf-8')

print('simulation hardening patch applied')
