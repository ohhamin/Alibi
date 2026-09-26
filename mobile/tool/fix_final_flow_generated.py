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

old = """                            ...candidates.map(
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
new = """                            ...candidates.map((candidate) {
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
if old not in text:
    raise SystemExit('missing generated candidate selector')
text = text.replace(old, new, 1)
path.write_text(text)
print('fixed', path)
