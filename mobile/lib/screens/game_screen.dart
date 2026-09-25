import 'package:flutter/material.dart';

import '../core/api_client.dart';
import '../core/app_assets.dart';
import '../core/app_theme.dart';
import '../widgets/pixel_avatar.dart';

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
  bool _autoAdvanceScheduled = false;
  bool _conversationSheetOpen = false;

  Map<String, dynamic> get _session =>
      (_state['session'] as Map<String, dynamic>?) ?? const {};
  Map<String, dynamic> get _publicState =>
      (_session['public_state'] as Map<String, dynamic>?) ?? const {};
  List<Map<String, dynamic>> get _messages =>
      ((_state['messages'] as List?) ?? const []).cast<Map<String, dynamic>>();
  List<Map<String, dynamic>> get _characters =>
      ((_state['characters'] as List?) ?? const []).cast<Map<String, dynamic>>();
  List<Map<String, dynamic>> get _characterDossiers =>
      ((_state['character_dossiers'] as List?) ?? const [])
          .cast<Map<String, dynamic>>();
  List<Map<String, dynamic>> get _clues =>
      ((_state['clues'] as List?) ?? const []).cast<Map<String, dynamic>>();
  List<Map<String, dynamic>> get _locations =>
      ((_state['locations'] as List?) ?? const []).cast<Map<String, dynamic>>();
  List<Map<String, dynamic>> get _visibleCharacters =>
      ((_state['visible_characters'] as List?) ?? const [])
          .cast<Map<String, dynamic>>();
  List<Map<String, dynamic>> get _characterLocations =>
      ((_state['character_locations'] as List?) ?? const [])
          .cast<Map<String, dynamic>>();
  List<Map<String, dynamic>> get _inventoryItems =>
      ((_state['inventory_items'] as List?) ?? const [])
          .cast<Map<String, dynamic>>();
  List<Map<String, dynamic>> get _playerActionHistory =>
      ((_state['player_action_history'] as List?) ?? const [])
          .cast<Map<String, dynamic>>();

  Map<String, dynamic>? get _playerRole =>
      _state['player_role'] as Map<String, dynamic>?;
  Map<String, dynamic>? get _currentLocationDetail =>
      _state['current_location_detail'] as Map<String, dynamic>?;
  Map<String, dynamic>? get _pendingQuestion =>
      _state['pending_npc_question'] as Map<String, dynamic>?;
  Map<String, dynamic>? get _activeConversation =>
      _state['active_conversation'] as Map<String, dynamic>?;

  String get _sessionId => _session['id'] as String;
  String? get _playerCharacterId => _session['player_character_id'] as String?;
  String? get _currentActorId => _state['current_actor_id'] as String?;
  String get _currentActorName =>
      _state['current_actor_name'] as String? ?? '';
  bool get _completed => _session['status'] == 'completed';
  bool get _isPlayerTurn =>
      !_completed &&
      _activeConversation == null &&
      _pendingQuestion == null &&
      _currentActorId == _playerCharacterId;
  int get _movementRemaining =>
      (_publicState['movement_remaining'] as num?)?.toInt() ?? 0;
  int get _actionsRemaining =>
      (_publicState['actions_remaining'] as num?)?.toInt() ?? 0;

  @override
  void initState() {
    super.initState();
    _state = widget.initialState;
    WidgetsBinding.instance.addPostFrameCallback((_) => _afterStateChanged());
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
      if (mounted) {
        setState(() => _busy = false);
        _afterStateChanged();
      }
    }
  }

  void _afterStateChanged() {
    if (!mounted || _busy || _completed) return;

    if (_activeConversation != null && !_conversationSheetOpen) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted &&
            _activeConversation != null &&
            !_conversationSheetOpen) {
          _openConversationSheet();
        }
      });
      return;
    }

    if (_pendingQuestion != null) return;

    if (_currentActorId != _playerCharacterId && !_autoAdvanceScheduled) {
      _autoAdvanceScheduled = true;
      Future<void>.delayed(const Duration(milliseconds: 140), () async {
        _autoAdvanceScheduled = false;
        if (!mounted ||
            _busy ||
            _completed ||
            _activeConversation != null ||
            _pendingQuestion != null ||
            _currentActorId == _playerCharacterId) {
          return;
        }
        await _run(
          () => _api.post('/sessions/$_sessionId/advance'),
        );
      });
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

  Future<void> _submitText() async {
    final text = _actionController.text.trim();
    if (text.isEmpty || _busy) return;

    if (_pendingQuestion != null) {
      _actionFocus.unfocus();
      await _act('reply', inputText: text);
      if (mounted) _actionController.clear();
      return;
    }

    if (!_isPlayerTurn) {
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
    await _act('act', inputText: text);
    if (mounted) _actionController.clear();
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

  Map<String, dynamic>? _characterById(String? id) {
    if (id == null || id.isEmpty) return null;
    for (final character in _characters) {
      if ('${character['id']}' == id) return character;
    }
    return null;
  }

  Map<String, dynamic>? _characterByName(String? name) {
    if (name == null || name.isEmpty) return null;
    for (final character in _characters) {
      if (character['display_name'] == name) return character;
    }
    return null;
  }

  String _clueTitle(String? code) {
    if (code == null) return '물건';
    for (final item in _inventoryItems) {
      if (item['clue_code'] == code) {
        return item['title'] as String? ?? code;
      }
    }
    for (final item in _clues) {
      if (item['clue_code'] == code) {
        return item['title'] as String? ?? code;
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

  String _historyDescription(Map<String, dynamic> item) {
    final type = item['action_type'] as String? ?? '';
    final input = item['input_text'] as String? ?? '';
    final target = item['target_name'] as String? ?? '';
    final payload =
        (item['payload'] as Map<String, dynamic>?) ?? const <String, dynamic>{};

    switch (type) {
      case 'move':
        return '이동 → ${_locationName(payload['location_code'] as String?)}';
      case 'ask':
        return '$target에게 질문: $input';
      case 'reply':
        return '대답: $input';
      case 'conversation_present':
        return '대화 중 물건 제시: ${_clueTitle(payload['clue_code'] as String?)}';
      case 'present':
        return '$target에게 물건 제시: ${_clueTitle(payload['clue_code'] as String?)}';
      case 'end_conversation':
        return '대화 종료';
      case 'act':
      case 'search':
      case 'inspect':
        return input.isEmpty ? '현장 행동' : input;
      default:
        return input.isEmpty ? type : input;
    }
  }

  String _historyTime(Map<String, dynamic> item) {
    final turn = item['turn_no'] ?? '?';
    final raw = item['created_at'] as String?;
    if (raw == null) return '라운드 $turn';
    final parsed = DateTime.tryParse(raw)?.toLocal();
    if (parsed == null) return '라운드 $turn';
    final hh = parsed.hour.toString().padLeft(2, '0');
    final mm = parsed.minute.toString().padLeft(2, '0');
    return '라운드 $turn · $hh:$mm';
  }

  Future<void> _showRole() async {
    final role = _playerRole;
    if (role == null) return;
    final personality =
        (role['personality'] as Map<String, dynamic>?) ?? const {};
    final traits = ((personality['traits'] as List?) ?? const [])
        .map((e) => '$e')
        .toList();
    final relationshipSeed =
        (role['relationship_seed'] as Map<String, dynamic>?) ?? const {};
    final incidentTimeline =
        ((relationshipSeed['incident_timeline'] as List?) ?? const [])
            .cast<Map<String, dynamic>>();

    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      builder: (context) => SafeArea(
        child: SizedBox(
          height: MediaQuery.sizeOf(context).height * .82,
          child: ListView(
            padding: const EdgeInsets.fromLTRB(20, 20, 20, 32),
            children: [
              Text(
                '${role['display_name']} · ${role['role_label'] ?? ''}',
                style: Theme.of(context).textTheme.headlineSmall,
              ),
              const SizedBox(height: 16),
              _InfoBlock(
                title: '공개 정보',
                body: role['public_bio'] as String? ?? '',
              ),
              const SizedBox(height: 10),
              _InfoBlock(
                title: '나의 배경',
                body: role['private_backstory'] as String? ?? '없음',
              ),
              const SizedBox(height: 10),
              _InfoBlock(
                title: '목표',
                body: role['objective'] as String? ?? '없음',
              ),
              if (traits.isNotEmpty) ...[
                const SizedBox(height: 10),
                _InfoBlock(title: '기본 성격', body: traits.join(' · ')),
              ],
              const SizedBox(height: 18),
              Text('소지품', style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 8),
              if (_inventoryItems.isEmpty)
                const Text('현재 가지고 있는 사건 물건이 없습니다.')
              else
                ..._inventoryItems.map(
                  (item) => ListTile(
                    contentPadding: EdgeInsets.zero,
                    leading: const Icon(Icons.inventory_2_outlined),
                    title: Text(item['title'] as String? ?? ''),
                    subtitle: Text(item['content'] as String? ?? ''),
                  ),
                ),
              const SizedBox(height: 18),
              Text(
                '사건 당시 나의 행적',
                style: Theme.of(context).textTheme.titleMedium,
              ),
              const SizedBox(height: 4),
              const Text(
                '사건이 일어나기 전후에 내가 실제로 무엇을 했는지 정리한 기록입니다. 진술할 때 사실대로 말할지, 일부를 숨기거나 거짓말할지 판단하는 데 참고하세요.',
              ),
              const SizedBox(height: 8),
              if (incidentTimeline.isEmpty)
                const Text('정리된 사건 당시 행적이 없습니다.')
              else
                ...incidentTimeline.map(
                  (item) => ListTile(
                    contentPadding: EdgeInsets.zero,
                    dense: true,
                    leading: const Icon(Icons.schedule, size: 20),
                    title: Text(item['text'] as String? ?? ''),
                    subtitle: Text(item['time'] as String? ?? ''),
                  ),
                ),
              const SizedBox(height: 18),
              Text(
                '게임 시작 후 행동·증언',
                style: Theme.of(context).textTheme.titleMedium,
              ),
              const SizedBox(height: 4),
              const Text(
                '게임 시작 후 내가 실제로 한 행동과 대답입니다. 이전 발언과 모순되지 않는지 확인할 수 있습니다.',
              ),
              const SizedBox(height: 8),
              if (_playerActionHistory.isEmpty)
                const Text('아직 기록된 행동이 없습니다.')
              else
                ..._playerActionHistory.map(
                  (item) => ListTile(
                    contentPadding: EdgeInsets.zero,
                    dense: true,
                    leading: const Icon(Icons.history, size: 20),
                    title: Text(_historyDescription(item)),
                    subtitle: Text(_historyTime(item)),
                  ),
                ),
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
                          final holding = _inventoryItems.any(
                            (item) =>
                                item['clue_code'] == clue['clue_code'],
                          );
                          return Card(
                            child: ListTile(
                              title: Text(clue['title'] as String? ?? ''),
                              subtitle: Text(clue['content'] as String? ?? ''),
                              trailing: holding
                                  ? const Chip(label: Text('소지 중'))
                                  : null,
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

  Future<void> _showCharacterDossiers() async {
    final dossiers = _characterDossiers.isNotEmpty
        ? _characterDossiers
        : _characters
            .map(
              (character) => <String, dynamic>{
                ...character,
                'is_player': '${character['id']}' == _playerCharacterId,
                'known_statements': const <String>[],
                'related_clues': const <Map<String, dynamic>>[],
              },
            )
            .toList();

    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      builder: (context) => SafeArea(
        child: SizedBox(
          height: MediaQuery.sizeOf(context).height * .84,
          child: Column(
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(18, 16, 12, 10),
                child: Row(
                  children: [
                    const Icon(
                      Icons.people_alt_outlined,
                      color: AppTheme.brass,
                    ),
                    const SizedBox(width: 9),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            '등장인물 기록',
                            style: Theme.of(context).textTheme.titleLarge,
                          ),
                          Text(
                            '지금까지 직접 확인한 정보만 기록됩니다.',
                            style: Theme.of(context).textTheme.bodySmall,
                          ),
                        ],
                      ),
                    ),
                    IconButton(
                      onPressed: () => Navigator.pop(context),
                      icon: const Icon(Icons.close),
                    ),
                  ],
                ),
              ),
              const Divider(height: 1),
              Expanded(
                child: ListView.separated(
                  padding: const EdgeInsets.fromLTRB(14, 12, 14, 28),
                  itemCount: dossiers.length,
                  separatorBuilder: (_, _) => const SizedBox(height: 10),
                  itemBuilder: (context, index) {
                    final dossier = dossiers[index];
                    final statements =
                        ((dossier['known_statements'] as List?) ?? const [])
                            .map((e) => '$e')
                            .where((e) => e.trim().isNotEmpty)
                            .toList();
                    final relatedClues =
                        ((dossier['related_clues'] as List?) ?? const [])
                            .cast<Map<String, dynamic>>();
                    final isPlayer = dossier['is_player'] == true;
                    final locationName =
                        dossier['known_location_name'] as String?;
                    final name =
                        dossier['display_name'] as String? ?? '알 수 없는 인물';
                    final role = dossier['role_label'] as String? ?? '';

                    return Card(
                      clipBehavior: Clip.antiAlias,
                      child: ExpansionTile(
                        leading: PixelAvatar(
                          name: name,
                          code: dossier['code'] as String?,
                          size: 48,
                        ),
                        title: Row(
                          children: [
                            Flexible(
                              child: Text(
                                name,
                                style: Theme.of(context).textTheme.titleMedium,
                              ),
                            ),
                            if (isPlayer) ...[
                              const SizedBox(width: 7),
                              const Chip(
                                visualDensity: VisualDensity.compact,
                                label: Text('나'),
                              ),
                            ],
                          ],
                        ),
                        subtitle: Text(role),
                        childrenPadding:
                            const EdgeInsets.fromLTRB(16, 0, 16, 16),
                        children: [
                          Align(
                            alignment: Alignment.centerLeft,
                            child: Text(
                              dossier['public_bio'] as String? ??
                                  '공개된 기본 정보가 없습니다.',
                            ),
                          ),
                          if (locationName != null &&
                              locationName.trim().isNotEmpty) ...[
                            const SizedBox(height: 12),
                            Row(
                              children: [
                                const Icon(
                                  Icons.place_outlined,
                                  size: 17,
                                  color: AppTheme.brass,
                                ),
                                const SizedBox(width: 6),
                                Expanded(
                                  child: Text(
                                    '확인된 위치 · $locationName',
                                    style:
                                        Theme.of(context).textTheme.bodySmall,
                                  ),
                                ),
                              ],
                            ),
                          ],
                          const SizedBox(height: 14),
                          Align(
                            alignment: Alignment.centerLeft,
                            child: Text(
                              '알게 된 내용',
                              style: Theme.of(context).textTheme.labelLarge,
                            ),
                          ),
                          const SizedBox(height: 7),
                          if (statements.isEmpty && relatedClues.isEmpty)
                            Align(
                              alignment: Alignment.centerLeft,
                              child: Text(
                                '아직 추가로 확인한 내용이 없습니다.',
                                style: Theme.of(context).textTheme.bodySmall,
                              ),
                            )
                          else ...[
                            ...statements.map(
                              (statement) => Padding(
                                padding: const EdgeInsets.only(bottom: 7),
                                child: Row(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    const Text(
                                      '• ',
                                      style: TextStyle(color: AppTheme.brass),
                                    ),
                                    Expanded(child: Text(statement)),
                                  ],
                                ),
                              ),
                            ),
                            ...relatedClues.map(
                              (clue) => Padding(
                                padding: const EdgeInsets.only(top: 5),
                                child: Container(
                                  width: double.infinity,
                                  padding: const EdgeInsets.all(10),
                                  decoration: BoxDecoration(
                                    color: const Color(0xFF0E1013),
                                    borderRadius: BorderRadius.circular(8),
                                    border: Border.all(
                                      color: const Color(0xFF2D3036),
                                    ),
                                  ),
                                  child: Column(
                                    crossAxisAlignment:
                                        CrossAxisAlignment.start,
                                    children: [
                                      Text(
                                        clue['title'] as String? ?? '관련 증거',
                                        style: Theme.of(context)
                                            .textTheme
                                            .labelLarge,
                                      ),
                                      const SizedBox(height: 3),
                                      Text(
                                        clue['content'] as String? ?? '',
                                        style:
                                            Theme.of(context).textTheme.bodySmall,
                                      ),
                                    ],
                                  ),
                                ),
                              ),
                            ),
                          ],
                        ],
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
                    '연결된 장소끼리 한 칸 이동할 수 있습니다. 인물 위치는 현재 위치를 그대로 보여줍니다.',
                  ),
                ),
              ),
              const SizedBox(height: 8),
              Expanded(
                child: ListView(
                  padding: const EdgeInsets.fromLTRB(16, 4, 16, 24),
                  children: _locations.map((location) {
                    final code =
                        location['location_code'] as String? ?? '';
                    final adjacent =
                        ((location['adjacent'] as List?) ?? const [])
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
                                    style:
                                        Theme.of(context).textTheme.titleMedium,
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
                  }).toList(),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _showCurrentLocation() async {
    final currentLocation = _publicState['current_location'] as String?;
    final currentName =
        _publicState['current_location_name'] as String? ?? '장소 미상';
    final adjacentNames =
        _adjacentCodes(currentLocation).map(_locationName).toList();

    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      builder: (context) => SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 28),
          child: _SceneCard(
            locationCode: currentLocation,
            locationName: currentName,
            description:
                _currentLocationDetail?['description'] as String? ?? '',
            people: _visibleCharacters,
            adjacentNames: adjacentNames,
            onMap: () {
              Navigator.pop(context);
              _showMap();
            },
          ),
        ),
      ),
    );
  }

  Future<void> _chooseMove() async {
    if (!_isPlayerTurn || _movementRemaining <= 0) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('이번 차례의 무료 이동을 사용할 수 없습니다.')),
      );
      return;
    }

    final current = _publicState['current_location'] as String?;
    final adjacent = _adjacentCodes(current);
    final candidates = _locations
        .where((location) => adjacent.contains(location['location_code']))
        .toList();

    if (candidates.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('현재 위치에서 바로 이동할 장소가 없습니다.')),
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
              title: Text('${_locationName(current)}에서 무료 이동'),
              subtitle: const Text(
                '이번 차례에 인접 장소 한 칸만 이동할 수 있습니다. 이동 후에도 주행동 1회가 남습니다.',
              ),
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

  Future<void> _startConversation() async {
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
                Text(
                  '대화 시작',
                  style: Theme.of(context).textTheme.titleLarge,
                ),
                const SizedBox(height: 4),
                const Text(
                  '대화 시작만 주행동 1회로 계산됩니다. 이후 최대 3번의 왕복 답변과 물건 제시는 추가 행동을 쓰지 않습니다.',
                ),
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
                          child: Row(
                            children: [
                              PixelAvatar(
                                name: c['display_name'] as String? ?? '인물',
                                code: c['code'] as String?,
                                size: 28,
                                borderRadius: 4,
                              ),
                              const SizedBox(width: 8),
                              Flexible(
                                child: Text(
                                  '${c['display_name']} · ${c['role_label'] ?? ''}',
                                  overflow: TextOverflow.ellipsis,
                                ),
                              ),
                            ],
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
                    hintText: '첫 질문이나 말을 입력하세요.',
                    border: OutlineInputBorder(),
                  ),
                ),
                const SizedBox(height: 14),
                FilledButton.icon(
                  onPressed: () {
                    final text = controller.text.trim();
                    if (text.isEmpty) return;
                    Navigator.pop(
                      context,
                      {
                        'character_id': selected['id'] as String,
                        'text': text,
                      },
                    );
                  },
                  icon: const Icon(Icons.forum_outlined),
                  label: const Text('대화 시작 · 주행동 1회'),
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
      inputText: result['text'],
    );
  }

  Future<Map<String, dynamic>?> _pickInventoryItem(
    BuildContext sheetContext,
  ) async {
    if (_inventoryItems.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('현재 제시할 소지품이 없습니다.')),
      );
      return null;
    }
    return showDialog<Map<String, dynamic>>(
      context: sheetContext,
      builder: (dialogContext) => AlertDialog(
        title: const Text('소지품 제시'),
        content: SizedBox(
          width: double.maxFinite,
          child: ListView(
            shrinkWrap: true,
            children: _inventoryItems
                .map(
                  (item) => ListTile(
                    leading: const Icon(Icons.inventory_2_outlined),
                    title: Text(item['title'] as String? ?? ''),
                    subtitle: Text(item['content'] as String? ?? ''),
                    onTap: () => Navigator.pop(dialogContext, item),
                  ),
                )
                .toList(),
          ),
        ),
      ),
    );
  }

  Future<void> _openConversationSheet() async {
    if (_conversationSheetOpen || _activeConversation == null || !mounted) {
      return;
    }
    _conversationSheetOpen = true;
    final replyController = TextEditingController();

    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      isDismissible: false,
      enableDrag: false,
      builder: (sheetContext) => StatefulBuilder(
        builder: (sheetContext, setSheetState) {
          final conversation = _activeConversation;
          if (conversation == null) {
            WidgetsBinding.instance.addPostFrameCallback((_) {
              if (sheetContext.mounted) Navigator.pop(sheetContext);
            });
            return const SizedBox.shrink();
          }

          final history =
              ((conversation['history'] as List?) ?? const [])
                  .cast<Map<String, dynamic>>();
          final exchange =
              (conversation['exchange_count'] as num?)?.toInt() ?? 0;
          final maxExchange =
              (conversation['max_exchanges'] as num?)?.toInt() ?? 3;
          final actorName =
              conversation['actor_name'] as String? ?? '인물';
          final actorCharacter =
              _characterById(conversation['actor_id'] as String?) ??
                  _characterByName(actorName);
          final playerCharacter = _characterById(_playerCharacterId);

          Future<void> refreshAfter(Future<void> task) async {
            await task;
            if (!sheetContext.mounted) return;
            if (_activeConversation == null) {
              Navigator.pop(sheetContext);
            } else {
              setSheetState(() {});
            }
          }

          return SafeArea(
            child: Padding(
              padding: EdgeInsets.fromLTRB(
                16,
                14,
                16,
                MediaQuery.viewInsetsOf(sheetContext).bottom + 14,
              ),
              child: SizedBox(
                height: MediaQuery.sizeOf(sheetContext).height * .68,
                child: Column(
                  children: [
                    Row(
                      children: [
                        PixelAvatar(
                          name: actorName,
                          code: actorCharacter?['code'] as String?,
                          size: 44,
                        ),
                        const SizedBox(width: 10),
                        Expanded(
                          child: Text(
                            '$actorName과의 대화',
                            style: Theme.of(sheetContext)
                                .textTheme
                                .titleLarge,
                          ),
                        ),
                        Chip(label: Text('왕복 $exchange / $maxExchange')),
                      ],
                    ),
                    const SizedBox(height: 6),
                    const Align(
                      alignment: Alignment.centerLeft,
                      child: Text(
                        '이 대화의 후속 답변과 소지품 제시는 추가 행동을 소모하지 않습니다. 같은 방의 인물은 내용을 모두 듣습니다.',
                      ),
                    ),
                    const SizedBox(height: 10),
                    const Divider(height: 1),
                    Expanded(
                      child: ListView.builder(
                        padding: const EdgeInsets.symmetric(vertical: 10),
                        itemCount: history.length,
                        itemBuilder: (context, index) {
                          final item = history[index];
                          final speaker = item['speaker'] as String? ?? '';
                          final text = item['text'] as String? ?? '';
                          final isMe = speaker == 'player';
                          final bubble = Container(
                            constraints: const BoxConstraints(maxWidth: 270),
                            padding: const EdgeInsets.all(11),
                            decoration: BoxDecoration(
                              color: isMe
                                  ? AppTheme.brass.withValues(alpha: .10)
                                  : const Color(0xFF171A1F),
                              borderRadius: BorderRadius.circular(10),
                              border: Border.all(
                                color: isMe
                                    ? AppTheme.brass.withValues(alpha: .24)
                                    : const Color(0xFF30333A),
                              ),
                            ),
                            child: Column(
                              crossAxisAlignment: isMe
                                  ? CrossAxisAlignment.end
                                  : CrossAxisAlignment.start,
                              children: [
                                Text(
                                  isMe ? '나' : speaker,
                                  style:
                                      Theme.of(context).textTheme.labelSmall,
                                ),
                                const SizedBox(height: 3),
                                Text(text),
                              ],
                            ),
                          );
                          return Padding(
                            padding: const EdgeInsets.symmetric(vertical: 4),
                            child: Row(
                              mainAxisAlignment: isMe
                                  ? MainAxisAlignment.end
                                  : MainAxisAlignment.start,
                              crossAxisAlignment: CrossAxisAlignment.end,
                              children: isMe
                                  ? [
                                      Flexible(child: bubble),
                                      const SizedBox(width: 7),
                                      PixelAvatar(
                                        name: playerCharacter?['display_name']
                                                as String? ??
                                            '나',
                                        code: playerCharacter?['code']
                                            as String?,
                                        size: 34,
                                      ),
                                    ]
                                  : [
                                      PixelAvatar(
                                        name: actorName,
                                        code: actorCharacter?['code']
                                            as String?,
                                        size: 34,
                                      ),
                                      const SizedBox(width: 7),
                                      Flexible(child: bubble),
                                    ],
                            ),
                          );
                        },
                      ),
                    ),
                    TextField(
                      controller: replyController,
                      minLines: 1,
                      maxLines: 3,
                      enabled: !_busy,
                      textInputAction: TextInputAction.send,
                      onSubmitted: (_) async {
                        final text = replyController.text.trim();
                        if (text.isEmpty || _busy) return;
                        replyController.clear();
                        await refreshAfter(
                          _act('reply', inputText: text),
                        );
                      },
                      decoration: InputDecoration(
                        hintText: '답변 또는 질문...',
                        border: const OutlineInputBorder(),
                        suffixIcon: IconButton(
                          onPressed: _busy
                              ? null
                              : () async {
                                  final text =
                                      replyController.text.trim();
                                  if (text.isEmpty) return;
                                  replyController.clear();
                                  await refreshAfter(
                                    _act('reply', inputText: text),
                                  );
                                },
                          icon: const Icon(Icons.send),
                        ),
                      ),
                    ),
                    const SizedBox(height: 8),
                    Row(
                      children: [
                        Expanded(
                          child: OutlinedButton.icon(
                            onPressed: _busy
                                ? null
                                : () async {
                                    final item = await _pickInventoryItem(
                                      sheetContext,
                                    );
                                    if (item == null) return;
                                    await refreshAfter(
                                      _act(
                                        'conversation_present',
                                        payload: {
                                          'clue_code':
                                              item['clue_code'],
                                        },
                                      ),
                                    );
                                  },
                            icon: const Icon(Icons.inventory_2_outlined),
                            label: const Text('소지품 제시'),
                          ),
                        ),
                        const SizedBox(width: 8),
                        Expanded(
                          child: TextButton.icon(
                            onPressed: _busy
                                ? null
                                : () async {
                                    await refreshAfter(
                                      _act('end_conversation'),
                                    );
                                  },
                            icon: const Icon(Icons.call_end),
                            label: const Text('대화 그만하기'),
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ),
          );
        },
      ),
    );

    replyController.dispose();
    _conversationSheetOpen = false;
    _afterStateChanged();
  }

  @override
  Widget build(BuildContext context) {
    final round = _session['current_turn'] ?? 1;
    final maxRounds =
        _publicState['max_rounds'] ?? _session['max_turns'] ?? 6;
    final currentLocation =
        _publicState['current_location_name'] ?? '장소 미상';
    final pending = _pendingQuestion;
    final pendingActor = pending == null
        ? null
        : _characterById(pending['actor_id'] as String?) ??
            _characterByName(pending['actor_name'] as String?);
    final keyboardOpen = MediaQuery.viewInsetsOf(context).bottom > 0;

    return Scaffold(
      resizeToAvoidBottomInset: true,
      appBar: AppBar(
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'ACTIVE CASE',
              style: TextStyle(
                color: AppTheme.muted,
                fontSize: 9,
                fontWeight: FontWeight.w900,
                letterSpacing: 1.4,
              ),
            ),
            const SizedBox(height: 2),
            Text(_session['story_title'] as String? ?? 'ALIBI'),
          ],
        ),
        actions: [
          IconButton(
            tooltip: '현장 지도',
            onPressed: _showMap,
            icon: const Icon(Icons.map_outlined),
          ),
          IconButton(
            tooltip: '등장인물 기록',
            onPressed: _showCharacterDossiers,
            icon: const Icon(Icons.people_alt_outlined),
          ),
          IconButton(
            tooltip: '내 인물 기록',
            onPressed: _showRole,
            icon: const Icon(Icons.badge_outlined),
          ),
          IconButton(
            tooltip: '증거 수첩',
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
            actionsRemaining: _actionsRemaining,
            maxActions: 2,
            location: '$currentLocation',
            onLocationTap: _showCurrentLocation,
          ),
          if (_busy) const LinearProgressIndicator(minHeight: 2),
          if (pending != null && !_completed)
            Card(
              margin: const EdgeInsets.fromLTRB(12, 4, 12, 8),
              child: ListTile(
                leading: PixelAvatar(
                  name: pending['actor_name'] as String? ?? '인물',
                  code: pendingActor?['code'] as String?,
                  size: 42,
                ),
                title: Text(
                  '${pending['actor_name'] ?? '인물'}의 질문',
                ),
                subtitle: Text(pending['question'] as String? ?? ''),
              ),
            ),
          Expanded(
            child: AnimatedSwitcher(
              duration: const Duration(milliseconds: 360),
              switchInCurve: Curves.easeOutCubic,
              switchOutCurve: Curves.easeInCubic,
              child: KeyedSubtree(
                key: ValueKey(_completed ? 'ending' : 'timeline'),
                child: _completed
                    ? _EndingView(state: _state)
                    : _MessageTimeline(
                        messages: _messages,
                        characters: _characters,
                        playerCharacterId: _playerCharacterId,
                      ),
              ),
            ),
          ),
          if (!_completed && _activeConversation == null)
            _ActionComposer(
              disabled:
                  _busy || (!_isPlayerTurn && _pendingQuestion == null),
              answeringLegacyQuestion: _pendingQuestion != null,
              canMove: _isPlayerTurn && _movementRemaining > 0,
              keyboardOpen: keyboardOpen,
              controller: _actionController,
              focusNode: _actionFocus,
              currentActorName: _currentActorName,
              onSubmit: _submitText,
              onMove: _chooseMove,
              onTalk: _startConversation,
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
    required this.actionsRemaining,
    required this.maxActions,
    required this.location,
    required this.onLocationTap,
  });

  final Object round;
  final Object maxRounds;
  final int actionsRemaining;
  final int maxActions;
  final String location;
  final VoidCallback onLocationTap;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(12, 8, 12, 8),
      child: Row(
        children: [
          Expanded(
            flex: 10,
            child: _StatusPill(
              icon: Icons.timelapse,
              label: '라운드 $round/$maxRounds',
            ),
          ),
          const SizedBox(width: 8),
          Expanded(
            flex: 9,
            child: _StatusPill(
              icon: Icons.bolt_outlined,
              label: '행동 $actionsRemaining/$maxActions',
            ),
          ),
          const SizedBox(width: 8),
          Expanded(
            flex: 13,
            child: _StatusPill(
              icon: Icons.place_outlined,
              label: location,
              onTap: onLocationTap,
            ),
          ),
        ],
      ),
    );
  }
}

class _StatusPill extends StatelessWidget {
  const _StatusPill({
    required this.icon,
    required this.label,
    this.onTap,
  });

  final IconData icon;
  final String label;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: const Color(0xFF121418),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(
          color: onTap == null
              ? const Color(0xFF2D3036)
              : AppTheme.brass.withValues(alpha: .38),
        ),
      ),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 11),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(icon, size: 16, color: AppTheme.brass),
              const SizedBox(width: 5),
              Flexible(
                child: Text(
                  label,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.labelLarge,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _SceneCard extends StatelessWidget {
  const _SceneCard({
    required this.locationCode,
    required this.locationName,
    required this.description,
    required this.people,
    required this.adjacentNames,
    required this.onMap,
  });

  final String? locationCode;
  final String locationName;
  final String description;
  final List<Map<String, dynamic>> people;
  final List<String> adjacentNames;
  final VoidCallback onMap;

  @override
  Widget build(BuildContext context) {
    final imageAsset = AppAssets.locationForCode(locationCode);

    return Card(
      margin: const EdgeInsets.fromLTRB(12, 0, 12, 8),
      clipBehavior: Clip.antiAlias,
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (imageAsset != null) ...[
              ClipRRect(
                borderRadius: BorderRadius.circular(8),
                child: AspectRatio(
                  aspectRatio: 4 / 3,
                  child: Image.asset(
                    imageAsset,
                    fit: BoxFit.cover,
                    filterQuality: FilterQuality.none,
                    errorBuilder: (_, _, _) => const SizedBox.shrink(),
                  ),
                ),
              ),
              const SizedBox(height: 12),
            ],
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
            const SizedBox(height: 8),
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
                        avatar: PixelAvatar(
                          name: p['display_name'] as String? ?? '인물',
                          code: p['code'] as String?,
                          size: 24,
                          borderRadius: 4,
                        ),
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

class _MessageTimeline extends StatelessWidget {
  const _MessageTimeline({
    required this.messages,
    required this.characters,
    required this.playerCharacterId,
  });

  final List<Map<String, dynamic>> messages;
  final List<Map<String, dynamic>> characters;
  final String? playerCharacterId;

  Map<String, dynamic>? _character(String? id) {
    if (id == null) return null;
    for (final character in characters) {
      if ('${character['id']}' == id) return character;
    }
    return null;
  }

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
            padding: const EdgeInsets.symmetric(vertical: 7),
            child: Container(
              padding: const EdgeInsets.fromLTRB(12, 11, 14, 11),
              decoration: BoxDecoration(
                color: const Color(0xFF111317),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: const Color(0xFF2B2E34)),
              ),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Padding(
                    padding: EdgeInsets.only(top: 2),
                    child: Icon(
                      Icons.notes_rounded,
                      size: 17,
                      color: AppTheme.brass,
                    ),
                  ),
                  const SizedBox(width: 9),
                  Expanded(
                    child: Text(
                      item['content'] as String? ?? '',
                      style: Theme.of(context).textTheme.bodyMedium,
                    ),
                  ),
                ],
              ),
            ),
          );
        }

        final speakerId = item['speaker_character_id'] as String? ??
            (isPlayer ? playerCharacterId : null);
        final character = _character(speakerId);
        final avatarName =
            character?['display_name'] as String? ?? (isPlayer ? '나' : speaker);
        final avatarCode = character?['code'] as String?;
        final bubble = Container(
          constraints: const BoxConstraints(maxWidth: 300),
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: isPlayer
                ? AppTheme.brass.withValues(alpha: .10)
                : const Color(0xFF171A1F),
            borderRadius: BorderRadius.only(
              topLeft: const Radius.circular(12),
              topRight: const Radius.circular(12),
              bottomLeft: Radius.circular(isPlayer ? 12 : 3),
              bottomRight: Radius.circular(isPlayer ? 3 : 12),
            ),
            border: Border.all(
              color: isPlayer
                  ? AppTheme.brass.withValues(alpha: .28)
                  : const Color(0xFF30333A),
            ),
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
        );

        return Padding(
          padding: const EdgeInsets.symmetric(vertical: 5),
          child: Row(
            mainAxisAlignment:
                isPlayer ? MainAxisAlignment.end : MainAxisAlignment.start,
            crossAxisAlignment: CrossAxisAlignment.end,
            children: isPlayer
                ? [
                    Flexible(child: bubble),
                    const SizedBox(width: 8),
                    PixelAvatar(
                      name: avatarName,
                      code: avatarCode,
                      size: 38,
                    ),
                  ]
                : [
                    PixelAvatar(
                      name: avatarName,
                      code: avatarCode,
                      size: 38,
                    ),
                    const SizedBox(width: 8),
                    Flexible(child: bubble),
                  ],
          ),
        );
      },
    );
  }
}

class _ActionComposer extends StatelessWidget {
  const _ActionComposer({
    required this.disabled,
    required this.answeringLegacyQuestion,
    required this.canMove,
    required this.keyboardOpen,
    required this.controller,
    required this.focusNode,
    required this.currentActorName,
    required this.onSubmit,
    required this.onMove,
    required this.onTalk,
  });

  final bool disabled;
  final bool answeringLegacyQuestion;
  final bool canMove;
  final bool keyboardOpen;
  final TextEditingController controller;
  final FocusNode focusNode;
  final String currentActorName;
  final VoidCallback onSubmit;
  final VoidCallback onMove;
  final VoidCallback onTalk;

  @override
  Widget build(BuildContext context) {
    final hint = answeringLegacyQuestion
        ? '질문에 답변하세요...'
        : disabled
            ? '${currentActorName.isEmpty ? '다른 인물' : currentActorName}의 차례입니다.'
            : '무엇을 할지 기록하세요. 예: 직원용 서랍을 조사한다';

    return SafeArea(
      top: false,
      child: Container(
        padding: EdgeInsets.fromLTRB(
          12,
          8,
          12,
          keyboardOpen ? 6 : 12,
        ),
        decoration: const BoxDecoration(
          color: Color(0xFF0D0F12),
          border: Border(
            top: BorderSide(color: Color(0xFF2B2E34)),
          ),
          boxShadow: [
            BoxShadow(
              color: Color(0x66000000),
              blurRadius: 18,
              offset: Offset(0, -8),
            ),
          ],
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: controller,
              focusNode: focusNode,
              enabled: !disabled || answeringLegacyQuestion,
              minLines: 1,
              maxLines: keyboardOpen ? 2 : 3,
              scrollPadding: EdgeInsets.only(
                bottom: keyboardOpen ? 140 : 24,
              ),
              textInputAction: TextInputAction.send,
              onSubmitted: (_) {
                if (!disabled || answeringLegacyQuestion) onSubmit();
              },
              decoration: InputDecoration(
                hintText: hint,
                prefixIcon: const Icon(Icons.edit_note_outlined),
                suffixIcon: IconButton(
                  onPressed:
                      (!disabled || answeringLegacyQuestion) ? onSubmit : null,
                  icon: const Icon(Icons.north_east),
                ),
              ),
            ),
            if (!answeringLegacyQuestion && !keyboardOpen) ...[
              const SizedBox(height: 8),
              Row(
                children: [
                  Expanded(
                    child: OutlinedButton.icon(
                      onPressed: canMove ? onMove : null,
                      icon: const Icon(Icons.directions_walk),
                      label: const Text('인접 장소 이동'),
                    ),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: OutlinedButton.icon(
                      onPressed: disabled ? null : onTalk,
                      icon: const Icon(Icons.forum_outlined),
                      label: const Text('인물과 대화'),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 4),
              Text(
                '라운드당 행동 2회 · 각 행동 전에 인접 장소 1칸을 무료로 이동할 수 있습니다.',
                style: Theme.of(context).textTheme.bodySmall,
                textAlign: TextAlign.center,
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _EndingView extends StatefulWidget {
  const _EndingView({required this.state});

  final Map<String, dynamic> state;

  @override
  State<_EndingView> createState() => _EndingViewState();
}

class _EndingViewState extends State<_EndingView> {
  bool _truthRevealed = false;

  @override
  Widget build(BuildContext context) {
    final ending = widget.state['ending'] as Map<String, dynamic>?;
    final solution = widget.state['solution'] as Map<String, dynamic>?;
    final verdict =
        widget.state['detective_verdict'] as Map<String, dynamic>?;

    return ListView(
      padding: const EdgeInsets.all(22),
      children: [
        const Icon(Icons.manage_search, size: 68, color: AppTheme.brass),
        const SizedBox(height: 14),
        Text(
          '탐정의 최종 수사 결과',
          textAlign: TextAlign.center,
          style: Theme.of(context).textTheme.headlineMedium,
        ),
        const SizedBox(height: 18),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(18),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  verdict?['detective_name'] as String? ?? '탐정',
                  style: Theme.of(context).textTheme.labelLarge,
                ),
                const SizedBox(height: 8),
                Text(
                  '최종 지목: ${verdict?['accused_name'] ?? '알 수 없는 인물'}',
                  style: Theme.of(context).textTheme.titleLarge,
                ),
                const SizedBox(height: 10),
                Text(
                  verdict?['reasoning'] as String? ??
                      '탐정의 최종 추론을 불러오지 못했습니다.',
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 16),
        if (!_truthRevealed)
          FilledButton.icon(
            onPressed: () => setState(() => _truthRevealed = true),
            icon: const Icon(Icons.visibility_outlined),
            label: const Text('봉인된 진실 열기'),
          ),
        if (_truthRevealed) ...[
          const SizedBox(height: 10),
          const Divider(),
          const SizedBox(height: 12),
          Text(
            ending?['title'] as String? ?? '사건의 결말',
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.headlineSmall,
          ),
          const SizedBox(height: 10),
          Text(
            ending?['ending_text'] as String? ?? '',
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 22),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(18),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '진짜 사건의 진실',
                    style: Theme.of(context).textTheme.titleLarge,
                  ),
                  const SizedBox(height: 10),
                  Text(
                    '실제 범인: ${solution?['culprit_name'] ?? '알 수 없음'}',
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
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
