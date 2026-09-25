import 'package:flutter/material.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

import '../core/api_client.dart';
import '../core/app_theme.dart';
import '../models/story.dart';
import '../widgets/pixel_avatar.dart';
import 'game_screen.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  final _api = ApiClient();
  bool _loading = true;
  String? _error;
  List<Story> _stories = const [];
  List<Map<String, dynamic>> _sessions = const [];

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final storiesResult = await _api.get('/stories');
      final sessionsResult = await _api.get('/sessions');
      if (!mounted) return;
      setState(() {
        _stories = ((storiesResult['items'] as List?) ?? const [])
            .map((e) => Story.fromJson(e as Map<String, dynamic>))
            .toList();
        _sessions = ((sessionsResult['items'] as List?) ?? const [])
            .cast<Map<String, dynamic>>();
      });
    } catch (e) {
      if (mounted) setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<T> _withGameLoading<T>({
    required String title,
    required String detail,
    required Future<T> Function() action,
  }) async {
    final dialogFuture = showDialog<void>(
      context: context,
      barrierDismissible: false,
      useRootNavigator: true,
      builder: (dialogContext) => PopScope(
        canPop: false,
        child: AlertDialog(
          contentPadding: const EdgeInsets.fromLTRB(24, 26, 24, 24),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const SizedBox(
                width: 42,
                height: 42,
                child: CircularProgressIndicator(strokeWidth: 3),
              ),
              const SizedBox(height: 18),
              Text(
                title,
                textAlign: TextAlign.center,
                style: Theme.of(dialogContext).textTheme.titleLarge,
              ),
              const SizedBox(height: 8),
              Text(
                detail,
                textAlign: TextAlign.center,
                style: Theme.of(dialogContext).textTheme.bodyMedium,
              ),
              const SizedBox(height: 12),
              const Text(
                'ALIBI · CASE PREPARATION',
                style: TextStyle(
                  color: AppTheme.brass,
                  fontSize: 10,
                  fontWeight: FontWeight.w900,
                  letterSpacing: 1.3,
                ),
              ),
            ],
          ),
        ),
      ),
    );

    await Future<void>.delayed(Duration.zero);
    try {
      return await action();
    } finally {
      if (mounted) {
        Navigator.of(context, rootNavigator: true).pop();
      }
      await dialogFuture;
    }
  }

  Future<void> _start(Story story) async {
    final choices = story.characters.where((c) => c.isPlayerSelectable).toList();
    final selected = await showModalBottomSheet<StoryCharacter>(
      context: context,
      isScrollControlled: true,
      builder: (context) => SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(20, 20, 20, 28),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Row(
                children: [
                  Icon(Icons.badge_outlined, size: 18, color: AppTheme.brass),
                  SizedBox(width: 8),
                  Text('PLAYER FILE', style: TextStyle(color: AppTheme.brass, fontSize: 10, fontWeight: FontWeight.w900, letterSpacing: 1.4)),
                ],
              ),
              const SizedBox(height: 8),
              Text('누구의 알리바이로 시작할까?', style: Theme.of(context).textTheme.headlineSmall),
              const SizedBox(height: 8),
              Text('선택한 인물의 실제 행적과 비밀을 알고 플레이합니다. 다른 인물의 진실은 직접 밝혀내야 합니다.', style: Theme.of(context).textTheme.bodySmall),
              const SizedBox(height: 16),
              ...choices.map(
                (c) => Card(
                  child: ListTile(
                    leading: PixelAvatar(
                      name: c.displayName,
                      code: c.code,
                      size: 48,
                    ),
                    title: Text(c.displayName),
                    subtitle: Text('${c.roleLabel}\n${c.publicBio}'),
                    isThreeLine: true,
                    trailing: const Icon(Icons.chevron_right),
                    onTap: () => Navigator.pop(context, c),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
    if (selected == null || !mounted) return;

    try {
      final state = await _withGameLoading<Map<String, dynamic>>(
        title: '사건을 준비하는 중',
        detail: '용의자 상태와 시작 증거품을 배치하고 있습니다.',
        action: () => _api.post(
          '/sessions',
          body: {
            'story_version_id': story.storyVersionId,
            'player_character_id': selected.id,
          },
        ),
      );
      if (!mounted) return;
      await Navigator.push(
        context,
        MaterialPageRoute(builder: (_) => GameScreen(initialState: state)),
      );
      await _load();
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('$e')));
    }
  }

  Future<void> _resume(String sessionId) async {
    try {
      final state = await _withGameLoading<Map<String, dynamic>>(
        title: '수사 기록을 불러오는 중',
        detail: '현재 라운드와 인물들의 기억을 복원하고 있습니다.',
        action: () => _api.get('/sessions/$sessionId'),
      );
      if (!mounted) return;
      await Navigator.push(
        context,
        MaterialPageRoute(builder: (_) => GameScreen(initialState: state)),
      );
      await _load();
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('$e')));
    }
  }

  Future<void> _deleteSession(Map<String, dynamic> session) async {
    final storyTitle = session['story_title'] as String? ?? '저장 게임';
    final playerName = session['player_name'] as String? ?? '';
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('수사 기록 폐기'),
        content: Text(
          "'$storyTitle'${playerName.isEmpty ? '' : ' · $playerName'} 수사 기록을 폐기할까요?\n폐기한 기록은 복구할 수 없습니다.",
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('보관'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('폐기'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;

    try {
      await _api.delete('/sessions/${session['id']}');
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('수사 기록을 폐기했습니다.')),
      );
      await _load();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('$e')));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('ALIBI / INVESTIGATION DESK', style: TextStyle(color: AppTheme.muted, fontSize: 9, fontWeight: FontWeight.w800, letterSpacing: 1.4)),
            SizedBox(height: 2),
            Text('사건 기록실'),
          ],
        ),
        actions: [
          IconButton(onPressed: _load, icon: const Icon(Icons.refresh)),
          IconButton(
            onPressed: () => Supabase.instance.client.auth.signOut(),
            icon: const Icon(Icons.logout),
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: _load,
        child: _loading
            ? ListView(children: const [SizedBox(height: 260), Center(child: CircularProgressIndicator())])
            : _error != null
                ? ListView(
                    padding: const EdgeInsets.all(24),
                    children: [Text(_error!), const SizedBox(height: 12), FilledButton(onPressed: _load, child: const Text('다시 시도'))],
                  )
                : ListView(
                    padding: const EdgeInsets.fromLTRB(18, 8, 18, 40),
                    children: [
                      if (_sessions.any((s) => s['status'] == 'active')) ...[
                        Text('진행 중인 수사', style: Theme.of(context).textTheme.titleLarge),
                        const SizedBox(height: 10),
                        ..._sessions.where((s) => s['status'] == 'active').map(
                              (s) => Padding(
                                padding: const EdgeInsets.only(bottom: 10),
                                child: Card(
                                  child: ListTile(
                                    leading: const Icon(Icons.manage_search, color: AppTheme.brass),
                                    title: Text(s['story_title'] as String? ?? ''),
                                    subtitle: Text('${s['player_name'] ?? ''} · 라운드 ${s['current_turn']}'),
                                    trailing: Row(
                                      mainAxisSize: MainAxisSize.min,
                                      children: [
                                        IconButton(
                                          tooltip: '수사 기록 폐기',
                                          onPressed: () => _deleteSession(s),
                                          icon: const Icon(Icons.delete_outline),
                                        ),
                                        const Icon(Icons.play_arrow),
                                      ],
                                    ),
                                    onTap: () => _resume(s['id'] as String),
                                  ),
                                ),
                              ),
                            ),
                        const SizedBox(height: 24),
                      ],
                      if (_sessions.any((s) => s['status'] != 'active')) ...[
                        Text('종결된 기록', style: Theme.of(context).textTheme.titleLarge),
                        const SizedBox(height: 10),
                        ..._sessions.where((s) => s['status'] != 'active').map(
                              (s) => Padding(
                                padding: const EdgeInsets.only(bottom: 10),
                                child: Card(
                                  child: ListTile(
                                    leading: const Icon(Icons.inventory_2_outlined),
                                    title: Text(s['story_title'] as String? ?? ''),
                                    subtitle: Text('${s['player_name'] ?? ''} · 라운드 ${s['current_turn']} · 종료'),
                                    trailing: IconButton(
                                      tooltip: '수사 기록 폐기',
                                      onPressed: () => _deleteSession(s),
                                      icon: const Icon(Icons.delete_outline),
                                    ),
                                  ),
                                ),
                              ),
                            ),
                        const SizedBox(height: 24),
                      ],
                      Text('사건 보관함', style: Theme.of(context).textTheme.titleLarge),
                      const SizedBox(height: 10),
                      ..._stories.map(
                        (story) => Padding(
                          padding: const EdgeInsets.only(bottom: 14),
                          child: Card(
                            clipBehavior: Clip.antiAlias,
                            child: InkWell(
                              borderRadius: BorderRadius.circular(12),
                              onTap: () => _start(story),
                              child: Padding(
                                padding: const EdgeInsets.all(18),
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Row(
                                      children: [
                                        Expanded(child: Text(story.title, style: Theme.of(context).textTheme.titleLarge)),
                                        const Icon(Icons.chevron_right),
                                      ],
                                    ),
                                    const SizedBox(height: 8),
                                    Text(story.synopsis),
                                    const SizedBox(height: 14),
                                    Wrap(
                                      spacing: 8,
                                      children: [
                                        Chip(label: Text('난이도 ${story.difficulty}')),
                                        if (story.estimatedMinutes != null) Chip(label: Text('약 ${story.estimatedMinutes}분')),
                                        Chip(label: Text('플레이 인물 ${story.characters.where((c) => c.isPlayerSelectable).length}명')),
                                      ],
                                    ),
                                  ],
                                ),
                              ),
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
      ),
    );
  }
}
