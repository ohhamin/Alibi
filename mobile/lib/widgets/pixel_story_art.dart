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
  //
  // Every clue code currently used by the bookstore story is mapped here.
  // Some ambient/document clues intentionally reuse the closest visual type,
  // but no clue depends on evidence_extra_sheet.webp. That old extra sheet is
  // malformed and caused blank thumbnails on Android.
  static const Map<String, Rect> _evidenceCrops = {
    // Core evidence artwork.
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

    // Motive / document evidence -> contract or manuscript artwork.
    'clue-han-cancel-contract': Rect.fromLTWH(0.8, 0.0, 0.2, 0.5),
    'clue-jiho-debt-letter': Rect.fromLTWH(0.8, 0.0, 0.2, 0.5),
    'clue-jiho-insurance': Rect.fromLTWH(0.8, 0.0, 0.2, 0.5),
    'clue-yuna-resignation-note': Rect.fromLTWH(0.4, 0.5, 0.2, 0.5),
    'clue-irrelevant-old-photo': Rect.fromLTWH(0.4, 0.5, 0.2, 0.5),
    'clue-irrelevant-bookmark': Rect.fromLTWH(0.4, 0.5, 0.2, 0.5),

    // Receipt / ticket / label / card-like evidence.
    'clue-irrelevant-lottery-ticket': Rect.fromLTWH(0.2, 0.0, 0.2, 0.5),
    'clue-irrelevant-raffle-ticket': Rect.fromLTWH(0.2, 0.0, 0.2, 0.5),
    'clue-irrelevant-return-label': Rect.fromLTWH(0.2, 0.0, 0.2, 0.5),
    'clue-irrelevant-milk-label': Rect.fromLTWH(0.2, 0.0, 0.2, 0.5),
    'clue-irrelevant-umbrella-tag': Rect.fromLTWH(0.2, 0.0, 0.2, 0.5),
    'clue-irrelevant-loyalty-card': Rect.fromLTWH(0.4, 0.0, 0.2, 0.5),
    'clue-irrelevant-event-badge': Rect.fromLTWH(0.4, 0.0, 0.2, 0.5),
    'clue-irrelevant-toner-invoice': Rect.fromLTWH(0.4, 0.0, 0.2, 0.5),
    'clue-irrelevant-tea-wrapper': Rect.fromLTWH(0.4, 0.0, 0.2, 0.5),
    'clue-min-business-card': Rect.fromLTWH(0.4, 0.0, 0.2, 0.5),

    // Small objects / trace evidence.
    'clue-irrelevant-coin-battery': Rect.fromLTWH(0.2, 0.5, 0.2, 0.5),
    'clue-han-shoeprint': Rect.fromLTWH(0.8, 0.5, 0.2, 0.5),
    'clue-yuna-polish-cloth': Rect.fromLTWH(0.8, 0.5, 0.2, 0.5),
  };

  @override
  Widget build(BuildContext context) {
    final crop = _evidenceCrops[clueCode] ??
        _evidenceCrops['clue-manuscript']!;

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
