import 'package:flutter/material.dart';

class AppTheme {
  AppTheme._();

  static const background = Color(0xFF0A0B0D);
  static const surface = Color(0xFF111317);
  static const surfaceHigh = Color(0xFF191C21);
  static const brass = Color(0xFFC8A96A);
  static const paper = Color(0xFFE8E0D0);
  static const muted = Color(0xFF9A958B);
  static const danger = Color(0xFFC97979);

  static ThemeData get dark {
    const scheme = ColorScheme.dark(
      primary: brass,
      onPrimary: Color(0xFF211A0D),
      primaryContainer: Color(0xFF3A2F1B),
      onPrimaryContainer: Color(0xFFF1DDAF),
      secondary: Color(0xFFA6AEBB),
      onSecondary: Color(0xFF171A1F),
      secondaryContainer: Color(0xFF252A31),
      onSecondaryContainer: Color(0xFFE1E6ED),
      error: danger,
      onError: Color(0xFF2A0A0A),
      surface: surface,
      onSurface: paper,
      surfaceContainerHighest: surfaceHigh,
      onSurfaceVariant: Color(0xFFB8B2A8),
      outline: Color(0xFF3A3D43),
      outlineVariant: Color(0xFF292C31),
      shadow: Colors.black,
      scrim: Colors.black,
    );

    final base = ThemeData(
      useMaterial3: true,
      brightness: Brightness.dark,
      colorScheme: scheme,
      scaffoldBackgroundColor: background,
      fontFamily: null,
    );

    final text = base.textTheme.copyWith(
      displaySmall: base.textTheme.displaySmall?.copyWith(
        fontWeight: FontWeight.w800,
        letterSpacing: 4,
        color: paper,
      ),
      headlineMedium: base.textTheme.headlineMedium?.copyWith(
        fontWeight: FontWeight.w800,
        letterSpacing: -.4,
        color: paper,
      ),
      headlineSmall: base.textTheme.headlineSmall?.copyWith(
        fontWeight: FontWeight.w800,
        letterSpacing: -.3,
        color: paper,
      ),
      titleLarge: base.textTheme.titleLarge?.copyWith(
        fontWeight: FontWeight.w800,
        letterSpacing: -.2,
        color: paper,
      ),
      titleMedium: base.textTheme.titleMedium?.copyWith(
        fontWeight: FontWeight.w700,
        color: paper,
      ),
      bodyLarge: base.textTheme.bodyLarge?.copyWith(
        height: 1.5,
        color: paper,
      ),
      bodyMedium: base.textTheme.bodyMedium?.copyWith(
        height: 1.5,
        color: const Color(0xFFD0CAC0),
      ),
      bodySmall: base.textTheme.bodySmall?.copyWith(
        height: 1.45,
        color: muted,
      ),
      labelLarge: base.textTheme.labelLarge?.copyWith(
        fontWeight: FontWeight.w700,
        letterSpacing: .1,
      ),
      labelMedium: base.textTheme.labelMedium?.copyWith(
        fontWeight: FontWeight.w700,
        color: muted,
      ),
    );

    const rounded = BorderRadius.all(Radius.circular(16));
    const compactRounded = BorderRadius.all(Radius.circular(12));

    return base.copyWith(
      textTheme: text,
      scaffoldBackgroundColor: background,
      pageTransitionsTheme: const PageTransitionsTheme(
        builders: {
          TargetPlatform.android: _MysteryPageTransitionsBuilder(),
          TargetPlatform.iOS: _MysteryPageTransitionsBuilder(),
          TargetPlatform.macOS: _MysteryPageTransitionsBuilder(),
          TargetPlatform.windows: _MysteryPageTransitionsBuilder(),
          TargetPlatform.linux: _MysteryPageTransitionsBuilder(),
        },
      ),
      appBarTheme: const AppBarTheme(
        elevation: 0,
        scrolledUnderElevation: 0,
        backgroundColor: background,
        foregroundColor: paper,
        centerTitle: false,
        surfaceTintColor: Colors.transparent,
        titleTextStyle: TextStyle(
          color: paper,
          fontSize: 18,
          fontWeight: FontWeight.w800,
          letterSpacing: -.2,
        ),
      ),
      cardTheme: const CardThemeData(
        margin: EdgeInsets.zero,
        elevation: 0,
        color: surface,
        surfaceTintColor: Colors.transparent,
        shape: RoundedRectangleBorder(
          borderRadius: rounded,
          side: BorderSide(color: Color(0xFF2B2E34)),
        ),
      ),
      dialogTheme: const DialogThemeData(
        backgroundColor: surface,
        surfaceTintColor: Colors.transparent,
        shape: RoundedRectangleBorder(borderRadius: rounded),
      ),
      bottomSheetTheme: const BottomSheetThemeData(
        backgroundColor: surface,
        modalBackgroundColor: surface,
        surfaceTintColor: Colors.transparent,
        showDragHandle: true,
        dragHandleColor: Color(0xFF4A4D53),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
        ),
      ),
      inputDecorationTheme: const InputDecorationTheme(
        filled: true,
        fillColor: Color(0xFF0D0F12),
        contentPadding: EdgeInsets.symmetric(horizontal: 16, vertical: 15),
        hintStyle: TextStyle(color: Color(0xFF777A80)),
        labelStyle: TextStyle(color: Color(0xFFAAA49A)),
        floatingLabelStyle: TextStyle(color: brass),
        prefixIconColor: Color(0xFF8F8A82),
        suffixIconColor: Color(0xFF8F8A82),
        border: OutlineInputBorder(
          borderRadius: compactRounded,
          borderSide: BorderSide(color: Color(0xFF36393F)),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: compactRounded,
          borderSide: BorderSide(color: Color(0xFF36393F)),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: compactRounded,
          borderSide: BorderSide(color: brass, width: 1.4),
        ),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          backgroundColor: brass,
          foregroundColor: const Color(0xFF201A0E),
          disabledBackgroundColor: const Color(0xFF303238),
          disabledForegroundColor: const Color(0xFF777A80),
          minimumSize: const Size(48, 50),
          padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 14),
          shape: const RoundedRectangleBorder(borderRadius: compactRounded),
          textStyle: const TextStyle(fontWeight: FontWeight.w800),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: paper,
          minimumSize: const Size(48, 48),
          side: const BorderSide(color: Color(0xFF3A3D43)),
          shape: const RoundedRectangleBorder(borderRadius: compactRounded),
          textStyle: const TextStyle(fontWeight: FontWeight.w700),
        ),
      ),
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(
          foregroundColor: brass,
          textStyle: const TextStyle(fontWeight: FontWeight.w700),
        ),
      ),
      iconButtonTheme: IconButtonThemeData(
        style: IconButton.styleFrom(
          foregroundColor: const Color(0xFFC9C4BB),
          highlightColor: const Color(0x22C8A96A),
        ),
      ),
      chipTheme: base.chipTheme.copyWith(
        backgroundColor: const Color(0xFF17191E),
        selectedColor: const Color(0xFF30291B),
        side: const BorderSide(color: Color(0xFF31343A)),
        labelStyle: const TextStyle(
          color: Color(0xFFC9C4BB),
          fontWeight: FontWeight.w700,
        ),
        shape: const RoundedRectangleBorder(borderRadius: compactRounded),
      ),
      dividerTheme: const DividerThemeData(
        color: Color(0xFF292C31),
        thickness: 1,
        space: 1,
      ),
      snackBarTheme: const SnackBarThemeData(
        backgroundColor: Color(0xFF202329),
        contentTextStyle: TextStyle(color: paper),
        behavior: SnackBarBehavior.floating,
        elevation: 0,
        shape: RoundedRectangleBorder(borderRadius: compactRounded),
      ),
      progressIndicatorTheme: const ProgressIndicatorThemeData(
        color: brass,
        linearTrackColor: Color(0xFF26282D),
      ),
      badgeTheme: const BadgeThemeData(
        backgroundColor: brass,
        textColor: Color(0xFF201A0E),
      ),
    );
  }
}

class _MysteryPageTransitionsBuilder extends PageTransitionsBuilder {
  const _MysteryPageTransitionsBuilder();

  @override
  Widget buildTransitions<T>(
    PageRoute<T> route,
    BuildContext context,
    Animation<double> animation,
    Animation<double> secondaryAnimation,
    Widget child,
  ) {
    final curve = CurvedAnimation(
      parent: animation,
      curve: Curves.easeOutCubic,
      reverseCurve: Curves.easeInCubic,
    );
    final fade = Tween<double>(begin: 0, end: 1).animate(curve);
    final slide = Tween<Offset>(
      begin: const Offset(0, .025),
      end: Offset.zero,
    ).animate(curve);

    return FadeTransition(
      opacity: fade,
      child: SlideTransition(position: slide, child: child),
    );
  }
}
