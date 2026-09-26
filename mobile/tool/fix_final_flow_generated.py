from pathlib import Path

path = Path(__file__).resolve().parents[1] / 'lib' / 'screens' / 'game_screen.dart'
text = path.read_text()

unused = """  List<Map<String, dynamic>> get _suspectFinalVotes =>
      ((_state['suspect_final_votes'] as List?) ?? const [])
          .cast<Map<String, dynamic>>();
  Map<String, dynamic>? get _playerOutcome =>
      _state['player_outcome'] as Map<String, dynamic>?;
"""
text = text.replace(unused, '')

old_selector = """                            ...candidates.map(
                              (candidate) => RadioListTile<String>(
                                value: '${candidate['id']}',
                                groupValue: selectedId,
                                title: Text(candidate['name'] as String? ?? '용의자'),
                                onChanged: _busy
                                    ? null
                                    : (value) => setSheetState(() => selectedId = value),
                              ),
                            ),
"""
new_selector = """                            ...candidates.map((candidate) {
                              final candidateId = '${candidate['id']}';
                              final selected = candidateId == selectedId;
                              return ListTile(
                                leading: Icon(
                                  selected
                                      ? Icons.radio_button_checked
                                      : Icons.radio_button_unchecked,
                                  color: selected ? AppTheme.brass : null,
                                ),
                                title: Text(
                                  candidate['name'] as String? ?? '용의자',
                                ),
                                selected: selected,
                                onTap: _busy
                                    ? null
                                    : () => setSheetState(
                                          () => selectedId = candidateId,
                                        ),
                              );
                            }),
"""
if old_selector in text:
    text = text.replace(old_selector, new_selector, 1)
elif new_selector not in text:
    raise SystemExit('missing generated candidate selector')

old_guard = """    if (_pendingQuestion != null ||
        _pendingEvidenceSubmission != null ||
        _pendingFinalVote != null) return;
    if (_autoAdvancePaused) return;
"""
new_guard = """    if (_pendingQuestion != null ||
        _pendingEvidenceSubmission != null ||
        _pendingFinalVote != null) {
      return;
    }
    if (_autoAdvancePaused) {
      return;
    }
"""
if old_guard in text:
    text = text.replace(old_guard, new_guard, 1)

old_body = """                                      body: {
                                        'culprit_character_id': selectedId,
                                        'reasoning': reason,
                                        if (selectedClueCode != null)
                                          'clue_code': selectedClueCode,
                                      },
"""
new_body = """                                      body: {
                                        'culprit_character_id': selectedId,
                                        'reasoning': reason,
                                        'clue_code': ?selectedClueCode,
                                      },
"""
if old_body in text:
    text = text.replace(old_body, new_body, 1)

path.write_text(text)
print('fixed', path)
