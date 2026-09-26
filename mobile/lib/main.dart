import 'dart:async';

import 'package:flutter/material.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

import 'core/app_config.dart';
import 'core/app_theme.dart';
import 'screens/home_screen.dart';
import 'screens/login_screen.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Supabase.initialize(
    url: AppConfig.supabaseUrl,
    publishableKey: AppConfig.supabasePublishableKey,
  );
  runApp(const AlibiApp());
}

class AlibiApp extends StatelessWidget {
  const AlibiApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'ALIBI',
      theme: AppTheme.dark,
      home: const SplashGate(),
    );
  }
}

class SplashGate extends StatefulWidget {
  const SplashGate({super.key});

  @override
  State<SplashGate> createState() => _SplashGateState();
}

class _SplashGateState extends State<SplashGate> {
  bool _ready = false;

  @override
  void initState() {
    super.initState();
    Future<void>.delayed(const Duration(milliseconds: 850), () {
      if (mounted) setState(() => _ready = true);
    });
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedSwitcher(
      duration: const Duration(milliseconds: 260),
      switchInCurve: Curves.easeOut,
      switchOutCurve: Curves.easeIn,
      child: _ready
          ? const AuthGate(key: ValueKey('auth'))
          : const Scaffold(
              key: ValueKey('splash'),
              backgroundColor: Color(0xFF08090A),
              body: Center(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(
                      Icons.fingerprint,
                      size: 54,
                      color: AppTheme.brass,
                    ),
                    SizedBox(height: 18),
                    Text(
                      'ALIBI',
                      style: TextStyle(
                        fontSize: 34,
                        fontWeight: FontWeight.w800,
                        letterSpacing: 8,
                      ),
                    ),
                    SizedBox(height: 10),
                    Text(
                      'CASE FILE INITIALIZING',
                      style: TextStyle(
                        color: AppTheme.muted,
                        fontSize: 10,
                        fontWeight: FontWeight.w800,
                        letterSpacing: 1.8,
                      ),
                    ),
                    SizedBox(height: 22),
                    SizedBox(
                      width: 24,
                      height: 24,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    ),
                  ],
                ),
              ),
            ),
    );
  }
}

class AuthGate extends StatefulWidget {
  const AuthGate({super.key});

  @override
  State<AuthGate> createState() => _AuthGateState();
}

class _AuthGateState extends State<AuthGate> {
  StreamSubscription<AuthState>? _authSubscription;
  late bool _signedIn;

  @override
  void initState() {
    super.initState();
    _signedIn = Supabase.instance.client.auth.currentSession != null;
    _authSubscription =
        Supabase.instance.client.auth.onAuthStateChange.listen(
      (data) {
        if (!mounted) return;
        if (data.session != null) {
          setState(() => _signedIn = true);
          return;
        }
        if (data.event == AuthChangeEvent.signedOut) {
          setState(() => _signedIn = false);
        }
      },
      onError: (Object error, StackTrace stackTrace) {
        // A temporary network/auth refresh error must not eject the user
        // from the game. ApiClient will refresh/retry on the next request.
      },
    );
  }

  @override
  void dispose() {
    _authSubscription?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedSwitcher(
      duration: const Duration(milliseconds: 320),
      switchInCurve: Curves.easeOutCubic,
      switchOutCurve: Curves.easeInCubic,
      transitionBuilder: (child, animation) => FadeTransition(
        opacity: animation,
        child: child,
      ),
      child: !_signedIn
          ? const LoginScreen(key: ValueKey('login'))
          : const HomeScreen(key: ValueKey('home')),
    );
  }
}
