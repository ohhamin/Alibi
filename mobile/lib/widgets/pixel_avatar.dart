import 'package:flutter/material.dart';

import '../core/app_assets.dart';
import 'sheet_crop_image.dart';

/// Character portrait backed by the generated high-resolution artwork.
///
/// The historical class name is kept so existing game UI call sites do not
/// need to change, but this no longer paints vector/pixel geometry.
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

  static const Map<String, Rect> _crops = {
    // Top row
    'seo-yuna': Rect.fromLTWH(0.017, 0.018, 0.297, 0.396),
    'han-jun': Rect.fromLTWH(0.349, 0.018, 0.297, 0.396),
    'min-seoyeon': Rect.fromLTWH(0.680, 0.018, 0.297, 0.396),
    // Bottom row
    'yoon-jiho': Rect.fromLTWH(0.124, 0.506, 0.325, 0.433),
    'kang-haejin': Rect.fromLTWH(0.552, 0.506, 0.325, 0.433),
  };

  @override
  Widget build(BuildContext context) {
    final crop = _crops[code];
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        color: const Color(0xFF17191D),
        borderRadius: BorderRadius.circular(borderRadius),
        border: Border.all(color: const Color(0xFF3A3630)),
      ),
      clipBehavior: Clip.antiAlias,
      child: crop == null
          ? Center(
              child: Text(
                name.isEmpty ? '?' : name.characters.first,
                style: TextStyle(
                  fontWeight: FontWeight.w800,
                  fontSize: size * .32,
                ),
              ),
            )
          : SheetCropImage(
              asset: AppAssets.characterSheet,
              crop: crop,
              fit: BoxFit.cover,
              filterQuality: FilterQuality.high,
            ),
    );
  }
}
