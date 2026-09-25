import 'package:flutter/material.dart';

import '../core/app_assets.dart';
import '../core/app_theme.dart';

class PixelAvatar extends StatelessWidget {
  const PixelAvatar({
    super.key,
    required this.name,
    this.code,
    this.size = 42,
    this.borderRadius = 7,
  });

  final String name;
  final String? code;
  final double size;
  final double borderRadius;

  @override
  Widget build(BuildContext context) {
    final asset = AppAssets.characterForCode(code);
    final fallback = name.trim().isEmpty ? '?' : name.trim().characters.first;

    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        color: const Color(0xFF17191D),
        borderRadius: BorderRadius.circular(borderRadius),
        border: Border.all(color: const Color(0xFF3A3630)),
      ),
      clipBehavior: Clip.antiAlias,
      child: asset == null
          ? Center(
              child: Text(
                fallback,
                style: TextStyle(
                  color: AppTheme.paper,
                  fontSize: size * .38,
                  fontWeight: FontWeight.w800,
                ),
              ),
            )
          : Image.asset(
              asset,
              fit: BoxFit.cover,
              filterQuality: FilterQuality.none,
              errorBuilder: (_, _, _) => Center(
                child: Text(
                  fallback,
                  style: TextStyle(
                    color: AppTheme.paper,
                    fontSize: size * .38,
                    fontWeight: FontWeight.w800,
                  ),
                ),
              ),
            ),
    );
  }
}
