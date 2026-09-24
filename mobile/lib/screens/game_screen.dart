import 'package:flutter/material.dart';

import '../core/api_client.dart';

class GameScreen extends StatefulWidget {
  const GameScreen({super.key, required this.initialState});
  final Map<String, dynamic> initialState;

  @override
  State<GameScreen> createState() => _GameScreenState();
}

class _GameScreenState extends State<GameScreen> {
  final _api = ApiClient();
  late Map<String, dynamic> _state;
  bool _busy = false;

  Map<String, dynamic> get _session =>
      (_state['session'] as Map<String, dynamic>?) ?? const {};
  Map<String, dynamic> get _publicState =>
      (_session['public_state'] as Map<String, dynamic>?) ?? const {};
  List<Map<String, dynamic>> get _messages =>
      ((_state['messages'] as List?) ?? const []).cast<Map<String, dynamic>>();
  List<Map<String, dynamic>> get _clues =>
      ((_state['clues'] as List?) ?? const []).cast<Map<String, dynamic>>();
  List<Map<String, dynamic>> get _locations =>
      ((_state['locations'] as List?) ?? const []).cast<Map<String, dynamic>>();
  List<Map<String, dynamic>> get _characters =>
      ((_state['characters'] as List?) ?? const []).cast<Map<String, dynamic>>();
  Map<String, dynamic>? get _playerRole =>
      _state['player_role'] as Map<String, dynamic>?;

  String get _sessionId => _session['id'] as String;
  String? get _playerCharacterId => _session['player_character_id'] as String?;
  bool get _completed => _session['status'] == 'completed';
  bool get _accusation => _session['current_phase'] == 'accusation';

  @override
  void initState() {
    super.initState();
    _state = widget.initialState;
  }

  Future<void> _run(Future<Map<String, dynamic>> Function() action) async {
    if (_busy) return;
    setState(() => _busy = true);
    try {
      final result = await action();
      if (mounted) setState(() => _state = result);
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('$e')),
        );
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _act(
    String actionType, {
    String? targetCharacterId,
    String? inputText,
    Map<String, dynamic>? payload,
  }) async {
    await _run(
      () => _api.post(
        '/sessions/$_sessionId/actions',
        body: {
          'action_type': actionType,
          if (targetCharacterId != null)
            'target_character_id': targetCharacterId,
          if (inputText != null) 'input_text': inputText,
          'payload': payload ?? <String, dynamic>{},
        },
      ),
    );
  }

