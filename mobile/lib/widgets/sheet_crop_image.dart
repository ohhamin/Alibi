import 'package:flutter/material.dart';

/// Displays a normalized crop from a real raster asset without redrawing it.
///
/// [crop] is expressed in 0..1 coordinates against the original sheet.
class SheetCropImage extends StatelessWidget {
  const SheetCropImage({
    super.key,
    required this.asset,
    required this.crop,
    this.fit = BoxFit.cover,
    this.filterQuality = FilterQuality.high,
    this.borderRadius,
    this.sheetWidth = 1200,
    this.sheetHeight = 900,
  });

  final String asset;
  final Rect crop;
  final BoxFit fit;
  final FilterQuality filterQuality;
  final BorderRadius? borderRadius;
  final double sheetWidth;
  final double sheetHeight;

  @override
  Widget build(BuildContext context) {
    Widget child = LayoutBuilder(
      builder: (context, constraints) {
        final targetWidth = constraints.maxWidth.isFinite
            ? constraints.maxWidth
            : 300.0;
        final targetHeight = constraints.maxHeight.isFinite
            ? constraints.maxHeight
            : 300.0;

        final cropWidth = crop.width * sheetWidth;
        final cropHeight = crop.height * sheetHeight;

        return ClipRect(
          child: SizedBox(
            width: targetWidth,
            height: targetHeight,
            child: FittedBox(
              fit: fit,
              clipBehavior: Clip.hardEdge,
              child: SizedBox(
                width: cropWidth,
                height: cropHeight,
                child: ClipRect(
                  child: Stack(
                    clipBehavior: Clip.hardEdge,
                    children: [
                      Positioned(
                        left: -crop.left * sheetWidth,
                        top: -crop.top * sheetHeight,
                        width: sheetWidth,
                        height: sheetHeight,
                        child: Image.asset(
                          asset,
                          width: sheetWidth,
                          height: sheetHeight,
                          fit: BoxFit.fill,
                          filterQuality: filterQuality,
                          gaplessPlayback: true,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        );
      },
    );

    if (borderRadius != null) {
      child = ClipRRect(borderRadius: borderRadius!, child: child);
    }
    return child;
  }
}
