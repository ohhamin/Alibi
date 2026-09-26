from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _string_set(value: Any) -> set[str]:
    return {str(item) for item in _as_list(value) if str(item).strip()}


def _matches(
    trigger: dict[str, Any],
    *,
    round_no: int,
    public_clues: set[str],
    known_clues: set[str],
    fired_events: set[str],
) -> bool:
    if not trigger:
        return False
    if trigger.get('round') is not None and int(trigger['round']) != round_no:
        return False
    if trigger.get('min_round') is not None and round_no < int(trigger['min_round']):
        return False
    if trigger.get('max_round') is not None and round_no > int(trigger['max_round']):
        return False

    all_public = _string_set(trigger.get('all_public_clues'))
    if all_public and not all_public.issubset(public_clues):
        return False
    any_public = _string_set(trigger.get('any_public_clues'))
    if any_public and not (any_public & public_clues):
        return False
    none_public = _string_set(trigger.get('none_public_clues'))
    if none_public and (none_public & public_clues):
        return False

    all_known = _string_set(trigger.get('all_known_clues'))
    if all_known and not all_known.issubset(known_clues):
        return False
    any_known = _string_set(trigger.get('any_known_clues'))
    if any_known and not (any_known & known_clues):
        return False

    required_events = _string_set(trigger.get('required_events'))
    if required_events and not required_events.issubset(fired_events):
        return False
    blocked_events = _string_set(trigger.get('blocked_events'))
    if blocked_events and (blocked_events & fired_events):
        return False

    if trigger.get('min_public_clues') is not None:
        if len(public_clues) < int(trigger['min_public_clues']):
            return False
    return True


async def _turn_id(cur, session: dict[str, Any], turn: dict[str, Any] | None):
    if turn and turn.get('id'):
        return turn['id']
    await cur.execute(
        """
        select id
        from public.game_turns
        where session_id = %s
        order by case when status = 'open' then 0 else 1 end, turn_no desc, opened_at desc
        limit 1
        """,
        (session['id'],),
    )
    row = await cur.fetchone()
    return row['id'] if row else None


async def _character_map(cur, story_version_id: str) -> dict[str, dict[str, Any]]:
    await cur.execute(
        """
        select id, code, display_name
        from public.story_characters
        where story_version_id = %s
        order by sort_order
        """,
        (story_version_id,),
    )
    return {str(row['code']): row for row in await cur.fetchall()}


async def _append_known_fact(cur, session_id: str, character_id: str, fact: str) -> bool:
    if not fact.strip():
        return False
    await cur.execute(
        """
        select known_facts
        from game_private.session_character_states
        where session_id = %s and character_id = %s
        for update
        """,
        (session_id, character_id),
    )
    row = await cur.fetchone()
    if row is None:
        return False
    facts = [str(item) for item in _as_list(row['known_facts']) if str(item).strip()]
    if fact in facts:
        return False
    facts.append(fact)
    await cur.execute(
        """
        update game_private.session_character_states
        set known_facts = %s, updated_at = now()
        where session_id = %s and character_id = %s
        """,
        (Jsonb(facts), session_id, character_id),
    )
    return True