  Future<void> _showRole() async {
    final role = _playerRole;
    if (role == null) return;
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      builder: (context) => SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(22, 22, 22, 32),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                '${role['display_name']} · ${role['role_label'] ?? ''}',
                style: Theme.of(context).textTheme.headlineSmall,
              ),
              const SizedBox(height: 18),
              _InfoBlock(
                title: '공개 정보',
                body: role['public_bio'] as String? ?? '',
              ),
              const SizedBox(height: 14),
              _InfoBlock(
                title: '당신의 배경',
                body: role['private_backstory'] as String? ?? '없음',
              ),
              const SizedBox(height: 14),
              _InfoBlock(
                title: '목표',
                body: role['objective'] as String? ?? '없음',
              ),
              const SizedBox(height: 14),
              Text(
                '숨기고 싶은 비밀',
                style: Theme.of(context).textTheme.titleMedium,
              ),
              const SizedBox(height: 8),
              ...(((role['secrets'] as List?) ?? const []).map(
                (secret) => Padding(
                  padding: const EdgeInsets.only(bottom: 6),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text('•  '),
                      Expanded(child: Text('$secret')),
                    ],
                  ),
                ),
              )),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _showClues() async {
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      builder: (context) => SafeArea(
        child: SizedBox(
          height: MediaQuery.sizeOf(context).height * .72,
          child: Column(
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(20, 20, 20, 12),
                child: Row(
                  children: [
                    Text(
                      '증거 수첩',
                      style: Theme.of(context).textTheme.titleLarge,
                    ),
                    const Spacer(),
                    Text('${_clues.length}개'),
                  ],
                ),
              ),
              const Divider(height: 1),
              Expanded(
                child: _clues.isEmpty
                    ? const Center(child: Text('아직 발견한 증거가 없습니다.'))
                    : ListView.separated(
                        padding: const EdgeInsets.all(16),
                        itemCount: _clues.length,
                        separatorBuilder: (_, __) =>
                            const SizedBox(height: 10),
                        itemBuilder: (context, index) {
                          final clue = _clues[index];
                          return Card(
                            child: Padding(
                              padding: const EdgeInsets.all(16),
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(
                                    clue['title'] as String? ?? '',
                                    style:
                                        Theme.of(context).textTheme.titleMedium,
                                  ),
                                  const SizedBox(height: 6),
                                  Text(clue['content'] as String? ?? ''),
                                  const SizedBox(height: 8),
                                  Text(
                                    '라운드 ${clue['discovered_turn'] ?? '?'} · ${clue['category'] ?? '기타'}',
                                    style:
                                        Theme.of(context).textTheme.bodySmall,
                                  ),
                                  if (!_completed && !_accusation) ...[
                                    const SizedBox(height: 10),
                                    OutlinedButton.icon(
                                      onPressed: () {
                                        Navigator.pop(context);
                                        _presentClue(clue);
                                      },
                                      icon: const Icon(Icons.record_voice_over),
                                      label: const Text('인물에게 제시'),
                                    ),
                                  ],
                                ],
                              ),
                            ),
                          );
                        },
                      ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _presentClue(Map<String, dynamic> clue) async {
    final targets =
        _characters.where((c) => c['id'] != _playerCharacterId).toList();
    final target = await showModalBottomSheet<Map<String, dynamic>>(
      context: context,
      builder: (context) => SafeArea(
        child: ListView(
          shrinkWrap: true,
          padding: const EdgeInsets.symmetric(vertical: 12),
          children: [
            ListTile(
              title: Text("'${clue['title']}'을 누구에게 제시할까?"),
              subtitle: const Text('증거 제시는 행동 1회를 소모합니다.'),
            ),
            ...targets.map(
              (character) => ListTile(
                leading: const Icon(Icons.person_outline),
                title: Text(character['display_name'] as String? ?? ''),
                subtitle: Text(character['role_label'] as String? ?? ''),
                onTap: () => Navigator.pop(context, character),
              ),
            ),
          ],
        ),
      ),
    );
    if (target == null) return;
    await _act(
      'present',
      targetCharacterId: target['id'] as String,
      payload: {'clue_code': clue['clue_code']},
    );
  }

  Future<void> _chooseMove() async {
    final current = _publicState['current_location'] as String?;
    final target = await showModalBottomSheet<Map<String, dynamic>>(
      context: context,
      builder: (context) => SafeArea(
        child: ListView(
          shrinkWrap: true,
          padding: const EdgeInsets.symmetric(vertical: 12),
          children: [
            const ListTile(title: Text('이동할 장소')),
            ..._locations.map(
              (location) => ListTile(
                leading: Icon(
                  location['location_code'] == current
                      ? Icons.location_on
                      : Icons.place_outlined,
                ),
                title: Text(location['name'] as String? ?? ''),
                subtitle: Text(location['description'] as String? ?? ''),
                enabled: location['location_code'] != current,
                onTap: () => Navigator.pop(context, location),
              ),
            ),
          ],
        ),
      ),
    );
    if (target == null) return;
    await _act(
      'move',
      payload: {'location_code': target['location_code']},
    );
  }

  Future<void> _askCharacter() async {
    final targets =
        _characters.where((c) => c['id'] != _playerCharacterId).toList();
    Map<String, dynamic>? selected = targets.isNotEmpty ? targets.first : null;
    final controller = TextEditingController();

    final result = await showModalBottomSheet<Map<String, String>>(
      context: context,
      isScrollControlled: true,
      builder: (context) => StatefulBuilder(
        builder: (context, setModalState) => SafeArea(
          child: Padding(
            padding: EdgeInsets.fromLTRB(
              20,
              20,
              20,
              MediaQuery.viewInsetsOf(context).bottom + 20,
            ),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text(
                  '인물 심문',
                  style: Theme.of(context).textTheme.titleLarge,
                ),
                const SizedBox(height: 12),
                DropdownButtonFormField<String>(
                  initialValue: selected?['id'] as String?,
                  decoration: const InputDecoration(
                    labelText: '대화할 인물',
                    border: OutlineInputBorder(),
                  ),
                  items: targets
                      .map(
                        (c) => DropdownMenuItem<String>(
                          value: c['id'] as String,
                          child: Text(
                            '${c['display_name']} · ${c['role_label'] ?? ''}',
                          ),
                        ),
                      )
                      .toList(),
                  onChanged: (id) {
                    setModalState(() {
                      selected = targets.firstWhere((c) => c['id'] == id);
                    });
                  },
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: controller,
                  autofocus: true,
                  minLines: 2,
                  maxLines: 5,
                  decoration: const InputDecoration(
                    hintText: '예: 22시 15분쯤 어디에 있었어요?',
                    border: OutlineInputBorder(),
                  ),
                ),
                const SizedBox(height: 14),
                FilledButton.icon(
                  onPressed: selected == null
                      ? null
                      : () {
                          final question = controller.text.trim();
                          if (question.isEmpty) return;
                          Navigator.pop(
                            context,
                            {
                              'character_id': selected!['id'] as String,
                              'question': question,
                            },
                          );
                        },
                  icon: const Icon(Icons.send),
                  label: const Text('질문하기 · 행동 1회'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
    controller.dispose();
    if (result == null) return;
    await _act(
      'ask',
      targetCharacterId: result['character_id'],
      inputText: result['question'],
    );
  }

  Future<void> _accuse() async {
    final candidates = _characters.where((c) {
      return c['is_player_selectable'] == true &&
          c['id'] != _playerCharacterId;
    }).toList();
    Map<String, dynamic>? selected =
        candidates.isNotEmpty ? candidates.first : null;
    final reason = TextEditingController();

    final result = await showModalBottomSheet<Map<String, String>>(
      context: context,
      isScrollControlled: true,
      builder: (context) => StatefulBuilder(
        builder: (context, setModalState) => SafeArea(
          child: Padding(
            padding: EdgeInsets.fromLTRB(
              20,
              20,
              20,
              MediaQuery.viewInsetsOf(context).bottom + 20,
            ),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text(
                  '최종 지목',
                  style: Theme.of(context).textTheme.headlineSmall,
                ),
                const SizedBox(height: 8),
                const Text('이 선택으로 사건의 결말이 결정됩니다.'),
                const SizedBox(height: 16),
                DropdownButtonFormField<String>(
                  initialValue: selected?['id'] as String?,
                  decoration: const InputDecoration(
                    labelText: '범인으로 지목할 인물',
                    border: OutlineInputBorder(),
                  ),
                  items: candidates
                      .map(
                        (c) => DropdownMenuItem<String>(
                          value: c['id'] as String,
                          child: Text(
                            '${c['display_name']} · ${c['role_label'] ?? ''}',
                          ),
                        ),
                      )
                      .toList(),
                  onChanged: (id) {
                    setModalState(() {
                      selected = candidates.firstWhere((c) => c['id'] == id);
                    });
                  },
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: reason,
                  minLines: 3,
                  maxLines: 6,
                  decoration: const InputDecoration(
                    labelText: '추리 근거 (선택)',
                    hintText: '발견한 증거와 진술의 모순을 정리해보세요.',
                    border: OutlineInputBorder(),
                  ),
                ),
                const SizedBox(height: 14),
                FilledButton(
                  onPressed: selected == null
                      ? null
                      : () => Navigator.pop(
                            context,
                            {
                              'culprit_character_id':
                                  selected!['id'] as String,
                              'reasoning': reason.text.trim(),
                            },
                          ),
                  child: const Text('이 인물을 최종 지목'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
    reason.dispose();
    if (result == null) return;

    await _run(
      () => _api.post('/sessions/$_sessionId/accuse', body: result),
    );
  }

  @override
  Widget build(BuildContext context) {
    final round = _session['current_turn'] ?? 1;
    final maxRounds =
        _publicState['max_rounds'] ?? _session['max_turns'] ?? 6;
    final remaining = _publicState['actions_remaining'] ?? 0;
    final currentLocation =
        _publicState['current_location_name'] ?? '장소 미상';

    return Scaffold(
      appBar: AppBar(
        title: Text(_session['story_title'] as String? ?? 'ALIBI'),
        actions: [
          IconButton(
            tooltip: '내 역할',
            onPressed: _showRole,
            icon: const Icon(Icons.badge_outlined),
          ),
          IconButton(
            tooltip: '증거',
            onPressed: _showClues,
            icon: Badge(
              label: Text('${_clues.length}'),
              child: const Icon(Icons.inventory_2_outlined),
            ),
          ),
        ],
      ),
      body: Column(
        children: [
          _StatusBar(
            round: round,
            maxRounds: maxRounds,
            remaining: remaining,
            location: '$currentLocation',
            phase: _session['current_phase'] as String? ?? '',
          ),
          if (_busy) const LinearProgressIndicator(minHeight: 2),
          Expanded(
            child: _completed
                ? _EndingView(state: _state)
                : _MessageTimeline(messages: _messages),
          ),
          if (!_completed)
            _ActionPanel(
              disabled: _busy,
              accusation: _accusation,
              onMove: _chooseMove,
              onSearch: () => _act(
                'search',
                payload: {
                  'location_code': _publicState['current_location'],
                },
              ),
              onInspect: () => _act(
                'inspect',
                payload: {
                  'location_code': _publicState['current_location'],
                },
              ),
              onAsk: _askCharacter,
              onAccuse: _accuse,
            ),
        ],
      ),
    );
  }
}

class _StatusBar extends StatelessWidget {
  const _StatusBar({
    required this.round,
    required this.maxRounds,
    required this.remaining,
    required this.location,
    required this.phase,
  });

  final Object round;
  final Object maxRounds;
  final Object remaining;
  final String location;
  final String phase;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 10),
      child: Wrap(
        spacing: 8,
        runSpacing: 8,
        children: [
          Chip(label: Text('라운드 $round / $maxRounds')),
          Chip(label: Text('남은 행동 $remaining')),
          Chip(
            avatar: const Icon(Icons.place_outlined, size: 18),
            label: Text(location),
          ),
          if (phase == 'accusation')
            const Chip(
              avatar: Icon(Icons.gavel, size: 18),
              label: Text('최종 지목'),
            ),
        ],
      ),
    );
  }
}

class _MessageTimeline extends StatelessWidget {
  const _MessageTimeline({required this.messages});
  final List<Map<String, dynamic>> messages;

  @override
  Widget build(BuildContext context) {
    if (messages.isEmpty) {
      return const Center(child: Text('사건 기록을 불러오는 중입니다.'));
    }
    return ListView.builder(
      padding: const EdgeInsets.fromLTRB(14, 4, 14, 18),
      itemCount: messages.length,
      itemBuilder: (context, index) {
        final item = messages[index];
        final type = item['speaker_type'] as String? ?? 'system';
        final isPlayer = type == 'player';
        final isNarration = type == 'narrator' || type == 'system';
        final speaker = item['speaker_name'] as String? ??
            (type == 'narrator'
                ? '사건'
                : type == 'system'
                    ? '시스템'
                    : '나');

        if (isNarration) {
          return Padding(
            padding: const EdgeInsets.symmetric(vertical: 8),
            child: Card(
              child: Padding(
                padding: const EdgeInsets.all(14),
                child: Text(
                  item['content'] as String? ?? '',
                  textAlign: TextAlign.center,
                ),
              ),
            ),
          );
        }

        return Align(
          alignment:
              isPlayer ? Alignment.centerRight : Alignment.centerLeft,
          child: Container(
            constraints: const BoxConstraints(maxWidth: 340),
            margin: const EdgeInsets.symmetric(vertical: 5),
            padding: const EdgeInsets.all(13),
            decoration: BoxDecoration(
              color: isPlayer
                  ? Theme.of(context).colorScheme.primaryContainer
                  : Theme.of(context).colorScheme.surfaceContainerHighest,
              borderRadius: BorderRadius.circular(14),
            ),
            child: Column(
              crossAxisAlignment: isPlayer
                  ? CrossAxisAlignment.end
                  : CrossAxisAlignment.start,
              children: [
                Text(
                  speaker,
                  style: Theme.of(context).textTheme.labelMedium,
                ),
                const SizedBox(height: 4),
                Text(item['content'] as String? ?? ''),
              ],
            ),
          ),
        );
      },
    );
  }
}

class _ActionPanel extends StatelessWidget {
  const _ActionPanel({
    required this.disabled,
    required this.accusation,
    required this.onMove,
    required this.onSearch,
    required this.onInspect,
    required this.onAsk,
    required this.onAccuse,
  });

  final bool disabled;
  final bool accusation;
  final VoidCallback onMove;
  final VoidCallback onSearch;
  final VoidCallback onInspect;
  final VoidCallback onAsk;
  final VoidCallback onAccuse;

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      top: false,
      child: Container(
        padding: const EdgeInsets.fromLTRB(12, 10, 12, 12),
        decoration: BoxDecoration(
          border: Border(
            top: BorderSide(color: Theme.of(context).dividerColor),
          ),
        ),
        child: accusation
            ? SizedBox(
                width: double.infinity,
                child: FilledButton.icon(
                  onPressed: disabled ? null : onAccuse,
                  icon: const Icon(Icons.gavel),
                  label: const Text('최종 지목하기'),
                ),
              )
            : Row(
                children: [
                  Expanded(
                    child: _ActionButton(
                      icon: Icons.directions_walk,
                      label: '이동',
                      onPressed: disabled ? null : onMove,
                    ),
                  ),
                  Expanded(
                    child: _ActionButton(
                      icon: Icons.search,
                      label: '수색',
                      onPressed: disabled ? null : onSearch,
                    ),
                  ),
                  Expanded(
                    child: _ActionButton(
                      icon: Icons.visibility_outlined,
                      label: '조사',
                      onPressed: disabled ? null : onInspect,
                    ),
                  ),
                  Expanded(
                    child: _ActionButton(
                      icon: Icons.forum_outlined,
                      label: '심문',
                      onPressed: disabled ? null : onAsk,
                    ),
                  ),
                ],
              ),
      ),
    );
  }
}

class _ActionButton extends StatelessWidget {
  const _ActionButton({
    required this.icon,
    required this.label,
    required this.onPressed,
  });

  final IconData icon;
  final String label;
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) {
    return TextButton(
      onPressed: onPressed,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon),
          const SizedBox(height: 4),
          Text(label),
        ],
      ),
    );
  }
}

class _EndingView extends StatelessWidget {
  const _EndingView({required this.state});
  final Map<String, dynamic> state;

  @override
  Widget build(BuildContext context) {
    final ending = state['ending'] as Map<String, dynamic>?;
    final solution = state['solution'] as Map<String, dynamic>?;
    return ListView(
      padding: const EdgeInsets.all(22),
      children: [
        Icon(
          ending?['is_success'] == true
              ? Icons.check_circle
              : Icons.nightlight,
          size: 72,
        ),
        const SizedBox(height: 16),
        Text(
          ending?['title'] as String? ?? '사건 종료',
          textAlign: TextAlign.center,
          style: Theme.of(context).textTheme.headlineMedium,
        ),
        const SizedBox(height: 12),
        Text(
          ending?['ending_text'] as String? ?? '',
          textAlign: TextAlign.center,
        ),
        const SizedBox(height: 28),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(18),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '사건의 진실',
                  style: Theme.of(context).textTheme.titleLarge,
                ),
                const SizedBox(height: 10),
                Text('범인: ${solution?['culprit_name'] ?? '알 수 없음'}'),
                const SizedBox(height: 8),
                Text(
                  solution?['canonical_explanation'] as String? ?? '',
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 18),
        FilledButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('사건 목록으로'),
        ),
      ],
    );
  }
}

class _InfoBlock extends StatelessWidget {
  const _InfoBlock({required this.title, required this.body});
  final String title;
  final String body;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title, style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 7),
            Text(body),
          ],
        ),
      ),
    );
  }
}
