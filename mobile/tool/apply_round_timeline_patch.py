from pathlib import Path

root = Path(__file__).resolve().parents[2]
mobile_path = root / 'mobile' / 'lib' / 'screens' / 'game_screen.dart'
backend_path = root / 'backend' / 'app' / 'game_service.py'


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old in text:
        return text.replace(old, new, 1)
    if new in text:
        return text
    raise SystemExit(f'patch anchor not found: {label}')


# --- Mobile: readable timeline -------------------------------------------------
text = mobile_path.read_text()

old_timeline = r'''  List<Map<String, dynamic>> _timelineEntries() {
    final entries = <Map<String, dynamic>>[];
    String? previousTurnId;
    var roundNo = 0;

    for (final message in widget.messages) {
      final turnId = '${message['turn_id'] ?? ''}';
      if (roundNo == 0 || turnId != previousTurnId) {
        roundNo += 1;
        entries.add(<String, dynamic>{
          '_type': 'round_header',
          'round_no': roundNo,
        });
        previousTurnId = turnId;
      }
      entries.add(message);
    }
    return entries;
  }
'''
new_timeline = r'''  bool _startsAction(Map<String, dynamic> message, bool inDialogue) {
    final speakerType = message['speaker_type'] as String? ?? 'system';
    final kind = message['message_kind'] as String? ?? '';
    if (kind == 'dialogue') return !inDialogue;
    if (speakerType == 'player' || speakerType == 'character') {
      return kind == 'choice_result' || kind == 'npc_action';
    }
    return false;
  }

  List<Map<String, dynamic>> _timelineEntries() {
    final entries = <Map<String, dynamic>>[];
    String? previousTurnId;
    var roundNo = 0;
    var hasAction = false;
    var inDialogue = false;

    for (final message in widget.messages) {
      final turnId = '${message['turn_id'] ?? ''}';
      if (roundNo == 0 || turnId != previousTurnId) {
        roundNo += 1;
        entries.add(<String, dynamic>{
          '_type': 'round_header',
          'round_no': roundNo,
        });
        previousTurnId = turnId;
        hasAction = false;
        inDialogue = false;
      }

      final kind = message['message_kind'] as String? ?? '';
      final startsAction = _startsAction(message, inDialogue);
      if (startsAction && hasAction) {
        entries.add(const <String, dynamic>{'_type': 'action_divider'});
      }
      if (startsAction) hasAction = true;
      entries.add(message);

      if (kind == 'dialogue') {
        inDialogue = true;
      } else if ((message['speaker_type'] as String?) == 'player' ||
          (message['speaker_type'] as String?) == 'character' ||
          (message['speaker_type'] as String?) == 'system') {
        inDialogue = false;
      }
    }
    return entries;
  }
'''
text = replace_once(text, old_timeline, new_timeline, 'timeline grouping')

message_anchor = "  Widget _message(BuildContext context, Map<String, dynamic> item) {\n"
action_divider = r'''  Widget _actionDivider() {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 10),
      child: LayoutBuilder(
        builder: (context, constraints) {
          const dashWidth = 5.0;
          const gap = 5.0;
          final count = (constraints.maxWidth / (dashWidth + gap)).floor();
          return Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: List.generate(
              count,
              (_) => Container(
                width: dashWidth,
                height: 1,
                color: const Color(0xFF393D45),
              ),
            ),
          );
        },
      ),
    );
  }

'''
if action_divider not in text:
    if message_anchor not in text:
        raise SystemExit('patch anchor not found: message renderer')
    text = text.replace(message_anchor, action_divider + message_anchor, 1)

