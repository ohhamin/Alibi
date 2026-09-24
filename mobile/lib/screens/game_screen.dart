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
  List<Map<String, dynamic>> get _characterLocations =>
      ((_state['character_locations'] as List?) ?? const [])
          .cast<Map<String, dynamic>>();

  Map<String, dynamic>? get _playerRole =>
      _state['player_role'] as Map<String, dynamic>?;
  Map<String, dynamic>? get _currentLocationDetail =>
      _state['current_location_detail'] as Map<String, dynamic>?;
  Map<String, dynamic>? get _pendingQuestion =>
      _state['pending_npc_question'] as Map<String, dynamic>?;

  String get _sessionId => _session['id'] as String;
  String? get _playerCharacterId => _session['player_character_id'] as String?;
  bool get _completed => _session['status'] == 'completed';
  String? get _currentActorId => _state['current_actor_id'] as String?;
  String get _currentActorName =>
      _state['current_actor_name'] as String? ?? '';
  bool get _isPlayerTurn =>
      !_completed &&
      _pendingQuestion == null &&
      _currentActorId == _playerCharacterId;

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
      if (mounted) {
        setState(() => _state = result);
      }
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

  Future<void> _submitText() async {
    final text = _actionController.text.trim();
    if (text.isEmpty || _busy) return;

    final pending = _pendingQuestion;
    if (pending == null && !_isPlayerTurn) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            _currentActorName.isEmpty
                ? '아직 당신의 차례가 아닙니다.'
                : '현재 $_currentActorName의 차례입니다.',
          ),
        ),
      );
      return;
    }

    _actionFocus.unfocus();
    await _act(
      pending != null ? 'reply' : 'act',
      inputText: text,
    );
    if (mounted) {
      _actionController.clear();
      _actionFocus.requestFocus();
    }
  }

  Future<void> _showRole() async {
    final role = _playerRole;
    if (role == null) return;

    final personality =
        (role['personality'] as Map<String, dynamic>?) ?? const {};
    final traits = ((personality['traits'] as List?) ?? const [])
        .map((e) => '$e')
        .toList();

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
              if (traits.isNotEmpty) ...[
                const SizedBox(height: 14),
                _InfoBlock(
                  title: '기본 성격',
                  body: traits.join(' · '),
                ),
              ],
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
                    ? const Center(child: Text('아직 확인한 증거가 없습니다.'))
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
                                  if (_isPlayerTurn) ...[
                                    const SizedBox(height: 10),
                                    OutlinedButton.icon(
                                      onPressed: _visibleCharacters.isEmpty
                                          ? null
                                          : () {
                                              Navigator.pop(context);
                                              _presentClue(clue);
                                            },
                                      icon: const Icon(Icons.record_voice_over),
                                      label: const Text('같은 장소 인물에게 제시'),
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
    if (!_isPlayerTurn) return;
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
              subtitle: const Text('같은 장소에 있는 인물에게만 제시할 수 있습니다.'),
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

  String _locationName(String? code) {
    if (code == null) return '위치 미상';
    for (final location in _locations) {
      if (location['location_code'] == code) {
        return location['name'] as String? ?? code;
      }
    }
    return code;
  }

  List<String> _adjacentCodes(String? locationCode) {
    if (locationCode == null) return const [];
    for (final location in _locations) {
      if (location['location_code'] == locationCode) {
        return ((location['adjacent'] as List?) ?? const [])
            .map((e) => '$e')
            .toList();
      }
    }
    return const [];
  }

  Future<void> _showMap() async {
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      builder: (context) => SafeArea(
        child: SizedBox(
          height: MediaQuery.sizeOf(context).height * .78,
          child: Column(
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(20, 18, 12, 10),
                child: Row(
                  children: [
                    Expanded(
                      child: Text(
                        '사건 현장 지도',
                        style: Theme.of(context).textTheme.titleLarge,
                      ),
                    ),
                    IconButton(
                      onPressed: () => Navigator.pop(context),
                      icon: const Icon(Icons.close),
                    ),
                  ],
                ),
              ),
              const Padding(
                padding: EdgeInsets.symmetric(horizontal: 20),
                child: Align(
                  alignment: Alignment.centerLeft,
                  child: Text(
                    '화살표로 연결된 장소끼리만 한 번에 이동할 수 있습니다. 인물 위치는 현재 위치입니다.',
                  ),
                ),
              ),
              const SizedBox(height: 8),
              Expanded(
                child: ListView(
                  padding: const EdgeInsets.fromLTRB(16, 4, 16, 24),
                  children: [
                    ..._locations.map((location) {
                      final code =
                          location['location_code'] as String? ?? '';
                      final adjacent = ((location['adjacent'] as List?) ?? const [])
                          .map((e) => _locationName('$e'))
                          .toList();
                      final people = _characterLocations
                          .where((c) => c['location_code'] == code)
                          .map((c) => c['display_name'] as String? ?? '인물')
                          .toList();
                      final isCurrent =
                          _publicState['current_location'] == code;
                      return Card(
                        child: Padding(
                          padding: const EdgeInsets.all(14),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Row(
                                children: [
                                  Icon(
                                    isCurrent
                                        ? Icons.my_location
                                        : Icons.location_on_outlined,
                                  ),
                                  const SizedBox(width: 8),
                                  Expanded(
                                    child: Text(
                                      location['name'] as String? ?? code,
                                      style: Theme.of(context)
                                          .textTheme
                                          .titleMedium,
                                    ),
                                  ),
                                  if (isCurrent)
                                    const Chip(label: Text('내 위치')),
                                ],
                              ),
                              const SizedBox(height: 8),
                              Text(
                                adjacent.isEmpty
                                    ? '연결된 장소 없음'
                                    : '이동 경로 → ${adjacent.join(' / ')}',
                              ),
                              const SizedBox(height: 6),
                              Text(
                                people.isEmpty
                                    ? '현재 인물: 없음'
                                    : '현재 인물: ${people.join(', ')}',
                              ),
                            ],
                          ),
                        ),
                      );
                    }),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _chooseMove() async {
    if (!_isPlayerTurn) return;

    final current = _publicState['current_location'] as String?;
    final adjacent = _adjacentCodes(current);
    final candidates = _locations
        .where((location) => adjacent.contains(location['location_code']))
        .toList();

    if (candidates.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('현재 위치에서 바로 이동할 수 있는 장소가 없습니다.')),
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
              title: Text('${_locationName(current)}에서 이동'),
              subtitle: const Text('연결된 장소만 표시됩니다. 이동하면 이번 차례가 끝납니다.'),
            ),
            ...candidates.map(
              (location) => ListTile(
                leading: const Icon(Icons.directions_walk),
                title: Text(location['name'] as String? ?? ''),
                subtitle: Text(location['description'] as String? ?? ''),
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
    if (!_isPlayerTurn) return;

    final targets = _visibleCharacters;
    if (targets.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('현재 같은 장소에 대화할 인물이 없습니다.')),
      );
      return;
    }

    Map<String, dynamic> selected = targets.first;
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
                Text('대화', style: Theme.of(context).textTheme.titleLarge),
                const SizedBox(height: 4),
                const Text('같은 장소에 있는 인물에게만 말을 걸 수 있습니다.'),
                const SizedBox(height: 12),
                DropdownButtonFormField<String>(
                  initialValue: selected['id'] as String?,
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
                    if (id == null) return;
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
                    hintText: '예: 사건 직전 어디에 있었어요?',
                    border: OutlineInputBorder(),
                  ),
                ),
                const SizedBox(height: 14),
                FilledButton.icon(
                  onPressed: () {
                    final question = controller.text.trim();
                    if (question.isEmpty) return;
                    Navigator.pop(
                      context,
                      {
                        'character_id': selected['id'] as String,
                        'question': question,
                      },
                    );
                  },
                  icon: const Icon(Icons.send),
                  label: const Text('질문하기'),
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

  @override
  Widget build(BuildContext context) {
    final round = _session['current_turn'] ?? 1;
    final maxRounds =
        _publicState['max_rounds'] ?? _session['max_turns'] ?? 6;
    final currentLocation =
        _publicState['current_location_name'] ?? '장소 미상';
    final pending = _pendingQuestion;

    return Scaffold(
      appBar: AppBar(
        title: Text(_session['story_title'] as String? ?? 'ALIBI'),
        actions: [
          IconButton(
            tooltip: '지도와 인물 위치',
            onPressed: _showMap,
            icon: const Icon(Icons.map_outlined),
          ),
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
            location: '$currentLocation',
            currentActor: _currentActorName,
            isPlayerTurn: _isPlayerTurn,
            hasPendingQuestion: pending != null,
          ),
          if (_busy) const LinearProgressIndicator(minHeight: 2),
          if (!_completed)
            _SceneCard(
              locationName: '$currentLocation',
              description:
                  _currentLocationDetail?['description'] as String? ?? '',
              people: _visibleCharacters,
              adjacentNames: _adjacentCodes(
                _publicState['current_location'] as String?,
              ).map(_locationName).toList(),
              onMap: _showMap,
            ),
          if (pending != null && !_completed)
            _IncomingQuestionCard(
              actorName: pending['actor_name'] as String? ?? '인물',
              question: pending['question'] as String? ?? '',
              isDetectiveBonus: pending['source'] == 'detective_bonus',
            ),
          Expanded(
            child: _completed
                ? _EndingView(state: _state)
                : _MessageTimeline(messages: _messages),
          ),
          if (!_completed)
            _ActionComposer(
              disabled: _busy || (!_isPlayerTurn && pending == null),
              answering: pending != null,
              controller: _actionController,
              focusNode: _actionFocus,
              currentActorName: _currentActorName,
              onSubmit: _submitText,
              onMove: _chooseMove,
              onTalk: _askCharacter,
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
    required this.location,
    required this.currentActor,
    required this.isPlayerTurn,
    required this.hasPendingQuestion,
  });

  final Object round;
  final Object maxRounds;
  final String location;
  final String currentActor;
  final bool isPlayerTurn;
  final bool hasPendingQuestion;

  @override
  Widget build(BuildContext context) {
    final turnText = hasPendingQuestion
        ? '답변 대기'
        : isPlayerTurn
            ? '내 차례'
            : currentActor.isEmpty
                ? '턴 진행 중'
                : '$currentActor 차례';

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 10),
      child: Wrap(
        spacing: 8,
        runSpacing: 8,
        children: [
          Chip(label: Text('라운드 $round / $maxRounds')),
          Chip(
            avatar: Icon(
              isPlayerTurn ? Icons.person : Icons.hourglass_bottom,
              size: 18,
            ),
            label: Text(turnText),
          ),
          Chip(
            avatar: const Icon(Icons.place_outlined, size: 18),
            label: Text(location),
          ),
        ],
      ),
    );
  }
}

class _SceneCard extends StatelessWidget {
  const _SceneCard({
    required this.locationName,
    required this.description,
    required this.people,
    required this.adjacentNames,
    required this.onMap,
  });

  final String locationName;
  final String description;
  final List<Map<String, dynamic>> people;
  final List<String> adjacentNames;
  final VoidCallback onMap;

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
                TextButton.icon(
                  onPressed: onMap,
                  icon: const Icon(Icons.map_outlined, size: 18),
                  label: const Text('지도'),
                ),
              ],
            ),
            if (description.isNotEmpty) ...[
              const SizedBox(height: 6),
              Text(description),
            ],
            const SizedBox(height: 10),
            Text(
              adjacentNames.isEmpty
                  ? '이동 경로: 없음'
                  : '이동 경로 → ${adjacentNames.join(' / ')}',
              style: Theme.of(context).textTheme.bodySmall,
            ),
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

class _IncomingQuestionCard extends StatelessWidget {
  const _IncomingQuestionCard({
    required this.actorName,
    required this.question,
    required this.isDetectiveBonus,
  });

  final String actorName;
  final String question;
  final bool isDetectiveBonus;

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.fromLTRB(12, 0, 12, 8),
      child: ListTile(
        leading: Icon(
          isDetectiveBonus ? Icons.manage_search : Icons.chat_bubble_outline,
        ),
        title: Text(
          isDetectiveBonus ? '탐정의 공개 추가 질문' : '$actorName의 질문',
        ),
        subtitle: Text(question),
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
                ? '게임 마스터'
                : type == 'system'
                    ? '시스템'
                    : '나');

        if (isNarration) {
          return Padding(
            padding: const EdgeInsets.symmetric(vertical: 6),
            child: Card(
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: Text(
                  item['content'] as String? ?? '',
                  textAlign: TextAlign.center,
                ),
              ),
            ),
          );
        }

        return Align(
          alignment: isPlayer ? Alignment.centerRight : Alignment.centerLeft,
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
              crossAxisAlignment:
                  isPlayer ? CrossAxisAlignment.end : CrossAxisAlignment.start,
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

class _ActionComposer extends StatelessWidget {
  const _ActionComposer({
    required this.disabled,
    required this.answering,
    required this.controller,
    required this.focusNode,
    required this.currentActorName,
    required this.onSubmit,
    required this.onMove,
    required this.onTalk,
  });

  final bool disabled;
  final bool answering;
  final TextEditingController controller;
  final FocusNode focusNode;
  final String currentActorName;
  final VoidCallback onSubmit;
  final VoidCallback onMove;
  final VoidCallback onTalk;

  @override
  Widget build(BuildContext context) {
    final hint = answering
        ? '질문에 답변하세요...'
        : disabled
            ? '${currentActorName.isEmpty ? '다른 인물' : currentActorName}의 차례입니다.'
            : '무엇을 할까? 예: 직원용 서랍을 열어본다';

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
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: controller,
              focusNode: focusNode,
              enabled: !disabled || answering,
              minLines: 1,
              maxLines: 3,
              textInputAction: TextInputAction.send,
              onSubmitted: (_) {
                if (!disabled || answering) onSubmit();
              },
              decoration: InputDecoration(
                hintText: hint,
                border: const OutlineInputBorder(),
                suffixIcon: IconButton(
                  tooltip: answering ? '답변하기' : '행동하기',
                  onPressed: (!disabled || answering) ? onSubmit : null,
                  icon: const Icon(Icons.arrow_upward),
                ),
              ),
            ),
            if (!answering) ...[
              const SizedBox(height: 8),
              Row(
                children: [
                  Expanded(
                    child: OutlinedButton.icon(
                      onPressed: disabled ? null : onMove,
                      icon: const Icon(Icons.directions_walk),
                      label: const Text('이동'),
                    ),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: OutlinedButton.icon(
                      onPressed: disabled ? null : onTalk,
                      icon: const Icon(Icons.forum_outlined),
                      label: const Text('대화'),
                    ),
                  ),
                ],
              ),
            ],
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
                Text(solution?['canonical_explanation'] as String? ?? ''),
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
