import 'package:flutter/material.dart';

import '../core/app_assets.dart';

/// Character portrait backed by an individual generated raster file.
///
/// The historical class name is kept so existing game UI call sites do not
/// need to change. No vector or CustomPainter rendering is used here.
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

    Widget fallback() => Center(
          child: Text(
            name.isEmpty ? '?' : name.substring(0, 1),
            style: TextStyle(
              fontWeight: FontWeight.w800,
              fontSize: size * .32,
            ),
          ),
        );

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
          ? fallback()
          : Image.asset(
              asset,
              fit: BoxFit.cover,
              filterQuality: FilterQuality.high,
              gaplessPlayback: true,
              errorBuilder: (_, _, _) => fallback(),
            ),
    );
  }
}
