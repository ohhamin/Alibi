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
  static const Map<String, Rect> _coreCrops = {
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

  // 1600 x 640 extra board: five 320px generated evidence images per row.
  // Several low-priority/ambient clues intentionally reuse a close visual.
  static const Map<String, Rect> _extraCrops = {
    // Row 1
    'clue-expense': Rect.fromLTWH(0.0, 0.0, 0.2, 0.5),
    'clue-irrelevant-lottery-ticket': Rect.fromLTWH(0.0, 0.0, 0.2, 0.5),
    'clue-irrelevant-tea-wrapper': Rect.fromLTWH(0.0, 0.0, 0.2, 0.5),
    'clue-irrelevant-toner-invoice': Rect.fromLTWH(0.0, 0.0, 0.2, 0.5),
    'clue-manuscript': Rect.fromLTWH(0.2, 0.0, 0.2, 0.5),
    'clue-han-cancel-contract': Rect.fromLTWH(0.4, 0.0, 0.2, 0.5),
    'clue-jiho-debt-letter': Rect.fromLTWH(0.4, 0.0, 0.2, 0.5),
    'clue-jiho-insurance': Rect.fromLTWH(0.4, 0.0, 0.2, 0.5),
    'clue-safe-key': Rect.fromLTWH(0.6, 0.0, 0.2, 0.5),
    'clue-irrelevant-coin-battery': Rect.fromLTWH(0.6, 0.0, 0.2, 0.5),
    'clue-irrelevant-raffle-ticket': Rect.fromLTWH(0.8, 0.0, 0.2, 0.5),
    'clue-irrelevant-event-badge': Rect.fromLTWH(0.8, 0.0, 0.2, 0.5),
    'clue-irrelevant-old-photo': Rect.fromLTWH(0.8, 0.0, 0.2, 0.5),

    // Row 2
    'clue-irrelevant-return-label': Rect.fromLTWH(0.0, 0.5, 0.2, 0.5),
    'clue-irrelevant-milk-label': Rect.fromLTWH(0.0, 0.5, 0.2, 0.5),
    'clue-irrelevant-umbrella-tag': Rect.fromLTWH(0.0, 0.5, 0.2, 0.5),
    'clue-irrelevant-loyalty-card': Rect.fromLTWH(0.2, 0.5, 0.2, 0.5),
    'clue-coffee-receipt': Rect.fromLTWH(0.2, 0.5, 0.2, 0.5),
    'clue-yuna-polish-cloth': Rect.fromLTWH(0.4, 0.5, 0.2, 0.5),
    'clue-yuna-resignation-note': Rect.fromLTWH(0.6, 0.5, 0.2, 0.5),
    'clue-min-business-card': Rect.fromLTWH(0.8, 0.5, 0.2, 0.5),
    'clue-han-shoeprint': Rect.fromLTWH(0.8, 0.5, 0.2, 0.5),
  };

  @override
  Widget build(BuildContext context) {
    final extraCrop = _extraCrops[clueCode];
    final coreCrop = _coreCrops[clueCode] ?? _coreCrops['clue-safe-key']!;

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
        asset: extraCrop == null
            ? AppAssets.evidenceSheet
            : AppAssets.evidenceExtraSheet,
        crop: extraCrop ?? coreCrop,
        sheetWidth: extraCrop == null ? 2560 : 1600,
        sheetHeight: extraCrop == null ? 1024 : 640,
        fit: BoxFit.cover,
        filterQuality: FilterQuality.high,
      ),
    );
  }
}
