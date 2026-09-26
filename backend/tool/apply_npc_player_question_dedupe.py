from pathlib import Path

path = Path(__file__).resolve().parents[1] / 'app' / 'game_service.py'
text = path.read_text()

old = '''                if target_id == str(session['player_character_id']):
                    question = str(choice.get('question') or '').strip()
                    if not question:
                        question = f"{intent} 지금 네가 아는 걸 말해줄래?"
                    await self._insert_internal_event(
                        cur, session, 'npc_asks_player',
'''
new = '''                if target_id == str(session['player_character_id']):
                    question = str(choice.get('question') or '').strip()
                    if not question:
                        question = f"{intent} 지금 네가 아는 걸 말해줄래?"

                    # Guard against the model asking the player the same alibi
                    # question over and over with only superficial wording changes.
                    await cur.execute(
                        """
                        select payload->>'question' as question
                        from game_private.internal_events
                        where session_id = %s
                          and event_type = 'npc_asks_player'
                          and actor_character_id = %s
                          and target_character_id = %s
                        order by created_at desc
                        limit 12
                        """,
                        (session['id'], actor['id'], target_id),
                    )
                    previous_questions = [
                        str(row.get('question') or '').strip()
                        for row in await cur.fetchall()
                        if str(row.get('question') or '').strip()
                    ]

                    def topic_key(value: str) -> str:
                        compact = ''.join(value.lower().split())
                        digits = ''.join(ch if ch.isdigit() else ' ' for ch in compact).split()
                        if ('시' in compact or '분' in compact) and any(
                            token in compact
                            for token in ('봤', '보셨', '기억', '있었', '동선', '목격')
                        ):
                            return 'time-alibi:' + ':'.join(digits[:2])
                        for token in (
                            '혹시', '제가', '저를', '당신', '정말', '기억나',
                            '기억합', '나요', '습니까', '보셨', '봤', '죠', '?', '.', ',',
                        ):
                            compact = compact.replace(token, '')
                        return compact[:80]

                    key = topic_key(question)
                    if key and any(topic_key(item) == key for item in previous_questions):
                        alternatives = [
                            '그 시간대 얘기는 이미 물었으니 다른 걸 묻겠습니다. 지금까지 공개된 증거 중 제 설명과 가장 충돌하는 게 뭐라고 생각해요?',
                            '같은 알리바이 확인은 반복하지 않을게요. 제가 아직 해명하지 못한 행동이나 증거가 있다면 무엇인지 말해줄래요?',
                            '제 동선 확인 말고 묻겠습니다. 지금 가장 의심하는 사람은 누구고, 그렇게 생각한 근거가 있나요?',
                        ]
                        used = {item.strip() for item in previous_questions}
                        question = next(
                            (item for item in alternatives if item not in used),
                            alternatives[-1],
                        )

                    await self._insert_internal_event(
                        cur, session, 'npc_asks_player',
'''
if new in text:
    print('already patched')
elif old not in text:
    raise SystemExit('missing NPC player question anchor')
else:
    text = text.replace(old, new, 1)
    path.write_text(text)
    print('patched', path)
