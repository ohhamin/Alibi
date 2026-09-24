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
  final _actionController = TextEditingController();
  final _actionFocus = FocusNode();
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
  List<Map<String, dynamic>> get _visibleCharacters =>
      ((_state['visible_characters'] as List?) ?? const [])
          .cast<Map<String, dynamic>>();
  Map<String, dynamic> get _knownCharacterLocations =>
      (_state['known_character_locations'] as Map<String, dynamic>?) ?? const {};
  Map<String, dynamic>? get _currentLocationDetail =>
      _state['current_location_detail'] as Map<String, dynamic>?;
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

  @override
  void dispose() {
    _actionController.dispose();
    _actionFocus.dispose();
    super.dispose();
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
          // ignore: use_null_aware_elements
          if (targetCharacterId != null)
            'target_character_id': targetCharacterId,
          // ignore: use_null_aware_elements
          if (inputText != null) 'input_text': inputText,
          'payload': payload ?? <String, dynamic>{},
        },
      ),
    );
  }

  Future<void> _submitFreeAction() async {
    final text = _actionController.text.trim();
    if (text.isEmpty || _busy) return;
    _actionFocus.unfocus();
    await _act('act', inputText: text);
    if (mounted) {
      _actionController.clear();
      _actionFocus.requestFocus();
    }
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
                        separatorBuilder: (_, _) =>
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
    final targets = _visibleCharacters;
    if (targets.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('현재 같은 장소에 대화할 인물이 없습니다.')),
      );
      return;
    }
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

  String _knownPeopleText(String locationCode) {
    final items = <String>[];
    for (final character in _characters) {
      final id = character['id'] as String?;
      if (id == null || id == _playerCharacterId) continue;
      final known = _knownCharacterLocations[id];
      if (known is! Map) continue;
      if (known['location_code'] != locationCode) continue;
      final turn = known['turn_no'];
      final name = character['display_name'] ?? '인물';
      items.add(turn == null ? '$name' : '$name · $turn라운드 확인');
    }
    return items.join(', ');
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
            const ListTile(
              title: Text('이동할 장소'),
              subtitle: Text('이동도 행동 1회를 사용합니다. 인물 위치는 마지막으로 직접 확인한 정보입니다.'),
            ),
            ..._locations.map((location) {
              final code = location['location_code'] as String? ?? '';
              final known = _knownPeopleText(code);
              return ListTile(
                leading: Icon(
                  code == current ? Icons.my_location : Icons.place_outlined,
                ),
                title: Text(location['name'] as String? ?? ''),
                subtitle: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(location['description'] as String? ?? ''),
                    if (known.isNotEmpty) ...[
                      const SizedBox(height: 4),
                      Text('마지막 확인: $known'),
                    ],
                  ],
                ),
                enabled: code != current,
                onTap: () => Navigator.pop(context, location),
              );
            }),
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
    final targets = _visibleCharacters;
    if (targets.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('현재 같은 장소에 대화할 인물이 없습니다.')),
      );
      return;
    }
    Map<String, dynamic>? selected = targets.first;
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
          if (!_completed)
            _SceneCard(
              locationName: '$currentLocation',
              description:
                  _currentLocationDetail?['description'] as String? ?? '',
              people: _visibleCharacters,
            ),
          Expanded(
            child: _completed
                ? _EndingView(state: _state)
                : _MessageTimeline(messages: _messages),
          ),
          if (!_completed)
            _ActionComposer(
              disabled: _busy,
              accusation: _accusation,
              controller: _actionController,
              focusNode: _actionFocus,
              onSubmit: _submitFreeAction,
              onMove: _chooseMove,
              onTalk: _askCharacter,
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
          Chip(label: Text('행동 $remaining / 2')),
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

class _SceneCard extends StatelessWidget {
  const _SceneCard({
    required this.locationName,
    required this.description,
    required this.people,
  });

  final String locationName;
  final String description;
  final List<Map<String, dynamic>> people;

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.fromLTRB(12, 0, 12, 8),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(Icons.room_outlined),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    locationName,
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                ),
              ],
            ),
            if (description.isNotEmpty) ...[
              const SizedBox(height: 8),
              Text(description),
            ],
            const SizedBox(height: 10),
            Text(
              '현재 이곳에 있는 인물',
              style: Theme.of(context).textTheme.labelLarge,
            ),
            const SizedBox(height: 6),
            if (people.isEmpty)
              const Text('아무도 없다.')
            else
              Wrap(
                spacing: 6,
                runSpacing: 6,
                children: people
                    .map(
                      (p) => Chip(
                        avatar: const Icon(Icons.person_outline, size: 17),
                        label: Text(p['display_name'] as String? ?? '인물'),
                      ),
                    )
                    .toList(),
              ),
          ],
        ),
      ),
    );
  }
}

class _ActionComposer extends StatelessWidget {
  const _ActionComposer({
    required this.disabled,
    required this.accusation,
    required this.controller,
    required this.focusNode,
    required this.onSubmit,
    required this.onMove,
    required this.onTalk,
    required this.onAccuse,
  });

  final bool disabled;
  final bool accusation;
  final TextEditingController controller;
  final FocusNode focusNode;
  final VoidCallback onSubmit;
  final VoidCallback onMove;
  final VoidCallback onTalk;
  final VoidCallback onAccuse;

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      top: false,
      child: Container(
        padding: const EdgeInsets.fromLTRB(12, 10, 12, 12),
        decoration: BoxDecoration(
          color: Theme.of(context).colorScheme.surface,
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
            : Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  TextField(
                    controller: controller,
                    focusNode: focusNode,
                    enabled: !disabled,
                    minLines: 1,
                    maxLines: 3,
                    textInputAction: TextInputAction.send,
                    onSubmitted: (_) {
                      if (!disabled) onSubmit();
                    },
                    decoration: InputDecoration(
                      hintText: '무엇을 할까?  예: 책상 오른쪽 서랍을 열어본다',
                      border: const OutlineInputBorder(),
                      suffixIcon: IconButton(
                        tooltip: '행동하기',
                        onPressed: disabled ? null : onSubmit,
                        icon: const Icon(Icons.arrow_upward),
                      ),
                    ),
                  ),
                  const SizedBox(height: 8),
                  Row(
                    children: [
                      Expanded(
                        child: OutlinedButton.icon(
                          onPressed: disabled ? null : onMove,
                          icon: const Icon(Icons.directions_walk),
                          label: const Text('이동 · 1'),
                        ),
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: OutlinedButton.icon(
                          onPressed: disabled ? null : onTalk,
                          icon: const Icon(Icons.forum_outlined),
                          label: const Text('대화 · 1'),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 4),
                  Text(
                    '불가능하거나 대상이 없는 행동은 행동 횟수를 소모하지 않습니다.',
                    style: Theme.of(context).textTheme.bodySmall,
                    textAlign: TextAlign.center,
                  ),
                ],
              ),
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
