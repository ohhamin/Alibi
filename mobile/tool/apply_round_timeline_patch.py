from pathlib import Path

path = Path(__file__).resolve().parents[1] / 'lib' / 'screens' / 'game_screen.dart'
text = path.read_text()

start_marker = 'class _MessageTimeline extends StatelessWidget {'
end_marker = 'class _ActionComposer extends StatelessWidget {'

if 'class _MessageTimeline extends StatefulWidget {' in text:
    print('round timeline already applied')
    raise SystemExit(0)

start = text.find(start_marker)
end = text.find(end_marker)
if start < 0 or end < 0 or end <= start:
    raise SystemExit('message timeline anchors not found')

replacement = r'''class _MessageTimeline extends StatefulWidget {
  const _MessageTimeline({
    required this.messages,
    required this.characters,
    required this.playerCharacterId,
  });

  final List<Map<String, dynamic>> messages;
  final List<Map<String, dynamic>> characters;
  final String? playerCharacterId;

  @override
  State<_MessageTimeline> createState() => _MessageTimelineState();
}

class _MessageTimelineState extends State<_MessageTimeline> {
  final ScrollController _scrollController = ScrollController();
  bool _stickToBottom = true;

  @override
  void initState() {
    super.initState();
    _scrollController.addListener(_trackScrollPosition);
    WidgetsBinding.instance.addPostFrameCallback((_) => _jumpToBottom());
  }

  @override
  void didUpdateWidget(covariant _MessageTimeline oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.messages.length != oldWidget.messages.length && _stickToBottom) {
      WidgetsBinding.instance.addPostFrameCallback((_) => _scrollToBottom());
    }
  }

  @override
  void dispose() {
    _scrollController
      ..removeListener(_trackScrollPosition)
      ..dispose();
    super.dispose();
  }

  void _trackScrollPosition() {
    if (!_scrollController.hasClients) return;
    final position = _scrollController.position;
    _stickToBottom = position.maxScrollExtent - position.pixels <= 96;
  }

  void _jumpToBottom() {
    if (!mounted || !_scrollController.hasClients) return;
    _scrollController.jumpTo(_scrollController.position.maxScrollExtent);
    _stickToBottom = true;
  }

  void _scrollToBottom() {
    if (!mounted || !_scrollController.hasClients) return;
    _scrollController.animateTo(
      _scrollController.position.maxScrollExtent,
      duration: const Duration(milliseconds: 220),
      curve: Curves.easeOutCubic,
    );
  }

  Map<String, dynamic>? _character(String? id) {
    if (id == null) return null;
    for (final character in widget.characters) {
      if ('${character['id']}' == id) return character;
    }
    return null;
  }

  List<Map<String, dynamic>> _timelineEntries() {
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

  Widget _roundHeader(BuildContext context, int roundNo) {
    return Padding(
      padding: EdgeInsets.only(
        top: roundNo == 1 ? 8 : 22,
        bottom: 9,
      ),
      child: Row(
        children: [
          const Expanded(child: Divider(color: Color(0xFF30333A))),
          Container(
            margin: const EdgeInsets.symmetric(horizontal: 10),
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
            decoration: BoxDecoration(
              color: const Color(0xFF171A1F),
              borderRadius: BorderRadius.circular(999),
              border: Border.all(
                color: AppTheme.brass.withValues(alpha: .38),
              ),
            ),
            child: Text(
              '라운드 $roundNo',
              style: Theme.of(context).textTheme.labelLarge?.copyWith(
                    color: AppTheme.brass,
                    fontWeight: FontWeight.w800,
                  ),
            ),
          ),
          const Expanded(child: Divider(color: Color(0xFF30333A))),
        ],
      ),
    );
  }

  Widget _message(BuildContext context, Map<String, dynamic> item) {
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
        (isPlayer ? widget.playerCharacterId : null);
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
  }

  @override
  Widget build(BuildContext context) {
    if (widget.messages.isEmpty) {
      return const Center(child: Text('사건 기록을 불러오는 중입니다.'));
    }

    final entries = _timelineEntries();
    final bottomSafeArea = MediaQuery.viewPaddingOf(context).bottom;
    return ListView.builder(
      controller: _scrollController,
      padding: EdgeInsets.fromLTRB(
        14,
        4,
        14,
        bottomSafeArea + 72,
      ),
      itemCount: entries.length,
      itemBuilder: (context, index) {
        final entry = entries[index];
        if (entry['_type'] == 'round_header') {
          return _roundHeader(context, entry['round_no'] as int);
        }
        return _message(context, entry);
      },
    );
  }
}

'''

text = text[:start] + replacement + text[end:]
path.write_text(text)
print('patched', path)
