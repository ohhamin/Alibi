from pathlib import Path

path = Path(__file__).resolve().parents[1] / 'app' / 'game_service.py'
text = path.read_text()

# 1) Event-locked clues must never be part of the random initial 3-clue distribution.
old_initial = """              where c.story_version_id = %s
                and not exists (
"""
new_initial = """              where c.story_version_id = %s
                and coalesce((c.reveal_rule->>'initial_eligible')::boolean, true) = true
                and coalesce(c.reveal_rule->>'required_event', '') = ''
                and not exists (
"""
if new_initial not in text:
    if old_initial not in text:
        raise SystemExit('missing initial evidence allocation anchor')
    text = text.replace(old_initial, new_initial, 1)

# 2) Player searches should only expose clues whose required story event already fired.
old_player = """        clue_rows = list(await cur.fetchall())
        hidden_candidates: list[dict[str, Any]] = []
        clue_map: dict[str, dict[str, Any]] = {}
        same_room_codes = {str(row.get('code') or '') for row in same_room}
        for clue in clue_rows:
            reveal_rule = _as_dict(clue['reveal_rule'])
            required_character = str(reveal_rule.get('character') or '').strip()
            if required_character and required_character not in same_room_codes:
                continue
"""
new_player = """        clue_rows = list(await cur.fetchall())
        await cur.execute(
            \"\"\"
            select payload->>'event_code' as event_code
            from game_private.internal_events
            where session_id = %s
              and event_type = 'story_scripted_event'
            \"\"\",
            (session['id'],),
        )
        fired_story_events = {
            str(row['event_code'])
            for row in await cur.fetchall()
            if row.get('event_code')
        }
        hidden_candidates: list[dict[str, Any]] = []
        clue_map: dict[str, dict[str, Any]] = {}
        same_room_codes = {str(row.get('code') or '') for row in same_room}
        for clue in clue_rows:
            reveal_rule = _as_dict(clue['reveal_rule'])
            required_event = str(reveal_rule.get('required_event') or '').strip()
            if required_event and required_event not in fired_story_events:
                continue
            required_events = {
                str(item)
                for item in _as_list(reveal_rule.get('required_events'))
                if str(item).strip()
            }
            if required_events and not required_events.issubset(fired_story_events):
                continue
            required_character = str(reveal_rule.get('character') or '').strip()
            if required_character and required_character not in same_room_codes:
                continue
"""
if new_player not in text:
    if old_player not in text:
        raise SystemExit('missing player clue filter anchor')
    text = text.replace(old_player, new_player, 1)

# 3) Detective bonus search and NPC investigation must honor the same required_event gate.
old_gate = """              and coalesce((c.reveal_rule->>'min_round')::int, 1) <= %s
              and (
                c.reveal_rule->>'character' is null
"""
new_gate = """              and coalesce((c.reveal_rule->>'min_round')::int, 1) <= %s
              and (
                coalesce(c.reveal_rule->>'required_event', '') = ''
                or exists (
                    select 1
                    from game_private.internal_events ie_gate
                    where ie_gate.session_id = %s
                      and ie_gate.event_type = 'story_scripted_event'
                      and ie_gate.payload->>'event_code' = c.reveal_rule->>'required_event'
                )
              )
              and (
                c.reveal_rule->>'character' is null
"""
occurrences = text.count(old_gate)
if occurrences:
    if occurrences != 2:
        raise SystemExit(f'unexpected gated search anchor count: {occurrences}')
    text = text.replace(old_gate, new_gate)

old_bonus_tuple = """                session['story_version_id'],
                target_code,
                session['current_turn'],
                session['id'],
                target_code,
                session['id'],
                session['id'],
                session['id'],
"""
new_bonus_tuple = """                session['story_version_id'],
                target_code,
                session['current_turn'],
                session['id'],
                session['id'],
                target_code,
                session['id'],
                session['id'],
                session['id'],
"""
if new_bonus_tuple not in text:
    if old_bonus_tuple not in text:
        raise SystemExit('missing detective gate tuple anchor')
    text = text.replace(old_bonus_tuple, new_bonus_tuple, 1)

old_npc_tuple = """                session['story_version_id'],
                location_code,
                session['current_turn'],
                session['id'],
                location_code,
                session['id'],
                session['id'],
                session['id'],
"""
new_npc_tuple = """                session['story_version_id'],
                location_code,
                session['current_turn'],
                session['id'],
                session['id'],
                location_code,
                session['id'],
                session['id'],
                session['id'],
"""
if new_npc_tuple not in text:
    if old_npc_tuple not in text:
        raise SystemExit('missing npc gate tuple anchor')
    text = text.replace(old_npc_tuple, new_npc_tuple, 1)

path.write_text(text)
print('patched', path)