old_message_head = r'''  Widget _message(BuildContext context, Map<String, dynamic> item) {
    final type = item['speaker_type'] as String? ?? 'system';
    final isPlayer = type == 'player';
    final isNarration = type == 'narrator' || type == 'system';
    final speaker = item['speaker_name'] as String? ??
        (type == 'narrator'
            ? '게임 마스터'
            : type == 'system'
                ? '시스템'
                : '나');

    if (isNarration) {
'''
new_message_head = r'''  Widget _message(BuildContext context, Map<String, dynamic> item) {
    final type = item['speaker_type'] as String? ?? 'system';
    final isPlayer = type == 'player';
    final isNarration = type == 'narrator';

    if (type == 'system') {
      return Padding(
        padding: const EdgeInsets.symmetric(vertical: 7),
        child: Container(
          width: double.infinity,
          padding: const EdgeInsets.fromLTRB(13, 11, 13, 11),
          decoration: BoxDecoration(
            color: AppTheme.brass.withValues(alpha: .07),
            borderRadius: BorderRadius.circular(10),
            border: Border.all(
              color: AppTheme.brass.withValues(alpha: .24),
            ),
          ),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Icon(
                Icons.campaign_outlined,
                size: 17,
                color: AppTheme.brass,
              ),
              const SizedBox(width: 9),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'SYSTEM',
                      style: Theme.of(context).textTheme.labelSmall?.copyWith(
                            color: AppTheme.brass,
                            fontWeight: FontWeight.w800,
                            letterSpacing: 1.1,
                          ),
                    ),
                    const SizedBox(height: 3),
                    Text(item['content'] as String? ?? ''),
                  ],
                ),
              ),
            ],
          ),
        ),
      );
    }

    final speaker = item['speaker_name'] as String? ??
        (type == 'narrator' ? '게임 마스터' : '나');

    if (isNarration) {
'''
text = replace_once(text, old_message_head, new_message_head, 'system notice style')

old_builder = r'''        if (entry['_type'] == 'round_header') {
          return _roundHeader(context, entry['round_no'] as int);
        }
        return _message(context, entry);
'''
new_builder = r'''        if (entry['_type'] == 'round_header') {
          return _roundHeader(context, entry['round_no'] as int);
        }
        if (entry['_type'] == 'action_divider') {
          return _actionDivider();
        }
        return _message(context, entry);
'''
text = replace_once(text, old_builder, new_builder, 'action divider rendering')
mobile_path.write_text(text)


# --- Backend: preserve the NPC as the visible speaker --------------------------
text = backend_path.read_text()
backend_replacements = [
    (
        """            if player_location in {origin_code, move_to}:\n                await self._insert_message(\n                    cur, session['id'], turn['id'], 'narrator', None, 'narration', exact_move\n                )\n""",
        """            if player_location in {origin_code, move_to}:\n                await self._insert_message(\n                    cur,\n                    session['id'],\n                    turn['id'],\n                    'character',\n                    actor['id'],\n                    'npc_action',\n                    exact_move,\n                )\n""",
        'npc move message',
    ),
    (
        """        await self._insert_message(\n            cur, session['id'], turn['id'], 'narrator', None, 'narration',\n            content if player_location == current_code else f\"{actor['display_name']}이(가) 행동을 했다.\",\n        )\n""",
        """        await self._insert_message(\n            cur,\n            session['id'],\n            turn['id'],\n            'character',\n            actor['id'],\n            'npc_action',\n            content if player_location == current_code\n            else f\"{actor['display_name']}이(가) 행동을 했다.\",\n        )\n""",
        'npc observe message',
    ),
    (
        """        await self._insert_message(\n            cur,\n            session['id'],\n            turn['id'],\n            'narrator',\n            None,\n            'narration',\n            exchange if state.get('current_location') == location_code\n            else f\"{actor['display_name']}이(가) 행동을 했다.\",\n        )\n""",
        """        if state.get('current_location') == location_code:\n            await self._insert_message(\n                cur,\n                session['id'],\n                turn['id'],\n                'character',\n                actor['id'],\n                'dialogue',\n                actual_question,\n            )\n            await self._insert_message(\n                cur,\n                session['id'],\n                turn['id'],\n                'character',\n                target_id,\n                'dialogue',\n                reply,\n            )\n        else:\n            await self._insert_message(\n                cur,\n                session['id'],\n                turn['id'],\n                'character',\n                actor['id'],\n                'npc_action',\n                f\"{actor['display_name']}이(가) 행동을 했다.\",\n            )\n""",
        'npc to npc dialogue',
    ),
    (
        """        await self._insert_message(\n            cur,\n            session['id'],\n            turn['id'],\n            'narrator',\n            None,\n            'narration',\n            public_observation if state.get('current_location') == location_code\n            else f\"{actor['display_name']}이(가) 행동을 했다.\",\n        )\n""",
        """        await self._insert_message(\n            cur,\n            session['id'],\n            turn['id'],\n            'character',\n            actor['id'],\n            'npc_action',\n            public_observation if state.get('current_location') == location_code\n            else f\"{actor['display_name']}이(가) 행동을 했다.\",\n        )\n""",
        'npc investigate message',
    ),
]
for old, new, label in backend_replacements:
    text = replace_once(text, old, new, label)
backend_path.write_text(text)

print('patched readable timeline and NPC chat source')
