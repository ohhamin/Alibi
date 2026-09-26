from pathlib import Path

path = Path(__file__).resolve().parents[1] / 'lib' / 'screens' / 'game_screen.dart'
text = path.read_text()


def replace_once(old: str, new: str, label: str) -> None:
    global text
    if new in text:
        return
    if old not in text:
        raise SystemExit(f'missing patch anchor: {label}')
    text = text.replace(old, new, 1)


replace_once(
    "  bool _submissionSheetOpen = false;\n",
    "  bool _submissionSheetOpen = false;\n  bool _finalVoteSheetOpen = false;\n",
    'final vote field',
)

replace_once(
    "  Map<String, dynamic>? get _activeConversation =>\n      _state['active_conversation'] as Map<String, dynamic>?;\n",
    "  Map<String, dynamic>? get _activeConversation =>\n      _state['active_conversation'] as Map<String, dynamic>?;\n  Map<String, dynamic>? get _pendingFinalVote =>\n      _state['pending_final_vote'] as Map<String, dynamic>?;\n  List<Map<String, dynamic>> get _suspectFinalVotes =>\n      ((_state['suspect_final_votes'] as List?) ?? const [])\n          .cast<Map<String, dynamic>>();\n  Map<String, dynamic>? get _playerOutcome =>\n      _state['player_outcome'] as Map<String, dynamic>?;\n",
    'final vote getters',
)

replace_once(
    "      _pendingEvidenceSubmission == null &&\n      _currentActorId == _playerCharacterId;\n",
    "      _pendingEvidenceSubmission == null &&\n      _pendingFinalVote == null &&\n      _currentActorId == _playerCharacterId;\n",
    'player turn final vote guard',
)

replace_once(
    "    if (_submissionSheetOpen) return;\n\n    if (_activeConversation != null &&\n",
    "    if (_submissionSheetOpen) return;\n\n    if (_pendingFinalVote != null && !_finalVoteSheetOpen) {\n      WidgetsBinding.instance.addPostFrameCallback((_) {\n        if (mounted && _pendingFinalVote != null && !_finalVoteSheetOpen) {\n          _openFinalVoteSheet();\n        }\n      });\n      return;\n    }\n    if (_finalVoteSheetOpen) return;\n\n    if (_activeConversation != null &&\n",
    'auto open final vote',
)

replace_once(
    "    if (_pendingQuestion != null || _pendingEvidenceSubmission != null) return;\n",
    "    if (_pendingQuestion != null ||\n        _pendingEvidenceSubmission != null ||\n        _pendingFinalVote != null) return;\n",
    'auto advance final vote guard',
)

replace_once(
    "            _pendingEvidenceSubmission != null ||\n            _currentActorId == _playerCharacterId) {\n",
    "            _pendingEvidenceSubmission != null ||\n            _pendingFinalVote != null ||\n            _finalVoteSheetOpen ||\n            _currentActorId == _playerCharacterId) {\n",
    'delayed auto advance final vote guard',
)

replace_once(
    "                              '라운드 종료 · 증거 제출',\n",
    "                              '탐정 취조 전 · 증거 제출',\n",
    'submission title',
)

replace_once(
    "                        '현재 소지한 증거 중 1개를 탐정에게 제출해야 합니다. '\n                        '제출한 증거와 아래 의견은 모든 인물에게 공개됩니다. '\n                        '숨기고 싶은 증거가 있다면 다른 증거를 선택하세요.',\n",
    "                        '2·5라운드의 비공개 취조가 시작되기 전에 현재 소지한 증거 중 1개를 탐정에게 제출해야 합니다. '\n                        '제출한 증거와 아래 의견은 모든 인물에게 공개됩니다. '\n                        '나머지 증거는 계속 비공개로 숨길 수 있습니다.',\n",
    'submission description',
)

