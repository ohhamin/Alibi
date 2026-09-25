import 'package:flutter/material.dart';

class PixelLocationArt extends StatelessWidget {
  const PixelLocationArt({
    super.key,
    required this.locationCode,
    this.height = 190,
  });

  final String? locationCode;
  final double height;

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(8),
      child: SizedBox(
        width: double.infinity,
        height: height,
        child: CustomPaint(
          painter: _PixelLocationPainter(locationCode ?? ''),
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

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(7),
      child: SizedBox.square(
        dimension: size,
        child: CustomPaint(
          painter: _PixelEvidencePainter(clueCode ?? ''),
        ),
      ),
    );
  }
}

class _PixelLocationPainter extends CustomPainter {
  const _PixelLocationPainter(this.code);

  final String code;

  static const bg = Color(0xFF0B0D10);
  static const wall = Color(0xFF202329);
  static const wall2 = Color(0xFF292B2D);
  static const wood = Color(0xFF4A3626);
  static const wood2 = Color(0xFF6A4A2E);
  static const paper = Color(0xFFC7B998);
  static const brass = Color(0xFFB38A48);
  static const steel = Color(0xFF5E6468);
  static const rain = Color(0xFF33495A);
  static const red = Color(0xFF6B3131);

  @override
  void paint(Canvas canvas, Size size) {
    canvas.save();
    canvas.scale(size.width / 160, size.height / 120);
    final p = Paint()..isAntiAlias = false;

    void rect(double x, double y, double w, double h, Color color) {
      p.color = color;
      canvas.drawRect(Rect.fromLTWH(x, y, w, h), p);
    }

    rect(0, 0, 160, 120, bg);
    rect(0, 0, 160, 82, wall);
    rect(0, 82, 160, 38, const Color(0xFF16191C));

    switch (code) {
      case 'hall':
        _hall(rect);
        break;
      case 'cafe':
        _cafe(rect);
        break;
      case 'office':
        _office(rect);
        break;
      case 'storage':
        _storage(rect);
        break;
      case 'back-alley':
        _alley(rect);
        break;
      default:
        _hall(rect);
    }

    canvas.restore();
  }

  void _shelf(
    void Function(double, double, double, double, Color) rect,
    double x,
    double y,
    double w,
    double h,
  ) {
    rect(x, y, w, h, wood);
    for (double yy = y + 8; yy < y + h - 2; yy += 10) {
      rect(x + 3, yy, w - 6, 2, wood2);
    }
    for (double xx = x + 5; xx < x + w - 4; xx += 6) {
      rect(xx, y + 3, 3, h - 7, const Color(0xFF343038));
    }
  }

  void _hall(void Function(double, double, double, double, Color) r) {
    _shelf(r, 4, 8, 34, 68);
    _shelf(r, 122, 8, 34, 68);
    r(45, 51, 54, 19, wood2);
    r(48, 70, 48, 13, wood);
    r(80, 56, 11, 7, const Color(0xFF131619)); // register
    r(53, 73, 28, 5, const Color(0xFF211A16)); // employee drawer
    r(103, 30, 11, 50, const Color(0xFF32363A)); // stairs
    for (double y = 34; y < 78; y += 7) {
      r(103, y, 11, 2, steel);
    }
    r(66, 16, 24, 18, const Color(0xFF3A3027));
    r(69, 19, 18, 12, paper);
    r(54, 90, 22, 10, wood);
    r(93, 92, 27, 8, wood);
  }

  void _cafe(void Function(double, double, double, double, Color) r) {
    _shelf(r, 4, 10, 29, 64);
    r(38, 50, 86, 26, wood);
    r(43, 35, 24, 15, steel); // coffee machine
    r(47, 38, 6, 6, const Color(0xFF111315));
    r(56, 38, 7, 6, const Color(0xFF111315));
    r(72, 42, 22, 8, const Color(0xFF41474A)); // sink
    r(99, 29, 23, 47, const Color(0xFF464C50)); // fridge
    r(131, 25, 22, 57, const Color(0xFF171A1F)); // emergency door
    r(135, 48, 3, 3, brass);
    r(50, 91, 33, 7, wood2);
    r(56, 98, 4, 14, wood);
    r(75, 98, 4, 14, wood);
  }

  void _office(void Function(double, double, double, double, Color) r) {
    r(7, 89, 103, 22, const Color(0xFF30292A)); // rug / carpet
    r(55, 49, 62, 22, wood2); // desk
    r(61, 46, 8, 4, brass); // brass bookend
    r(73, 45, 20, 3, paper); // documents
    r(120, 20, 25, 28, steel); // wall safe
    r(126, 28, 11, 8, const Color(0xFF1B1E21));
    r(10, 28, 27, 52, const Color(0xFF181B1F)); // door
    r(32, 48, 3, 8, brass); // door lock
    r(113, 77, 12, 15, const Color(0xFF363A3E)); // bin
    r(122, 61, 31, 13, const Color(0xFF343239)); // sofa
    r(26, 77, 18, 5, const Color(0xFF262B30)); // body
    r(20, 82, 26, 5, const Color(0xFF262B30));
    r(16, 86, 7, 7, const Color(0xFFB49B80)); // head
    r(35, 79, 4, 4, red); // restrained blood cue
  }

  void _storage(void Function(double, double, double, double, Color) r) {
    _shelf(r, 3, 9, 36, 70);
    _shelf(r, 121, 10, 35, 69);
    for (final b in const [
      [45.0, 58.0, 25.0, 20.0],
      [73.0, 51.0, 27.0, 27.0],
      [103.0, 62.0, 17.0, 16.0],
    ]) {
      r(b[0], b[1], b[2], b[3], const Color(0xFF51402D));
      r(b[0] + 3, b[1] + 5, b[2] - 6, 2, const Color(0xFF776045));
    }
    r(48, 26, 24, 26, const Color(0xFF383D40)); // shredder
    r(52, 20, 16, 7, const Color(0xFF17191C));
    r(55, 86, 21, 3, paper); // shredded scraps
    r(81, 92, 5, 2, brass); // spare key
    r(85, 91, 7, 3, brass);
  }

