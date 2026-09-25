import 'package:flutter/material.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

import '../core/app_theme.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _email = TextEditingController();
  final _password = TextEditingController();
  bool _signup = false;
  bool _loading = false;

  @override
  void dispose() {
    _email.dispose();
    _password.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final email = _email.text.trim();
    final password = _password.text;
    if (email.isEmpty || password.length < 6) {
      _show('이메일과 6자 이상의 비밀번호를 입력하세요.');
      return;
    }
    setState(() => _loading = true);
    try {
      if (_signup) {
        await Supabase.instance.client.auth.signUp(
          email: email,
          password: password,
        );
        if (mounted) {
          _show('가입 요청이 완료되었습니다. 이메일 확인 설정에 따라 인증 후 로그인하세요.');
        }
      } else {
        await Supabase.instance.client.auth.signInWithPassword(
          email: email,
          password: password,
        );
      }
    } on AuthException catch (e) {
      if (mounted) _show(e.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  void _show(String message) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message)),
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      body: Stack(
        children: [
          const Positioned.fill(child: _CaseBackdrop()),
          SafeArea(
            child: Center(
              child: SingleChildScrollView(
                padding: const EdgeInsets.fromLTRB(24, 28, 24, 32),
                child: ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 440),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      const _AlibiMark(),
                      const SizedBox(height: 28),
                      Text(
                        'ALIBI',
                        textAlign: TextAlign.center,
                        style: theme.textTheme.displaySmall,
                      ),
                      const SizedBox(height: 8),
                      Text(
                        '말 한마디, 숨긴 한 장면.\n당신의 알리바이가 사건의 결말을 바꿉니다.',
                        textAlign: TextAlign.center,
                        style: theme.textTheme.bodyMedium?.copyWith(
                          color: AppTheme.muted,
                        ),
                      ),
                      const SizedBox(height: 34),
                      Container(
                        padding: const EdgeInsets.fromLTRB(20, 20, 20, 18),
                        decoration: BoxDecoration(
                          color: AppTheme.surface.withValues(alpha: .92),
                          borderRadius: BorderRadius.circular(20),
                          border: Border.all(
                            color: const Color(0xFF2D3036),
                          ),
                          boxShadow: const [
                            BoxShadow(
                              color: Color(0x66000000),
                              blurRadius: 30,
                              offset: Offset(0, 16),
                            ),
                          ],
                        ),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            Row(
                              children: [
                                const Icon(
                                  Icons.lock_outline,
                                  color: AppTheme.brass,
                                  size: 20,
                                ),
                                const SizedBox(width: 8),
                                Text(
                                  _signup ? '수사 기록 등록' : '수사 기록 접근',
                                  style: theme.textTheme.titleMedium,
                                ),
                              ],
                            ),
                            const SizedBox(height: 6),
                            Text(
                              _signup
                                  ? '새 조사관 계정을 만들고 사건 기록을 시작합니다.'
                                  : '계정을 확인한 뒤 마지막 수사 기록으로 돌아갑니다.',
                              style: theme.textTheme.bodySmall,
                            ),
                            const SizedBox(height: 20),
                            TextField(
                              controller: _email,
                              keyboardType: TextInputType.emailAddress,
                              autofillHints: const [AutofillHints.email],
                              decoration: const InputDecoration(
                                labelText: '이메일',
                                prefixIcon: Icon(Icons.alternate_email),
                              ),
                            ),
                            const SizedBox(height: 12),
                            TextField(
                              controller: _password,
                              obscureText: true,
                              autofillHints: const [AutofillHints.password],
                              onSubmitted: (_) => _submit(),
                              decoration: const InputDecoration(
                                labelText: '비밀번호',
                                prefixIcon: Icon(Icons.key_outlined),
                              ),
                            ),
                            const SizedBox(height: 16),
                            AnimatedSwitcher(
                              duration: const Duration(milliseconds: 180),
                              child: FilledButton.icon(
                                key: ValueKey(_loading),
                                onPressed: _loading ? null : _submit,
                                icon: _loading
                                    ? const SizedBox(
                                        width: 18,
                                        height: 18,
                                        child: CircularProgressIndicator(
                                          strokeWidth: 2,
                                        ),
                                      )
                                    : Icon(
                                        _signup
                                            ? Icons.person_add_alt_1
                                            : Icons.fingerprint,
                                      ),
                                label: Text(
                                  _loading
                                      ? '확인 중…'
                                      : (_signup ? '기록 등록하기' : '신원 확인'),
                                ),
                              ),
                            ),
                            const SizedBox(height: 4),
                            TextButton(
                              onPressed: _loading
                                  ? null
                                  : () => setState(() => _signup = !_signup),
                              child: Text(
                                _signup
                                    ? '이미 사건 기록이 있습니다'
                                    : '처음이라면 조사관 등록',
                              ),
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(height: 18),
                      Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          const Icon(
                            Icons.visibility_outlined,
                            size: 15,
                            color: AppTheme.muted,
                          ),
                          const SizedBox(width: 6),
                          Text(
                            '사건의 진실은 플레이가 끝날 때까지 봉인됩니다.',
                            style: theme.textTheme.bodySmall,
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _AlibiMark extends StatelessWidget {
  const _AlibiMark();

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Container(
        width: 82,
        height: 82,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          color: const Color(0xFF14171B),
          border: Border.all(color: AppTheme.brass.withValues(alpha: .75)),
          boxShadow: const [
            BoxShadow(
              color: Color(0x33000000),
              blurRadius: 20,
              offset: Offset(0, 10),
            ),
          ],
        ),
        child: const Icon(
          Icons.fingerprint,
          size: 44,
          color: AppTheme.brass,
        ),
      ),
    );
  }
}

class _CaseBackdrop extends StatelessWidget {
  const _CaseBackdrop();

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: const BoxDecoration(
        gradient: RadialGradient(
          center: Alignment(-.2, -.45),
          radius: 1.15,
          colors: [
            Color(0xFF1A1B1E),
            Color(0xFF0D0E10),
            Color(0xFF08090A),
          ],
        ),
      ),
      child: CustomPaint(painter: _CaseLinePainter()),
    );
  }
}

class _CaseLinePainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = const Color(0x0FC8A96A)
      ..strokeWidth = 1;

    const gap = 42.0;
    for (double y = 18; y < size.height; y += gap) {
      canvas.drawLine(Offset(0, y), Offset(size.width, y), paint);
    }

    final vertical = Paint()
      ..color = const Color(0x083A3D43)
      ..strokeWidth = 1;
    for (double x = 24; x < size.width; x += 72) {
      canvas.drawLine(Offset(x, 0), Offset(x, size.height), vertical);
    }
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