final_vote_method = r'''  Future<void> _openFinalVoteSheet() async {
    if (_finalVoteSheetOpen || _pendingFinalVote == null || !mounted) return;
    _finalVoteSheetOpen = true;
    final pending = _pendingFinalVote!;
    final candidates = ((pending['candidates'] as List?) ?? const [])
        .cast<Map<String, dynamic>>();
    String? selectedId = candidates.isNotEmpty ? '${candidates.first['id']}' : null;
    String? selectedClueCode;
    final reasonController = TextEditingController();

    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      isDismissible: false,
      enableDrag: false,
      builder: (sheetContext) => PopScope(
        canPop: false,
        child: StatefulBuilder(
          builder: (sheetContext, setSheetState) {
            return SafeArea(
              child: Padding(
                padding: EdgeInsets.fromLTRB(
                  16,
                  16,
                  16,
                  MediaQuery.viewInsetsOf(sheetContext).bottom + 16,
                ),
                child: SizedBox(
                  height: MediaQuery.sizeOf(sheetContext).height * .72,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          const Icon(Icons.how_to_vote_outlined, color: AppTheme.brass),
                          const SizedBox(width: 9),
                          Expanded(
                            child: Text(
                              '최종 예상 범인 제출',
                              style: Theme.of(sheetContext).textTheme.titleLarge,
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 8),
                      const Text(
                        '탐정이 최종 판단을 내리기 전에, 자신과 탐정을 제외한 용의자 중 가장 의심되는 한 명과 이유를 제출하세요. 남은 비공개 증거를 하나 제안할 수도 있습니다.',
                      ),
                      const SizedBox(height: 14),
                      Expanded(
                        child: ListView(
                          children: [
                            ...candidates.map(
                              (candidate) => RadioListTile<String>(
                                value: '${candidate['id']}',
                                groupValue: selectedId,
                                title: Text(candidate['name'] as String? ?? '용의자'),
                                onChanged: _busy
                                    ? null
                                    : (value) => setSheetState(() => selectedId = value),
                              ),
                            ),
                            const SizedBox(height: 8),
                            TextField(
                              controller: reasonController,
                              minLines: 3,
                              maxLines: 6,
                              decoration: const InputDecoration(
                                labelText: '지목 이유',
                                hintText: '대화, 동선, 공개 증거 등을 근거로 적어 주세요.',
                                border: OutlineInputBorder(),
                              ),
                            ),
                            const SizedBox(height: 14),
                            DropdownButtonFormField<String?>(
                              initialValue: null,
                              decoration: const InputDecoration(
                                labelText: '남은 비공개 증거 제안 (선택)',
                                border: OutlineInputBorder(),
                              ),
                              items: [
                                const DropdownMenuItem<String?>(
                                  value: null,
                                  child: Text('제안하지 않음'),
                                ),
                                ..._inventoryItems.map(
                                  (item) => DropdownMenuItem<String?>(
                                    value: item['clue_code'] as String?,
                                    child: Text(
                                      item['title'] as String? ?? '증거',
                                      overflow: TextOverflow.ellipsis,
                                    ),
                                  ),
                                ),
                              ],
                              onChanged: _busy
                                  ? null
                                  : (value) => setSheetState(() => selectedClueCode = value),
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(height: 12),
                      SizedBox(
                        width: double.infinity,
                        child: FilledButton.icon(
                          onPressed: _busy || selectedId == null
                              ? null
                              : () async {
                                  final reason = reasonController.text.trim();
                                  if (reason.isEmpty) {
                                    ScaffoldMessenger.of(sheetContext).showSnackBar(
                                      const SnackBar(content: Text('지목 이유를 입력해 주세요.')),
                                    );
                                    return;
                                  }
                                  await _run(
                                    () => _api.post(
                                      '/sessions/$_sessionId/final-vote',
                                      body: {
                                        'culprit_character_id': selectedId,
                                        'reasoning': reason,
                                        if (selectedClueCode != null)
                                          'clue_code': selectedClueCode,
                                      },
                                    ),
                                  );
                                  if (sheetContext.mounted && _pendingFinalVote == null) {
                                    Navigator.pop(sheetContext);
                                  }
                                },
                          icon: const Icon(Icons.how_to_vote_outlined),
                          label: const Text('최종 의견 제출'),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            );
          },
        ),
      ),
    );
    reasonController.dispose();
    _finalVoteSheetOpen = false;
    _afterStateChanged();
  }

'''
replace_once(
    "  Future<void> _openConversationSheet() async {\n",
    final_vote_method + "  Future<void> _openConversationSheet() async {\n",
    'final vote sheet',
)

replace_once(
    "                title: const Text('라운드 종료 증거 제출 필요'),\n                subtitle: const Text(\n                  '소지 증거 1개를 탐정에게 제출해야 다음 라운드로 진행됩니다.',\n                ),\n",
    "                title: const Text('탐정 취조 전 증거 제출 필요'),\n                subtitle: const Text(\n                  '2·5라운드 비공개 취조 전에 소지 증거 1개를 제출해야 합니다.',\n                ),\n",
    'submission banner',
)

