from pathlib import Path

root = Path(__file__).resolve().parents[2]


def replace_once(path: str, old: str, new: str, label: str) -> None:
    p = root / path
    text = p.read_text()
    if new in text:
        return
    if old not in text:
        raise SystemExit(f'missing patch anchor: {label}')
    p.write_text(text.replace(old, new, 1))


replace_once(
    'mobile/lib/screens/game_screen.dart',
    """  int get _movementRemaining =>
      (_publicState['movement_remaining'] as num?)?.toInt() ?? 0;
  int get _actionsRemaining =>
      (_publicState['actions_remaining'] as num?)?.toInt() ?? 0;
""",
    """  int get _movementRemaining {
    final raw = (_publicState['movement_remaining'] as num?)?.toInt() ?? 0;
    if (_isPlayerTurn && raw <= 0 && _actionsRemaining > 0) return 1;
    return raw;
  }

  int get _actionsRemaining {
    final raw = (_publicState['actions_remaining'] as num?)?.toInt() ?? 0;
    if (_isPlayerTurn && raw <= 0) {
      final roundActions = (_publicState['round_actor_actions'] as Map?) ?? const {};
      final completed = (roundActions[_playerCharacterId] as num?)?.toInt() ?? 0;
      if (completed < 2) return 2 - completed;
    }
    return raw;
  }
""",
    'mobile turn counters',
)

replace_once(
    'mobile/lib/screens/game_screen.dart',
    """  bool _startsAction(Map<String, dynamic> message, bool inDialogue) {
    final speakerType = message['speaker_type'] as String? ?? 'system';
    final kind = message['message_kind'] as String? ?? '';
    if (kind == 'dialogue') return !inDialogue;
    if (speakerType == 'player' || speakerType == 'character') {
      return kind == 'choice_result' || kind == 'npc_action';
    }
    return false;
  }
""",
    """  bool _startsAction(Map<String, dynamic> message, bool inDialogue) {
    final speakerType = message['speaker_type'] as String? ?? 'system';
    final kind = message['message_kind'] as String? ?? '';
    final content = message['content'] as String? ?? '';
    if (kind == 'dialogue') return !inDialogue;
    if (speakerType == 'player' || speakerType == 'character') {
      return kind == 'choice_result' || kind == 'npc_action';
    }
    if (speakerType == 'system' &&
        (content.startsWith('[공개 증거] 탐정이') ||
         content.contains('탐정이 추가 수사') ||
         content.contains('탐정이 공개 질문'))) {
      return true;
    }
    return false;
  }
""",
    'timeline detective divider',
)

replace_once(
    'backend/app/game_service.py',
    """        state['current_actor_id'] = actor_id
        state['current_actor_name'] = _as_dict(turn_info).get('name')

    async def _run_single_npc_turn(self, cur, session, turn, state, actor_id: str) -> None:
""",
    """        state['current_actor_id'] = actor_id
        state['current_actor_name'] = _as_dict(turn_info).get('name')
        if actor_id == str(session.get('player_character_id') or ''):
            counts = _as_dict(state.get('round_actor_actions'))
            completed = int(counts.get(actor_id, 0) or 0)
            remaining = max(0, 2 - completed)
            state['actions_remaining'] = remaining
            state['movement_remaining'] = 1 if remaining > 0 else 0

    async def _run_single_npc_turn(self, cur, session, turn, state, actor_id: str) -> None:
""",
    'backend preview counters',
)

replace_once(
    'backend/app/agent_service.py',
    """        fallback = {
            'reply': self._fallback_reply(agent),
            'end_conversation': ctx.exchange_no >= ctx.max_exchanges,
        }
""",
    """        if ctx.presented_item:
            item_title = str(ctx.presented_item.get('title') or ctx.presented_item.get('name') or '이 증거')
            fallback_reply = (
                f\"'{item_title}'은 확인했습니다. 이 증거가 직접 보여주는 사실을 \"
                '기존 진술과 시간대에 맞춰 비교해보겠습니다.'
            )
        else:
            fallback_reply = self._fallback_reply(agent)
        fallback = {
            'reply': fallback_reply,
            'end_conversation': ctx.exchange_no >= ctx.max_exchanges,
        }
""",
    'conversation fallback evidence',
)

replace_once(
    'backend/app/agent_service.py',
    """            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                reply = str(parsed.get('reply') or '').strip()
                if reply:
                    return {
                        'reply': reply,
                        'end_conversation': bool(parsed.get('end_conversation'))
                        or ctx.exchange_no >= ctx.max_exchanges,
                    }
        except (OpenAIError, json.JSONDecodeError, TypeError, ValueError):
            logger.warning('OpenAI conversation response failed; using fallback')
        return fallback
""",
    """            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict):
                reply = str(parsed.get('reply') or '').strip()
                if reply:
                    return {
                        'reply': reply,
                        'end_conversation': bool(parsed.get('end_conversation'))
                        or ctx.exchange_no >= ctx.max_exchanges,
                    }
            plain = raw.strip().strip('`').strip()
            if plain and not plain.startswith('{'):
                return {
                    'reply': plain[:700],
                    'end_conversation': ctx.exchange_no >= ctx.max_exchanges,
                }
        except (OpenAIError, TypeError, ValueError) as exc:
            logger.warning('OpenAI conversation response failed; using fallback: %s', exc)
        return fallback
""",
    'conversation tolerant parsing',
)

print('patched turn reset, detective divider, and dialogue fallback')
