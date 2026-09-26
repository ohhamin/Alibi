from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from fastapi import HTTPException
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .db import pool
from .game_service import GameService, _as_dict, _as_list
from .story_events import run_story_events
from .schemas import FinalVoteRequest, StartSessionRequest


class EnhancedGameService(GameService):
    """Game rules layered on top of the core turn/evidence engine."""

    mandatory_submission_rounds = {2, 5}

    async def start_session(
        self,
        user_id: str,
        request: StartSessionRequest,
    ) -> dict[str, Any]:
        result = await super().start_session(user_id, request)
        session = result.get('session') or {}
        session_id = str(session.get('id') or '')
        if not session_id:
            return result

        async with pool.connection() as conn:
            async with conn.transaction():
                async with conn.cursor(row_factory=dict_row) as cur:
                    await cur.execute(
                        "select story_version_id, player_character_id, public_state "
                        "from public.game_sessions where id = %s",
                        (session_id,),
                    )
                    row = await cur.fetchone()
                    if row:
                        state = deepcopy(_as_dict(row['public_state']))
                        await self._ensure_social_state(
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
                            (Jsonb(state), session_id),
                        )
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

    async def get_session_state(
        self,
        user_id: str,
        session_id: str,
    ) -> dict[str, Any]:
        result = await super().get_session_state(user_id, session_id)
        session = result.get('session') or {}
        state = deepcopy(_as_dict(session.get('public_state')))
        current_round = int(session.get('current_turn') or 1)
        changed = False

        if (
            current_round not in self.mandatory_submission_rounds
            and _as_dict(state.get('pending_evidence_submission'))
        ):
            state['pending_evidence_submission'] = None
            state['round_submission_done_round'] = current_round
            changed = True

        async with pool.connection() as conn:
            async with conn.transaction():
                async with conn.cursor(row_factory=dict_row) as cur:
                    before = deepcopy(_as_dict(state.get('social_state')))
                    await self._ensure_social_state(
                        cur,
                        session['story_version_id'],
                        state,
                    )
                    if before != _as_dict(state.get('social_state')):
                        changed = True
                    if changed:
                        await cur.execute(
                            """
                            update public.game_sessions
                            set public_state = %s, updated_at = now()
                            where id = %s and user_id = %s
                            """,
                            (Jsonb(state), session_id, user_id),
                        )
                        await cur.execute(
                            """
                            update game_private.session_runtime
                            set state = %s, state_version = state_version + 1, updated_at = now()
                            where session_id = %s
                            """,
                            (Jsonb(state), session_id),
                        )

        session['public_state'] = state
        result['social_state'] = _as_dict(state.get('social_state'))
        result['pending_evidence_submission'] = state.get('pending_evidence_submission')
        result['pending_final_vote'] = state.get('pending_final_vote')
        result['suspect_final_votes'] = _as_list(state.get('suspect_final_votes'))
        result['player_outcome'] = state.get('player_outcome')

        player_id = str(session.get('player_character_id') or '')
        social = _as_dict(state.get('social_state'))
        for dossier in result.get('character_dossiers') or []:
            character_id = str(dossier.get('id') or '')
            if not character_id or character_id == player_id:
                continue
            attitude = _as_dict(_as_dict(social.get(character_id)).get(player_id))
            dossier['relationship_to_player'] = int(attitude.get('relationship', 0))
            dossier['suspicion_of_player'] = int(attitude.get('suspicion', 25))
        return result

    async def _ensure_social_state(self, cur, story_version_id, state) -> None:
        await cur.execute(
            """
            select id, display_name
            from public.story_characters
            where story_version_id = %s and is_player_selectable = true
            order by sort_order
            """,
            (story_version_id,),
        )
        suspects = list(await cur.fetchall())
        social = deepcopy(_as_dict(state.get('social_state')))
        for actor in suspects:
            actor_id = str(actor['id'])
            actor_map = deepcopy(_as_dict(social.get(actor_id)))
            for target in suspects:
                target_id = str(target['id'])
                if actor_id == target_id:
                    continue
                entry = deepcopy(_as_dict(actor_map.get(target_id)))
                entry.setdefault('relationship', 0)
                entry.setdefault('suspicion', 25)
                entry.setdefault('reasons', [])
                actor_map[target_id] = entry
            social[actor_id] = actor_map
        state['social_state'] = social

    def _apply_social_delta(
        self,
        state: dict[str, Any],
        actor_id: str,
        target_id: str,
        *,
        relationship_delta: int = 0,
        suspicion_delta: int = 0,
        reason: str = '',
    ) -> None:
        if not actor_id or not target_id or actor_id == target_id:
            return
        social = deepcopy(_as_dict(state.get('social_state')))
        actor_map = deepcopy(_as_dict(social.get(actor_id)))
        entry = deepcopy(_as_dict(actor_map.get(target_id)))
        relationship = int(entry.get('relationship', 0)) + relationship_delta
        suspicion = int(entry.get('suspicion', 25)) + suspicion_delta
        entry['relationship'] = max(-100, min(100, relationship))
        entry['suspicion'] = max(0, min(100, suspicion))
        reasons = [str(x) for x in _as_list(entry.get('reasons')) if str(x).strip()]
        if reason and reason not in reasons:
            reasons.append(reason)
        entry['reasons'] = reasons[-5:]
        actor_map[target_id] = entry
        social[actor_id] = actor_map
        state['social_state'] = social

    def _dialogue_deltas(self, text: str) -> tuple[int, int]:
        normalized = text.replace(' ', '')
        helpful = ('맞', '봤', '기억해', '기억합', '확실', '도움', '동의')
        evasive = ('모르', '기억나지', '기억안', '단정', '확실하지', '못봤', '못 봤')
        if any(token in normalized for token in helpful):
            return 3, -4
        if any(token.replace(' ', '') in normalized for token in evasive):
            return -2, 4
        return 1, 0

    def _question_fingerprint(self, question: str) -> str:
        text = question.lower().strip()
        times = re.findall(r'(\d{1,2})\s*시(?:\s*(\d{1,2})\s*분)?', text)
        if times and any(token in text for token in ('봤', '보셨', '기억', '있었', '동선')):
            hour, minute = times[0]
            return f"time-alibi:{int(hour):02d}:{int(minute or 0):02d}"
        compact = re.sub(r'[^0-9a-z가-힣]+', '', text)
        for token in ('혹시', '제가', '저를', '당신', '정말', '기억', '나요', '나요?', '죠'):
            compact = compact.replace(token, '')
        return compact[:80]

    async def _dedupe_npc_question(
        self,
        cur,
        session,
        actor,
        target,
        question: str,
    ) -> tuple[str, str]:
        question = question.strip()
        fingerprint = self._question_fingerprint(question)
        if not fingerprint:
            return question, fingerprint
        await cur.execute(
            """
            select payload->>'question' as question,
                   payload->>'fingerprint' as fingerprint
            from game_private.internal_events
            where session_id = %s
              and event_type = 'npc_question_record'
              and actor_character_id = %s
              and target_character_id = %s
            order by created_at desc
            limit 12
            """,
            (session['id'], actor['id'], target['id']),
        )
        rows = list(await cur.fetchall())
        duplicate = any(
            str(row.get('fingerprint') or '') == fingerprint
            or self._question_fingerprint(str(row.get('question') or '')) == fingerprint
            for row in rows
        )
        if not duplicate:
            return question, fingerprint

        alternatives = [
            '제 동선 얘기는 여기까지 할게요. 공개된 증거 중 제게 불리하게 보일 만한 게 있다면 무엇인지 말해줄래요?',
            '제가 제출할 증거를 고른다면 제 입장을 가장 잘 설명해 줄 자료가 뭐라고 생각해요?',
            '아까 이야기와 겹치지 않게 묻겠습니다. 지금까지 나온 것 중 제 설명과 가장 충돌한다고 느낀 부분이 있나요?',
        ]
        used = {str(row.get('question') or '').strip() for row in rows}
        replacement = next((item for item in alternatives if item not in used), alternatives[-1])
        return replacement, self._question_fingerprint(replacement)

    async def _npc_talk(
        self,
        cur,
        session,
        turn,
        state,
        actor,
        target,
        location_code: str,
        intent: str,
        question: str | None = None,
    ) -> None:
        await self._ensure_social_state(cur, session['story_version_id'], state)
        actual = question or f"{intent} 제 입장을 확인하는 데 도움이 될 만한 기억이 있나요?"
        actual, fingerprint = await self._dedupe_npc_question(
            cur, session, actor, target, actual
        )
        await super()._npc_talk(
            cur,
            session,
            turn,
            state,
            actor,
            target,
            location_code,
            intent,
            question=actual,
        )
        await cur.execute(
            """
            select payload->>'reply' as reply
            from game_private.internal_events
            where session_id = %s
              and event_type = 'npc_talk'
              and actor_character_id = %s
              and target_character_id = %s
            order by created_at desc
            limit 1
            """,
            (session['id'], actor['id'], target['id']),
        )
        event = await cur.fetchone()
        reply = str(event.get('reply') or '') if event else ''
        rel_delta, suspicion_delta = self._dialogue_deltas(reply)
        actor_id = str(actor['id'])
        target_id = str(target['id'])
        self._apply_social_delta(
            state,
            actor_id,
            target_id,
            relationship_delta=rel_delta,
            suspicion_delta=suspicion_delta,
            reason=f"대화: {actual[:70]}",
        )
        if any(token in actual for token in ('의심', '수상', '거짓', '숨기', '왜')):
            self._apply_social_delta(
                state,
                target_id,
                actor_id,
                relationship_delta=-2,
                suspicion_delta=3,
                reason=f"공격적인 질문을 받음: {actual[:60]}",
            )
        else:
            self._apply_social_delta(
                state,
                target_id,
                actor_id,
                relationship_delta=1,
                reason='직접 대화를 나눔',
            )
        await self._insert_internal_event(
            cur,
            session,
            'npc_question_record',
            actor_character_id=actor['id'],
            target_character_id=target['id'],
            payload={'question': actual, 'fingerprint': fingerprint},
        )

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

    async def _continue_conversation(
        self,
        cur,
        session,
        turn,
        state,
        request,
        client_action_id: str,
        conversation: dict[str, Any],
    ) -> bool:
        ended = await super()._continue_conversation(
            cur,
            session,
            turn,
            state,
            request,
            client_action_id,
            conversation,
        )
        actor_id = str(conversation.get('actor_id') or '')
        player_id = str(session.get('player_character_id') or '')
        if actor_id and player_id:
            await cur.execute(
                "select role_label from public.story_characters where id = %s",
                (actor_id,),
            )
            actor_meta = await cur.fetchone()
            if actor_meta and actor_meta['role_label'] != '탐정':
                text = str(request.input_text or '')
                rel_delta, suspicion_delta = self._dialogue_deltas(text)
                self._apply_social_delta(
                    state,
                    actor_id,
                    player_id,
                    relationship_delta=rel_delta,
                    suspicion_delta=suspicion_delta,
                    reason=f"플레이어와 대화: {text[:70]}",
                )
        return ended

    async def _publish_evidence(
        self,
        cur,
        session,
        turn,
        state,
        clue_code: str,
        holder_character_id: str,
        *,
        opinion: str = '',
        source: str = 'round_submission',
    ):
        clue = await super()._publish_evidence(
            cur,
            session,
            turn,
            state,
            clue_code,
            holder_character_id,
            opinion=opinion,
            source=source,
        )
        if clue is None:
            return None
        await run_story_events(self, cur, session, turn, state)
        await self._ensure_social_state(cur, session['story_version_id'], state)
        await cur.execute(
            "select metadata from game_private.story_clues "
            "where story_version_id = %s and code = %s",
            (session['story_version_id'], clue_code),
        )
        row = await cur.fetchone()
        metadata = _as_dict(row['metadata']) if row else {}
        suspect_code = str(metadata.get('suspect_code') or '')
        alibi_code = str(metadata.get('supports_alibi_for') or '')
        if not suspect_code and not alibi_code:
            return clue

        await cur.execute(
            """
            select id, code, display_name
            from public.story_characters
            where story_version_id = %s and is_player_selectable = true
            order by sort_order
            """,
            (session['story_version_id'],),
        )
        suspects = list(await cur.fetchall())
        target = next(
            (
                item for item in suspects
                if str(item['code']) == (suspect_code or alibi_code)
            ),
            None,
        )
        if target is None:
            return clue
        target_id = str(target['id'])
        for observer in suspects:
            observer_id = str(observer['id'])
            if observer_id == target_id:
                continue
            if suspect_code:
                self._apply_social_delta(
                    state,
                    observer_id,
                    target_id,
                    relationship_delta=-4,
                    suspicion_delta=16,
                    reason=f"공개 증거 '{clue['player_title']}'이(가) {target['display_name']}에게 불리함",
                )
            else:
                self._apply_social_delta(
                    state,
                    observer_id,
                    target_id,
                    relationship_delta=2,
                    suspicion_delta=-12,
                    reason=f"공개 증거 '{clue['player_title']}'이(가) {target['display_name']}의 알리바이를 보강함",
                )
        return clue

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
            metadata = _as_dict(clue['metadata'])
            supports_self = str(metadata.get('supports_alibi_for') or '') == str(suspect['code'])
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
                where session_id = %s and holder_character_id = %s and status = 'held'
                """,
                (session['id'], player_id),
            )
            held_count = int((await cur.fetchone())['cnt'])
            if held_count > 0:
                if not _as_dict(state.get('pending_evidence_submission')):
                    state['pending_evidence_submission'] = {
                        'round': current_round,
                        'required': True,
                        'context': 'detective_interrogation',
                        'message': '탐정의 비공개 취조가 시작되기 전, 소지한 증거 중 1개를 제출해야 합니다.',
                    }
                    await self._insert_message(
                        cur,
                        session['id'],
                        turn['id'],
                        'system',
                        None,
                        'system',
                        '탐정 취조 전 증거 제출: 소지한 증거 중 1개를 탐정에게 제출하세요. 제출한 증거와 의견은 모두에게 공개됩니다. 나머지 증거는 계속 비공개로 보유할 수 있습니다.',
                    )
                return False
        state['round_submission_done_round'] = current_round
        state['pending_evidence_submission'] = None
        return True

    async def _prepare_final_votes(self, cur, session, turn, state) -> bool:
        await self._ensure_social_state(cur, session['story_version_id'], state)
        await cur.execute(
            """
            select id, code, display_name
            from public.story_characters
            where story_version_id = %s and is_player_selectable = true
            order by sort_order
            """,
            (session['story_version_id'],),
        )
        suspects = list(await cur.fetchall())
        player_id = str(session.get('player_character_id') or '')
        existing = {
            str(item.get('voter_character_id')): item
            for item in _as_list(state.get('suspect_final_votes'))
            if isinstance(item, dict) and item.get('voter_character_id')
        }
        social = _as_dict(state.get('social_state'))

        for voter in suspects:
            voter_id = str(voter['id'])
            if voter_id == player_id or voter_id in existing:
                continue
            candidate_rows = [item for item in suspects if str(item['id']) != voter_id]
            if not candidate_rows:
                continue
            attitude_map = _as_dict(social.get(voter_id))
            scored: list[tuple[int, int, dict[str, Any]]] = []
            for index, candidate in enumerate(candidate_rows):
                candidate_id = str(candidate['id'])
                attitude = _as_dict(attitude_map.get(candidate_id))
                score = int(attitude.get('suspicion', 25)) - int(attitude.get('relationship', 0)) // 5
                await cur.execute(
                    """
                    select count(*) as cnt
                    from game_private.agent_memories
                    where session_id = %s and character_id = %s and content ilike %s
                    """,
                    (session['id'], voter_id, f"%{candidate['display_name']}%"),
                )
                score += min(20, int((await cur.fetchone())['cnt']) * 2)
                scored.append((score, -index, candidate))
            scored.sort(reverse=True, key=lambda item: (item[0], item[1]))
            accused = scored[0][2]
            accused_id = str(accused['id'])
            accused_name = str(accused['display_name'])
            attitude = _as_dict(attitude_map.get(accused_id))

            await cur.execute(
                """
                select left(content, 220) as content
                from game_private.agent_memories
                where session_id = %s and character_id = %s
                  and content ilike %s
                  and memory_type not in ('private_evidence', 'clue')
                order by salience desc, created_at desc
                limit 2
                """,
                (session['id'], voter_id, f"%{accused_name}%"),
            )
            supports = [str(row['content']).strip() for row in await cur.fetchall() if str(row['content']).strip()]
            if supports:
                reason = f"{accused_name}을(를) 가장 의심합니다. " + ' '.join(supports)
            else:
                reason = (
                    f"{accused_name}에 대한 제 의심도가 가장 높습니다. "
                    f"지금까지의 대화와 행동을 종합하면 의심도는 {int(attitude.get('suspicion', 25))}/100 정도입니다."
                )

            await cur.execute(
                """
                select h.clue_code, c.player_title, c.player_text
                from game_private.session_evidence_holdings h
                join game_private.story_clues c
                  on c.story_version_id = %s and c.code = h.clue_code
                where h.session_id = %s
                  and h.holder_character_id = %s
                  and h.status = 'held'
                  and c.metadata->>'suspect_code' = %s
                order by h.acquired_at
                limit 1
                """,
                (session['story_version_id'], session['id'], voter_id, accused['code']),
            )
            evidence = await cur.fetchone()
            existing[voter_id] = {
                'voter_character_id': voter_id,
                'voter_name': voter['display_name'],
                'accused_character_id': accused_id,
                'accused_name': accused_name,
                'reasoning': reason[:700],
                'suggested_evidence': (
                    {
                        'clue_code': evidence['clue_code'],
                        'title': evidence['player_title'],
                        'content': evidence['player_text'],
                    }
                    if evidence else None
                ),
                'is_player': False,
            }

        ordered_votes = [existing[str(item['id'])] for item in suspects if str(item['id']) in existing]
        state['suspect_final_votes'] = ordered_votes
        if player_id and player_id not in existing:
            candidates = [
                {'id': str(item['id']), 'name': item['display_name'], 'code': item['code']}
                for item in suspects
                if str(item['id']) != player_id
            ]
            state['pending_final_vote'] = {
                'required': True,
                'message': '탐정의 최종 판단 전에 당신이 생각하는 범인과 이유를 제출하세요.',
                'candidates': candidates,
                'evidence_optional': True,
            }
            if not state.get('final_vote_prompted'):
                await self._insert_message(
                    cur,
                    session['id'],
                    turn['id'],
                    'system',
                    None,
                    'system',
                    '최종 의견 제출: 자신과 탐정을 제외한 용의자 중 예상 범인을 선택하고 이유를 적으세요. 남은 비공개 증거를 하나 제안할 수도 있습니다.',
                )
                state['final_vote_prompted'] = True
            return False

        state['pending_final_vote'] = None
        return True

    async def _advance_round(self, cur, session, turn, state) -> None:
        current_round = int(session['current_turn'])
        max_rounds = int(state.get('max_rounds', 6))
        if current_round < max_rounds:
            await super()._advance_round(cur, session, turn, state)
            await run_story_events(self, cur, session, turn, state)
            return

        if not await self._prepare_round_end_submissions(cur, session, turn, state):
            return
        if (
            current_round in {2, 5}
            and int(state.get('detective_interrogation_done_round', 0)) != current_round
        ):
            started = await self._run_private_detective_interrogations(cur, session, turn, state)
            if started:
                return
            state['detective_interrogation_done_round'] = current_round

        if not await self._prepare_final_votes(cur, session, turn, state):
            state['current_actor_id'] = None
            state['current_actor_name'] = '최종 의견 정리'
            return

        await cur.execute(
            "update public.game_turns set status = 'resolved', closed_at = now() where id = %s",
            (turn['id'],),
        )
        await self._resolve_detective_verdict(cur, session, turn, state)

    async def submit_final_vote(
        self,
        user_id: str,
        session_id: str,
        request: FinalVoteRequest,
    ) -> dict[str, Any]:
        lock = await self._session_advance_lock(session_id)
        async with lock:
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
                            return await self.get_session_state(user_id, session_id)
                        state = deepcopy(_as_dict(session['public_state']))
                        player_id = str(session.get('player_character_id') or '')
                        accused_id = str(request.culprit_character_id)
                        if not player_id or accused_id == player_id:
                            raise HTTPException(status_code=400, detail='자기 자신은 최종 예상 범인으로 선택할 수 없습니다.')
                        await cur.execute(
                            """
                            select id, display_name
                            from public.story_characters
                            where id = %s and story_version_id = %s and is_player_selectable = true
                            """,
                            (accused_id, session['story_version_id']),
                        )
                        accused = await cur.fetchone()
                        if accused is None:
                            raise HTTPException(status_code=400, detail='선택할 수 없는 인물입니다.')
                        await cur.execute(
                            "select display_name from public.story_characters where id = %s",
                            (player_id,),
                        )
                        player = await cur.fetchone()

                        suggested = None
                        if request.clue_code:
                            await cur.execute(
                                """
                                select h.clue_code, c.player_title, c.player_text
                                from game_private.session_evidence_holdings h
                                join game_private.story_clues c
                                  on c.story_version_id = %s and c.code = h.clue_code
                                where h.session_id = %s and h.holder_character_id = %s
                                  and h.status = 'held' and h.clue_code = %s
                                """,
                                (session['story_version_id'], session_id, player_id, request.clue_code),
                            )
                            evidence = await cur.fetchone()
                            if evidence is None:
                                raise HTTPException(status_code=400, detail='현재 소지 중인 비공개 증거만 제안할 수 있습니다.')
                            suggested = {
                                'clue_code': evidence['clue_code'],
                                'title': evidence['player_title'],
                                'content': evidence['player_text'],
                            }

                        votes = {
                            str(item.get('voter_character_id')): item
                            for item in _as_list(state.get('suspect_final_votes'))
                            if isinstance(item, dict) and item.get('voter_character_id')
                        }
                        votes[player_id] = {
                            'voter_character_id': player_id,
                            'voter_name': player['display_name'] if player else '플레이어',
                            'accused_character_id': accused_id,
                            'accused_name': accused['display_name'],
                            'reasoning': request.reasoning.strip(),
                            'suggested_evidence': suggested,
                            'is_player': True,
                        }
                        state['suspect_final_votes'] = list(votes.values())
                        state['pending_final_vote'] = None

                        await cur.execute(
                            """
                            select * from public.game_turns
                            where session_id = %s and turn_no = %s and status = 'open'
                            order by opened_at desc limit 1
                            """,
                            (session_id, session['current_turn']),
                        )
                        turn = await cur.fetchone()
                        if turn is None:
                            raise HTTPException(status_code=409, detail='최종 의견을 처리할 열린 라운드가 없습니다.')
                        await self._insert_message(
                            cur,
                            session_id,
                            turn['id'],
                            'player',
                            session['player_character_id'],
                            'dialogue',
                            f"최종 예상 범인은 {accused['display_name']}입니다. {request.reasoning.strip()}",
                        )
                        await self._advance_round(cur, session, turn, state)
                        await cur.execute(
                            """
                            update public.game_sessions
                            set public_state = %s, current_phase = %s,
                                last_saved_at = now(), updated_at = now()
                            where id = %s
                            """,
                            (Jsonb(state), session['current_phase'], session_id),
                        )
                        await cur.execute(
                            """
                            update game_private.session_runtime
                            set state = %s, state_version = state_version + 1, updated_at = now()
                            where session_id = %s
                            """,
                            (Jsonb(state), session_id),
                        )
        return await self.get_session_state(user_id, session_id)

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
            order by sc.sort_order limit 1
            """,
            (session['id'], session['story_version_id']),
        )
        detective = await cur.fetchone()
        if detective is None:
            raise HTTPException(status_code=500, detail='탐정 캐릭터가 없습니다.')
        await cur.execute(
            """
            select left(content, 800) as content
            from game_private.agent_memories
            where session_id = %s and character_id = %s
            order by salience desc, created_at desc limit 18
            """,
            (session['id'], detective['id']),
        )
        memories = [row['content'] for row in await cur.fetchall()]
        await cur.execute(
            """
            select id, code, display_name, role_label
            from public.story_characters
            where story_version_id = %s and is_player_selectable = true
            order by sort_order
            """,
            (session['story_version_id'],),
        )
        candidates = list(await cur.fetchall())
        votes = _as_list(state.get('suspect_final_votes'))

        vote_counts: dict[str, int] = {}
        for vote in votes:
            if isinstance(vote, dict):
                key = str(vote.get('accused_character_id') or '')
                if key:
                    vote_counts[key] = vote_counts.get(key, 0) + 1
        scored: list[tuple[int, int, dict[str, Any]]] = []
        evidence_text = [str(x) for x in [*_as_list(detective['known_facts']), *memories]]
        for index, candidate in enumerate(candidates):
            cid = str(candidate['id'])
            name = str(candidate['display_name'])
            evidence_mentions = sum(1 for item in evidence_text if name in item)
            score = evidence_mentions * 3 + vote_counts.get(cid, 0) * 2
            scored.append((score, -index, candidate))
        scored.sort(reverse=True, key=lambda item: (item[0], item[1]))
        fallback_accused = scored[0][2] if scored else None
        fallback = {
            'accused_character_id': str(fallback_accused['id']) if fallback_accused else None,
            'reasoning': (
                f"직접 확보한 증거와 진술, 그리고 용의자들의 최종 의견을 교차 검토한 결과 "
                f"{fallback_accused['display_name']}을(를) 가장 의심합니다."
                if fallback_accused else '현재 정보만으로는 최종 지목을 할 수 없습니다.'
            ),
        }
        instructions = f"""
당신은 탐정 '{detective['display_name']}'이다.
세계관: {detective['world_prompt']}
당신이 직접 확보한 증거와 진술을 최우선으로 사용해 최종 용의자 한 명을 지목한다.
용의자들의 최종 선택도 참고하되, 그것은 어디까지나 각자의 의견이며 사실로 취급하면 안 된다.
여러 용의자가 같은 사람을 지목했더라도 직접 증거와 모순되면 따르지 않는다.
각 용의자가 마지막에 제안한 비공개 증거가 있다면 그 내용은 최종 제보로 참고할 수 있다.
후보 목록 밖 인물을 선택하면 안 된다.
reasoning에는 구체적인 증거·시간·진술과 용의자 의견을 어떻게 평가했는지 2~4문장으로 설명한다.
반드시 JSON 객체 하나만 출력한다.
{{"accused_character_id":"후보 id","reasoning":"최종 판단 근거"}}
""".strip()
        payload = {
            'known_facts': _as_list(detective['known_facts']),
            'memories': memories,
            'suspect_final_votes': votes,
            'candidates': candidates,
        }
        verdict = await self.agent_service._json_response(
            instructions,
            __import__('json').dumps(payload, ensure_ascii=False, default=str),
            fallback,
        )
        valid_ids = {str(row['id']) for row in candidates}
        accused_id = str(verdict.get('accused_character_id') or '')
        if accused_id not in valid_ids and fallback_accused:
            accused_id = str(fallback_accused['id'])
        accused = next((row for row in candidates if str(row['id']) == accused_id), None)

        await cur.execute(
            "select culprit_character_id from game_private.story_solutions where story_version_id = %s",
            (session['story_version_id'],),
        )
        solution = await cur.fetchone()
        culprit_id = str(solution['culprit_character_id']) if solution and solution['culprit_character_id'] else ''
        caught = accused_id == culprit_id
        player_id = str(session.get('player_character_id') or '')
        player_is_culprit = player_id == culprit_id
        if player_is_culprit:
            ending_code = 'culprit-caught' if caught else 'culprit-escape'
        else:
            ending_code = 'suspect-innocent-win' if caught else 'suspect-innocent-fail'

        reasoning = str(verdict.get('reasoning') or '').strip()
        accused_name = accused['display_name'] if accused else '알 수 없는 인물'
        state['detective_verdict'] = {
            'detective_name': detective['display_name'],
            'accused_character_id': accused_id,
            'accused_name': accused_name,
            'reasoning': reasoning,
            'considered_suspect_votes': True,
        }
        success = accused_id != player_id
        state['player_outcome'] = {
            'success': success,
            'label': '성공' if success else '실패',
            'message': (
                '탐정의 최종 지목에서 벗어났습니다.'
                if success else '탐정이 당신을 최종 범인으로 지목했습니다.'
            ),
        }
        state['pending_final_vote'] = None
        await self._insert_message(
            cur,
            session['id'],
            turn['id'],
            'character',
            detective['id'],
            'dialogue',
            f"최종 지목은 {accused_name}입니다. {reasoning}".strip(),
        )
        await cur.execute(
            """
            select title, ending_text
            from game_private.story_endings
            where story_version_id = %s and code = %s
            """,
            (session['story_version_id'], ending_code),
        )
        ending = await cur.fetchone()
        if ending:
            await self._insert_message(
                cur,
                session['id'],
                turn['id'],
                'narrator',
                None,
                'narration',
                f"{ending['title']}\n{ending['ending_text']}",
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
        state['current_actor_id'] = None
        state['current_actor_name'] = None