replace_once(
    "          if (pending != null && !_completed)\n",
    "          if (_pendingFinalVote != null && !_completed)\n            Card(\n              margin: const EdgeInsets.fromLTRB(12, 4, 12, 8),\n              child: ListTile(\n                leading: const Icon(Icons.how_to_vote_outlined, color: AppTheme.brass),\n                title: const Text('최종 예상 범인 제출 필요'),\n                subtitle: const Text('탐정의 최종 선택 전에 당신의 예상 범인과 이유를 제출하세요.'),\n                trailing: TextButton(\n                  onPressed: _finalVoteSheetOpen ? null : _openFinalVoteSheet,\n                  child: const Text('선택'),\n                ),\n              ),\n            ),\n          if (pending != null && !_completed)\n",
    'final vote banner',
)

replace_once(
    "          if (!_completed &&\n              _activeConversation == null &&\n              _pendingEvidenceSubmission == null)\n",
    "          if (!_completed &&\n              _activeConversation == null &&\n              _pendingEvidenceSubmission == null &&\n              _pendingFinalVote == null)\n",
    'hide composer during final vote',
)

replace_once(
    "                    final role = dossier['role_label'] as String? ?? '';\n\n                    return Card(\n",
    "                    final role = dossier['role_label'] as String? ?? '';\n                    final relationshipToPlayer =\n                        (dossier['relationship_to_player'] as num?)?.toInt();\n                    final suspicionOfPlayer =\n                        (dossier['suspicion_of_player'] as num?)?.toInt();\n\n                    return Card(\n",
    'social dossier vars',
)

replace_once(
    "                          if (locationName != null &&\n                              locationName.trim().isNotEmpty) ...[\n",
    "                          if (!isPlayer &&\n                              relationshipToPlayer != null &&\n                              suspicionOfPlayer != null) ...[\n                            const SizedBox(height: 12),\n                            Wrap(\n                              spacing: 8,\n                              runSpacing: 6,\n                              children: [\n                                Chip(\n                                  avatar: const Icon(Icons.handshake_outlined, size: 16),\n                                  label: Text('나와의 관계 $relationshipToPlayer'),\n                                ),\n                                Chip(\n                                  avatar: const Icon(Icons.visibility_outlined, size: 16),\n                                  label: Text('나를 의심 $suspicionOfPlayer/100'),\n                                ),\n                              ],\n                            ),\n                          ],\n                          if (locationName != null &&\n                              locationName.trim().isNotEmpty) ...[\n",
    'social dossier chips',
)

start = text.find('class _EndingView extends StatefulWidget {')
end = text.find('class _EvidenceThumb extends StatelessWidget {', start)
if start < 0 or end < 0:
    raise SystemExit('missing ending view range')
