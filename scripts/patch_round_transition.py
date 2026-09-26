from pathlib import Path

path = Path('mobile/lib/screens/game_screen.dart')
text = path.read_text(encoding='utf-8')

old = """  bool _submissionSheetOpen = false;\n  bool _finalVoteSheetOpen = false;\n"""
new = """  bool _submissionSheetOpen = false;\n  bool _finalVoteSheetOpen = false;\n  bool _roundTransitionSheetOpen = false;\n  int? _roundTransitionFrom;\n"""
assert old in text, 'round transition field anchor not found'
text = text.replace(old, new, 1)

old = """      final result = await action();\n      success = true;\n      if (mounted) {\n        setState(() {\n          _state = result;\n          if (autoAdvance) {\n"""
new = """      final beforeRound = (_session['current_turn'] as num?)?.toInt() ?? 1;\n      final result = await action();\n      final resultSession =\n          (result['session'] as Map<String, dynamic>?) ?? const {};\n      final afterRound =\n          (resultSession['current_turn'] as num?)?.toInt() ?? beforeRound;\n      final roundAdvanced = resultSession['status'] != 'completed' &&\n          afterRound > beforeRound;\n      success = true;\n      if (mounted) {\n        setState(() {\n          _state = result;\n          if (roundAdvanced) {\n            _roundTransitionFrom = beforeRound;\n          }\n          if (autoAdvance) {\n"""
assert old in text, 'run anchor not found'
text = text.replace(old, new, 1)

old = """  void _afterStateChanged() {\n    if (!mounted || _busy || _completed) return;\n\n    if (_pendingEvidenceSubmission != null && !_submissionSheetOpen) {\n"""
new = """  void _afterStateChanged() {\n    if (!mounted || _busy || _completed) return;\n\n    if (_roundTransitionFrom != null && !_roundTransitionSheetOpen) {\n      WidgetsBinding.instance.addPostFrameCallback((_) {\n        if (mounted &&\n            _roundTransitionFrom != null &&\n            !_roundTransitionSheetOpen) {\n          _openRoundTransitionSheet();\n        }\n      });\n      return;\n    }\n    if (_roundTransitionSheetOpen) return;\n\n    if (_pendingEvidenceSubmission != null && !_submissionSheetOpen) {\n"""
assert old in text, 'after state anchor not found'
text = text.replace(old, new, 1)

old = """            _submissionSheetOpen ||\n            _activeConversation != null ||\n"""
new = """            _submissionSheetOpen ||\n            _roundTransitionSheetOpen ||\n            _roundTransitionFrom != null ||\n            _activeConversation != null ||\n"""
assert old in text, 'auto advance guard anchor not found'
text = text.replace(old, new, 1)

anchor = """  Future<void> _act(\n    String actionType, {\n"""
assert anchor in text, 'act method anchor not found'
method = r'''  Future<void> _openRoundTransitionSheet() async {
    final endedRound = _roundTransitionFrom;
    if (endedRound == null || !mounted) return;

    _roundTransitionSheetOpen = true;
    final nextRound = endedRound + 1;
    final publicEvidenceCount = _clues.length;
    final privateEvidenceCount = _inventoryItems.length;

    await showModalBottomSheet<void>(
      context: context,
      isDismissible: false,
      enableDrag: false,
      isScrollControlled: true,
      builder: (sheetContext) => PopScope(
        canPop: false,
        child: SafeArea(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(22, 18, 22, 24),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Container(
                  width: 46,
                  height: 4,
                  decoration: BoxDecoration(
                    color: const Color(0xFF555A63),
                    borderRadius: BorderRadius.circular(99),
                  ),
                ),
                const SizedBox(height: 26),
                const Icon(
                  Icons.hourglass_bottom_rounded,
                  size: 52,
                  color: AppTheme.brass,
                ),
                const SizedBox(height: 12),
                Text(
                  '라운드 $endedRound 종료',
                  style: Theme.of(sheetContext).textTheme.headlineSmall,
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 7),
                Text(
                  endedRound == 2 || endedRound == 5
                      ? '증거 제출과 탐정의 비공개 취조까지 정리되었습니다.'
                      : '이번 라운드의 행동과 대화가 모두 끝났습니다.',
                  textAlign: TextAlign.center,
                  style: Theme.of(sheetContext).textTheme.bodyMedium,
                ),
                const SizedBox(height: 18),
                Wrap(
                  alignment: WrapAlignment.center,
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    Chip(
                      avatar: const Icon(Icons.public, size: 16),
                      label: Text('공개 증거 $publicEvidenceCount'),
                    ),
                    Chip(
                      avatar: const Icon(Icons.lock_outline, size: 16),
                      label: Text('내 비공개 증거 $privateEvidenceCount'),
                    ),
                    Chip(
                      avatar: const Icon(Icons.flag_outlined, size: 16),
                      label: Text('다음 · 라운드 $nextRound'),
                    ),
                  ],
                ),
                const SizedBox(height: 18),
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(14),
                  decoration: BoxDecoration(
                    color: const Color(0xFF111317),
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(color: const Color(0xFF2B2E34)),
                  ),
                  child: Text(
                    nextRound == 2 || nextRound == 5
                        ? '이번 라운드가 끝나면 탐정 취조 전 증거 1개를 제출하게 됩니다. 어떤 증거를 계속 숨길지 생각해 두세요.'
                        : '지금까지의 대화와 증거를 확인한 뒤 다음 라운드를 시작할 수 있습니다.',
                    textAlign: TextAlign.center,
                  ),
                ),
                const SizedBox(height: 18),
                SizedBox(
                  width: double.infinity,
                  child: FilledButton.icon(
                    onPressed: () => Navigator.pop(sheetContext),
                    icon: const Icon(Icons.arrow_forward),
                    label: Text('라운드 $nextRound 시작'),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );

    _roundTransitionSheetOpen = false;
    if (!mounted) return;
    setState(() => _roundTransitionFrom = null);
    _afterStateChanged();
  }

'''
text = text.replace(anchor, method + anchor, 1)

path.write_text(text, encoding='utf-8')
print('patched round transition interaction')