  void _alley(void Function(double, double, double, double, Color) r) {
    r(0, 0, 160, 86, const Color(0xFF171B20));
    for (double y = 9; y < 82; y += 11) {
      for (double x = (y ~/ 11).isEven ? 0 : 8; x < 160; x += 18) {
        r(x, y, 15, 7, const Color(0xFF24292E));
      }
    }
    r(15, 24, 29, 61, const Color(0xFF101317)); // emergency door
    r(38, 53, 3, 3, brass);
    r(0, 86, 160, 34, const Color(0xFF11171C));
    r(93, 98, 25, 6, const Color(0xFF252C31)); // drain
    for (double x = 96; x < 116; x += 5) {
      r(x, 99, 2, 4, const Color(0xFF0C0F12));
    }
    r(121, 99, 3, 3, const Color(0xFF5F6468)); // coat button
    for (double x = 8; x < 155; x += 18) {
      r(x, 7, 1, 18, rain);
      r(x + 6, 33, 1, 21, rain);
      r(x + 11, 62, 1, 17, rain);
    }
    r(48, 104, 36, 3, const Color(0xFF263C49));
    r(127, 109, 25, 2, const Color(0xFF263C49));
  }

  @override
  bool shouldRepaint(covariant _PixelLocationPainter oldDelegate) =>
      oldDelegate.code != code;
}

class _PixelEvidencePainter extends CustomPainter {
  const _PixelEvidencePainter(this.code);

  final String code;

  @override
  void paint(Canvas canvas, Size size) {
    canvas.save();
    canvas.scale(size.width / 48, size.height / 48);
    final p = Paint()..isAntiAlias = false;

    void r(double x, double y, double w, double h, Color c) {
      p.color = c;
      canvas.drawRect(Rect.fromLTWH(x, y, w, h), p);
    }

    const bg = Color(0xFF111419);
    const edge = Color(0xFF343840);
    const paper = Color(0xFFD0C2A0);
    const ink = Color(0xFF645943);
    const brass = Color(0xFFB38A48);
    const metal = Color(0xFF737A7E);
    const red = Color(0xFF743838);

    r(0, 0, 48, 48, bg);
    r(1, 1, 46, 46, const Color(0xFF171A1F));
    r(1, 1, 46, 2, edge);
    r(1, 45, 46, 2, edge);
    r(1, 1, 2, 46, edge);
    r(45, 1, 2, 46, edge);

    switch (code) {
      case 'clue-drain-button':
        r(19, 17, 11, 11, metal);
        r(22, 20, 2, 2, bg);
        r(26, 20, 2, 2, bg);
        r(22, 24, 2, 2, bg);
        r(26, 24, 2, 2, bg);
        break;
      case 'clue-coffee-receipt':
        r(13, 8, 22, 32, paper);
        for (double y = 14; y < 35; y += 5) r(17, y, 14, 2, ink);
        r(20, 9, 8, 3, red);
        break;
      case 'clue-brass-dust':
        r(10, 10, 28, 26, const Color(0xFF292C31));
        for (final point in const [[15, 17], [24, 15], [32, 20], [19, 28], [29, 31]]) {
          r(point[0].toDouble(), point[1].toDouble(), 3, 3, brass);
        }
        break;
      case 'clue-expense':
        r(10, 9, 28, 31, paper);
        for (double y = 15; y < 35; y += 5) r(14, y, 20, 2, ink);
        r(27, 30, 8, 5, red);
        break;
      case 'clue-body-time':
        r(12, 18, 24, 12, const Color(0xFF30353A));
        r(18, 14, 12, 20, metal);
        r(21, 18, 6, 8, const Color(0xFF0D1013));
        r(23, 21, 2, 4, red);
        break;
      case 'clue-bookend':
        r(14, 11, 8, 26, brass);
        r(22, 29, 14, 8, brass);
        r(17, 15, 3, 18, const Color(0xFF84642F));
        r(31, 31, 3, 3, red);
        break;
      case 'clue-contract':
        r(9, 8, 30, 32, paper);
        r(16, 8, 3, 6, bg);
        r(25, 8, 3, 7, bg);
        r(33, 8, 3, 5, bg);
        for (double y = 17; y < 34; y += 5) r(14, y, 20, 2, ink);
        r(15, 35, 17, 2, red);
        break;
      case 'clue-door-lock':
        r(12, 10, 24, 28, metal);
        r(16, 14, 16, 9, const Color(0xFF101317));
        r(18, 28, 12, 5, brass);
        break;
      case 'clue-manuscript':
        r(8, 11, 25, 29, paper);
        r(15, 7, 25, 29, const Color(0xFFB8AA8E));
        for (double y = 14; y < 31; y += 5) r(19, y, 16, 2, ink);
        r(21, 19, 10, 2, red);
        break;
      case 'clue-safe-key':
        r(8, 21, 16, 9, brass);
        r(12, 18, 9, 15, bg);
        r(21, 24, 18, 4, brass);
        r(32, 27, 4, 5, brass);
        r(27, 27, 4, 4, brass);
        break;
      default:
        r(13, 10, 22, 28, paper);
        r(18, 17, 12, 2, ink);
        r(18, 23, 12, 2, ink);
        r(18, 29, 8, 2, ink);
    }

    canvas.restore();
  }

  @override
  bool shouldRepaint(covariant _PixelEvidencePainter oldDelegate) =>
      oldDelegate.code != code;
}