new_ending = r'''class _EndingView extends StatefulWidget {
  const _EndingView({required this.state});

  final Map<String, dynamic> state;

  @override
  State<_EndingView> createState() => _EndingViewState();
}

class _EndingViewState extends State<_EndingView> {
  bool _detectiveRevealed = false;
  bool _truthRevealed = false;

  @override
  Widget build(BuildContext context) {
    final ending = widget.state['ending'] as Map<String, dynamic>?;
    final solution = widget.state['solution'] as Map<String, dynamic>?;
    final verdict = widget.state['detective_verdict'] as Map<String, dynamic>?;
    final outcome = widget.state['player_outcome'] as Map<String, dynamic>?;
    final votes = ((widget.state['suspect_final_votes'] as List?) ?? const [])
        .cast<Map<String, dynamic>>();
    final rawReasoning = (verdict?['reasoning'] as String? ?? '').trim();

    return ListView(
      padding: const EdgeInsets.fromLTRB(20, 22, 20, 42),
      children: [
        const Icon(Icons.how_to_vote_outlined, size: 62, color: AppTheme.brass),
        const SizedBox(height: 12),
        Text(
          '용의자들의 최종 선택',
          textAlign: TextAlign.center,
          style: Theme.of(context).textTheme.headlineMedium,
        ),
        const SizedBox(height: 6),
        const Text(
          '탐정의 최종 지목 전에 각 용의자가 남긴 예상 범인과 이유입니다.',
          textAlign: TextAlign.center,
        ),
        const SizedBox(height: 18),
        if (votes.isEmpty)
          const Card(
            child: Padding(
              padding: EdgeInsets.all(18),
              child: Text('정리된 용의자 최종 의견이 없습니다.'),
            ),
          )
        else
          ...votes.map((vote) {
            final evidence = vote['suggested_evidence'] as Map<String, dynamic>?;
            return Card(
              margin: const EdgeInsets.only(bottom: 10),
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Expanded(
                          child: Text(
                            '${vote['voter_name'] ?? '용의자'}의 선택',
                            style: Theme.of(context).textTheme.titleMedium,
                          ),
                        ),
                        if (vote['is_player'] == true)
                          const Chip(label: Text('나')),
                      ],
                    ),
                    const SizedBox(height: 7),
                    Text(
                      '예상 범인 · ${vote['accused_name'] ?? '알 수 없음'}',
                      style: Theme.of(context).textTheme.labelLarge,
                    ),
                    const SizedBox(height: 6),
                    Text(vote['reasoning'] as String? ?? ''),
                    if (evidence != null) ...[
                      const SizedBox(height: 10),
                      Container(
                        width: double.infinity,
                        padding: const EdgeInsets.all(10),
                        decoration: BoxDecoration(
                          color: const Color(0xFF0E1013),
                          borderRadius: BorderRadius.circular(8),
                          border: Border.all(color: const Color(0xFF2D3036)),
                        ),
                        child: Text(
                          '남은 증거 제안 · ${evidence['title'] ?? '증거'}\n${evidence['content'] ?? ''}',
                        ),
                      ),
                    ],
                  ],
                ),
              ),
            );
          }),
        const SizedBox(height: 12),
        if (!_detectiveRevealed)
          FilledButton.icon(
            onPressed: () => setState(() => _detectiveRevealed = true),
            icon: const Icon(Icons.manage_search),
            label: const Text('탐정의 선택 보기'),
          ),
        if (_detectiveRevealed) ...[
          const SizedBox(height: 18),
          Container(
            width: double.infinity,
            padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 20),
            decoration: BoxDecoration(
              color: AppTheme.brass.withValues(alpha: .08),
              borderRadius: BorderRadius.circular(14),
              border: Border.all(color: AppTheme.brass.withValues(alpha: .30)),
            ),
            child: Column(
              children: [
                Text(
                  outcome?['label'] as String? ?? '결과',
                  style: Theme.of(context).textTheme.headlineLarge,
                ),
                const SizedBox(height: 5),
                Text(
                  outcome?['message'] as String? ?? '',
                  textAlign: TextAlign.center,
                ),
              ],
            ),
          ),
          const SizedBox(height: 12),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(18),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '탐정의 최종 선택',
                    style: Theme.of(context).textTheme.titleLarge,
                  ),
                  const SizedBox(height: 8),
                  Text(
                    '${verdict?['detective_name'] ?? '탐정'}의 최종 지목 · ${verdict?['accused_name'] ?? '알 수 없는 인물'}',
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                  const SizedBox(height: 14),
                  Text(
                    '판단 근거',
                    style: Theme.of(context).textTheme.labelLarge,
                  ),
                  const SizedBox(height: 6),
                  Text(
                    rawReasoning.isEmpty
                        ? '탐정의 상세 판단 근거를 불러오지 못했습니다.'
                        : rawReasoning,
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 12),
          if (!_truthRevealed)
            FilledButton.icon(
              onPressed: () => setState(() => _truthRevealed = true),
              icon: const Icon(Icons.visibility_outlined),
              label: const Text('사건의 진실 보기'),
            ),
        ],
        if (_truthRevealed) ...[
          const SizedBox(height: 18),
          const Divider(),
          const SizedBox(height: 12),
          Text(
            '사건의 진실',
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.headlineSmall,
          ),
          const SizedBox(height: 12),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(18),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '실제 범인 · ${solution?['culprit_name'] ?? '알 수 없음'}',
                    style: Theme.of(context).textTheme.titleLarge,
                  ),
                  const SizedBox(height: 10),
                  Text(solution?['canonical_explanation'] as String? ?? ''),
                  if ((ending?['ending_text'] as String? ?? '').isNotEmpty) ...[
                    const SizedBox(height: 14),
                    Text(
                      ending?['title'] as String? ?? '사건의 결말',
                      style: Theme.of(context).textTheme.titleMedium,
                    ),
                    const SizedBox(height: 6),
                    Text(ending?['ending_text'] as String? ?? ''),
                  ],
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

'''
text = text[:start] + new_ending + text[end:]

path.write_text(text)
print('patched', path)
