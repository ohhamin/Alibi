import 'package:flutter/material.dart';

import '../core/app_assets.dart';
import 'sheet_crop_image.dart';

/// Location/evidence artwork backed by generated raster files.
///
/// The old public class names are kept for compatibility, but no CustomPainter
/// vector/pixel drawing remains here.
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

  // The generated evidence board is a 4 x 2 composition.
  // Crops focus on the photographed object/paper, not the board labels.
  static const Map<String, Rect> _crops = {
    'clue-safe-key': Rect.fromLTWH(0.025, 0.105, 0.205, 0.315),
    'clue-coffee-receipt': Rect.fromLTWH(0.280, 0.105, 0.205, 0.315),
    'clue-expense': Rect.fromLTWH(0.525, 0.105, 0.205, 0.315),
    'clue-bookend': Rect.fromLTWH(0.770, 0.105, 0.205, 0.315),
    'clue-contract': Rect.fromLTWH(0.025, 0.600, 0.205, 0.315),
    'clue-door-lock': Rect.fromLTWH(0.280, 0.600, 0.205, 0.315),
    'clue-drain-button': Rect.fromLTWH(0.525, 0.600, 0.205, 0.315),
    'clue-manuscript': Rect.fromLTWH(0.770, 0.600, 0.205, 0.315),
  };

  @override
  Widget build(BuildContext context) {
    final crop = _crops[clueCode];

    Widget image;
    if (crop != null) {
      image = SheetCropImage(
        asset: AppAssets.evidenceSheet,
        crop: crop,
        fit: BoxFit.cover,
        filterQuality: FilterQuality.high,
      );
    } else if (clueCode == 'clue-body-time') {
      // Until a dedicated watch close-up is added, use the real office scene
      // rather than falling back to generated geometry.
      image = const SheetCropImage(
        asset: AppAssets.locationSheet,
        crop: Rect.fromLTWH(0.710, 0.090, 0.220, 0.300),
        fit: BoxFit.cover,
        filterQuality: FilterQuality.high,
      );
    } else if (clueCode == 'clue-brass-dust') {
      // The brass trace belongs to the weapon context; keep this raster-only.
      image = const SheetCropImage(
        asset: AppAssets.evidenceSheet,
        crop: Rect.fromLTWH(0.770, 0.105, 0.205, 0.315),
        fit: BoxFit.cover,
        filterQuality: FilterQuality.high,
      );
    } else {
      image = const SheetCropImage(
        asset: AppAssets.evidenceSheet,
        crop: Rect.fromLTWH(0.025, 0.105, 0.205, 0.315),
        fit: BoxFit.cover,
        filterQuality: FilterQuality.high,
      );
    }

    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        color: const Color(0xFF171A1F),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: const Color(0xFF343840)),
      ),
      clipBehavior: Clip.antiAlias,
      child: image,
    );
  }
}