async def run_story_events(
    service,
    cur,
    session: dict[str, Any],
    turn: dict[str, Any] | None,
    state: dict[str, Any],
) -> list[str]:
    """Evaluate DB-authored scripted events and apply newly satisfied ones.

    Events are intentionally data driven. New story branches can be added by editing
    story_scripted_events without adding another hard-coded if/else block.
    """
    story_version_id = str(session['story_version_id'])
    session_id = str(session['id'])
    fired_now: list[str] = []
    turn_id = await _turn_id(cur, session, turn)

    # A newly fired event can satisfy another event, so allow a short event chain.
    for _ in range(12):
        await cur.execute(
            "select clue_code from public.session_clues where session_id = %s",
            (session_id,),
        )
        public_clues = {str(row['clue_code']) for row in await cur.fetchall()}
        await cur.execute(
            "select clue_code from game_private.session_evidence_holdings where session_id = %s",
            (session_id,),
        )
        known_clues = public_clues | {str(row['clue_code']) for row in await cur.fetchall()}
        await cur.execute(
            """
            select payload->>'event_code' as event_code
            from game_private.internal_events
            where session_id = %s and event_type = 'story_scripted_event'
            """,
            (session_id,),
        )
        fired_events = {
            str(row['event_code']) for row in await cur.fetchall() if row.get('event_code')
        }

        round_no = int(session.get('current_turn') or state.get('round') or 1)
        await cur.execute(
            """
            select code, event_type, trigger_rule, player_text, internal_payload,
                   once_per_session, priority
            from game_private.story_scripted_events
            where story_version_id = %s
            order by priority desc, created_at, code
            """,
            (story_version_id,),
        )
        events = list(await cur.fetchall())
        event = next(
            (
                row for row in events
                if (not row['once_per_session'] or str(row['code']) not in fired_events)
                and _matches(
                    _as_dict(row['trigger_rule']),
                    round_no=round_no,
                    public_clues=public_clues,
                    known_clues=known_clues,
                    fired_events=fired_events,
                )
            ),
            None,
        )
        if event is None:
            break

        code = str(event['code'])
        payload = _as_dict(event['internal_payload'])
        changed = False
        characters = await _character_map(cur, story_version_id)

        unlock_values = payload.get('unlock_location')
        unlock_codes = (
            [str(unlock_values)]
            if isinstance(unlock_values, str)
            else [str(item) for item in _as_list(unlock_values)]
        )
        for location_code in unlock_codes:
            if not location_code:
                continue
            await cur.execute(
                """
                insert into public.session_locations
                  (session_id, location_code, name, description, unlocked_turn)
                select %s, code, player_name, player_description, %s
                from game_private.story_locations
                where story_version_id = %s and code = %s
                on conflict do nothing
                returning location_code
                """,
                (session_id, round_no, story_version_id, location_code),
            )
            if await cur.fetchone():
                changed = True

        state_updates = _as_dict(payload.get('state_updates'))
        for key in ('phase', 'detective_mode'):
            if payload.get(key) is not None:
                state_updates.setdefault(key, payload[key])
        for key, value in state_updates.items():
            if state.get(key) != value:
                state[key] = value
                changed = True

        broadcast_facts: list[str] = []
        public_fact = payload.get('public_fact')
        if isinstance(public_fact, str) and public_fact.strip():
            broadcast_facts.append(public_fact.strip())
        broadcast = payload.get('broadcast_fact')
        if isinstance(broadcast, str) and broadcast.strip():
            broadcast_facts.append(broadcast.strip())
        broadcast_facts.extend(
            str(item).strip() for item in _as_list(payload.get('broadcast_facts'))
            if str(item).strip()
        )
        for fact in broadcast_facts:
            for character in characters.values():
                if await _append_known_fact(cur, session_id, str(character['id']), fact):
                    changed = True

        for character_code, raw_facts in _as_dict(payload.get('character_facts')).items():
            character = characters.get(str(character_code))
            if character is None:
                continue
            facts = [raw_facts] if isinstance(raw_facts, str) else _as_list(raw_facts)
            for fact in facts:
                if await _append_known_fact(
                    cur, session_id, str(character['id']), str(fact).strip()
                ):
                    changed = True

        for delta in _as_list(payload.get('social_deltas')):
            item = _as_dict(delta)
            actor = characters.get(str(item.get('actor') or ''))
            target = characters.get(str(item.get('target') or ''))
            if actor is None or target is None or not hasattr(service, '_apply_social_delta'):
                continue
            service._apply_social_delta(
                state,
                str(actor['id']),
                str(target['id']),
                relationship_delta=int(item.get('relationship', 0)),
                suspicion_delta=int(item.get('suspicion', 0)),
                reason=str(item.get('reason') or event['player_text'] or code)[:140],
            )
            changed = True

        world_changes = [str(item) for item in _as_list(state.get('world_changes'))]
        if code not in world_changes:
            world_changes.append(code)
            state['world_changes'] = world_changes

        await service._insert_internal_event(
            cur,
            session,
            'story_scripted_event',
            payload={
                'event_code': code,
                'event_type': event['event_type'],
                'round': round_no,
                'payload': payload,
            },
        )
        fired_now.append(code)

        text = str(event['player_text'] or '').strip()
        announce = bool(payload.get('always_announce')) or changed
        if text and announce and turn_id is not None:
            await service._insert_message(
                cur,
                session_id,
                turn_id,
                'narrator',
                None,
                'system',
                text,
            )
            for character in characters.values():
                await service._remember(
                    cur,
                    session_id,
                    str(character['id']),
                    turn_id,
                    'scripted_event',
                    text,
                    f'story-event:{code}',
                    salience=95,
                )

    return fired_now
