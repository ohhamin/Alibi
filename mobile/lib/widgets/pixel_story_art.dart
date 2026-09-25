import 'package:flutter/material.dart';

import '../core/app_assets.dart';
import 'sheet_crop_image.dart';

/// Location/evidence artwork backed only by generated raster image files.
///
/// The old class names are retained for compatibility with existing game UI.
class PixelLocationArt extends StatelessWidget {
  const PixelLocationArt({
    super.key,
    required this.locationCode,
    this.height = 220,
  });

  final String? locationCode;
  final double height;

  @override
  Widget build(BuildContext context) {
    final asset = AppAssets.locationForCode(locationCode) ??
        AppAssets.locationForCode('hall')!;

    return ClipRRect(
      borderRadius: BorderRadius.circular(10),
      child: SizedBox(
        width: double.infinity,
        height: height,
        child: Image.asset(
          asset,
          fit: BoxFit.cover,
          filterQuality: FilterQuality.high,
          gaplessPlayback: true,
        ),
      ),
    );
  }
}

class PixelEvidenceArt extends StatelessWidget {
  const PixelEvidenceArt({
    super.key,
    required this.clueCode,
    this.size = 48,
  });

  final String? clueCode;
  final double size;

  // 2560 x 1024 raster board: five 512px evidence images per row.
  static const Map<String, Rect> _crops = {
    'clue-safe-key': Rect.fromLTWH(0.0, 0.0, 0.2, 0.5),
    'clue-coffee-receipt': Rect.fromLTWH(0.2, 0.0, 0.2, 0.5),
    'clue-expense': Rect.fromLTWH(0.4, 0.0, 0.2, 0.5),
    'clue-bookend': Rect.fromLTWH(0.6, 0.0, 0.2, 0.5),
    'clue-contract': Rect.fromLTWH(0.8, 0.0, 0.2, 0.5),
    'clue-door-lock': Rect.fromLTWH(0.0, 0.5, 0.2, 0.5),
    'clue-drain-button': Rect.fromLTWH(0.2, 0.5, 0.2, 0.5),
    'clue-manuscript': Rect.fromLTWH(0.4, 0.5, 0.2, 0.5),
    'clue-body-time': Rect.fromLTWH(0.6, 0.5, 0.2, 0.5),
    'clue-brass-dust': Rect.fromLTWH(0.8, 0.5, 0.2, 0.5),
  };

  @override
  Widget build(BuildContext context) {
    final crop = _crops[clueCode] ?? _crops['clue-safe-key']!;

    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        color: const Color(0xFF171A1F),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: const Color(0xFF343840)),
      ),
      clipBehavior: Clip.antiAlias,
      child: SheetCropImage(
        asset: AppAssets.evidenceSheet,
        crop: crop,
        sheetWidth: 2560,
        sheetHeight: 1024,
        fit: BoxFit.cover,
        filterQuality: FilterQuality.high,
      ),
    );
  }
}
