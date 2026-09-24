import 'package:flutter/material.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

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
        await Supabase.instance.client.auth.signUp(email: email, password: password);
        if (mounted) _show('가입 요청이 완료되었습니다. 이메일 확인 설정에 따라 인증 후 로그인하세요.');
      } else {
        await Supabase.instance.client.auth.signInWithPassword(email: email, password: password);
      }
    } on AuthException catch (e) {
      if (mounted) _show(e.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  void _show(String message) {
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(28),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const Icon(Icons.fingerprint, size: 72),
                  const SizedBox(height: 20),
                  Text('ALIBI', style: Theme.of(context).textTheme.displaySmall, textAlign: TextAlign.center),
                  const SizedBox(height: 8),
                  const Text('당신의 말 한마디가 알리바이를 바꾼다.', textAlign: TextAlign.center),
                  const SizedBox(height: 36),
                  TextField(
                    controller: _email,
                    keyboardType: TextInputType.emailAddress,
                    decoration: const InputDecoration(labelText: '이메일', border: OutlineInputBorder()),
                  ),
                  const SizedBox(height: 12),
                  TextField(
                    controller: _password,
                    obscureText: true,
                    onSubmitted: (_) => _submit(),
                    decoration: const InputDecoration(labelText: '비밀번호', border: OutlineInputBorder()),
                  ),
                  const SizedBox(height: 16),
                  FilledButton(
                    onPressed: _loading ? null : _submit,
                    child: Text(_loading ? '처리 중…' : (_signup ? '가입하기' : '로그인')),
                  ),
                  TextButton(
                    onPressed: _loading ? null : () => setState(() => _signup = !_signup),
                    child: Text(_signup ? '이미 계정이 있어요' : '처음이라면 계정 만들기'),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
