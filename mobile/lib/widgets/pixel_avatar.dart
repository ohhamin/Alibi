import 'package:flutter/material.dart';

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
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        color: const Color(0xFF17191D),
        borderRadius: BorderRadius.circular(borderRadius),
        border: Border.all(color: const Color(0xFF3A3630)),
      ),
      clipBehavior: Clip.antiAlias,
      child: CustomPaint(
        painter: _PixelPortraitPainter(code ?? '', name),
      ),
    );
  }
}

class _PixelPortraitPainter extends CustomPainter {
  const _PixelPortraitPainter(this.code, this.name);

  final String code;
  final String name;

  @override
  void paint(Canvas canvas, Size size) {
    canvas.save();
    canvas.scale(size.width / 32, size.height / 40);
    final p = Paint()..isAntiAlias = false;

    void r(double x, double y, double w, double h, Color c) {
      p.color = c;
      canvas.drawRect(Rect.fromLTWH(x, y, w, h), p);
    }

    const bg = Color(0xFF22262C);
    const skin = Color(0xFFC99F7A);
    const skinDark = Color(0xFF9B7357);
    const black = Color(0xFF17181B);
    const brown = Color(0xFF3D2C25);
    const auburn = Color(0xFF5A342C);
    const gray = Color(0xFF5F6264);
    const paper = Color(0xFFE3D8C2);
    const green = Color(0xFF455C4B);
    const red = Color(0xFF6C3638);
    const navy = Color(0xFF303B4B);
    const brass = Color(0xFFB38A48);

    r(0, 0, 32, 40, bg);

    Color hair = brown;
    Color clothes = green;
    bool glasses = false;
    bool cap = false;
    bool moustache = false;
    bool tie = false;

    switch (code) {
      case 'seo-yuna':
        hair = const Color(0xFF2B2422);
        clothes = green;
        break;
      case 'han-jun':
        hair = const Color(0xFF2C2B2A);
        clothes = const Color(0xFF494742);
        glasses = true;
        moustache = true;
        break;
      case 'min-seoyeon':
        hair = auburn;
        clothes = red;
        break;
      case 'yoon-jiho':
        hair = black;
        clothes = paper;
        tie = true;
        break;
      case 'kang-haejin':
        hair = const Color(0xFF22272B);
        clothes = navy;
        cap = true;
        break;
      default:
        hair = black;
        clothes = const Color(0xFF4A4D53);
    }

    // shoulders / clothes
    r(5, 30, 22, 10, clothes);
    r(3, 34, 26, 6, clothes);

    // neck
    r(13, 27, 6, 6, skinDark);
    r(12, 27, 8, 4, skin);

    // ears
    r(7, 16, 3, 8, skinDark);
    r(22, 16, 3, 8, skinDark);

    // head
    r(9, 10, 14, 18, skin);
    r(10, 8, 12, 4, hair);
    r(8, 11, 3, 9, hair);
    r(21, 11, 3, 9, hair);

    if (code == 'seo-yuna') {
      r(7, 9, 18, 6, hair);
      r(7, 13, 4, 13, hair);
      r(21, 13, 4, 13, hair);
      r(10, 8, 9, 3, hair);
      r(18, 9, 6, 4, hair);
    } else if (code == 'han-jun') {
      r(8, 8, 16, 5, hair);
      r(8, 11, 4, 4, gray);
      r(20, 11, 4, 4, gray);
      r(10, 8, 4, 2, gray);
    } else if (code == 'min-seoyeon') {
      r(7, 8, 18, 6, hair);
      r(7, 12, 4, 15, hair);
      r(21, 12, 4, 15, hair);
      r(18, 8, 7, 4, hair);
    } else if (code == 'yoon-jiho') {
      r(7, 8, 18, 5, hair);
      r(8, 6, 5, 5, hair);
      r(14, 7, 5, 4, hair);
      r(20, 6, 4, 6, hair);
      r(7, 12, 4, 6, hair);
      r(21, 12, 4, 6, hair);
    } else if (code == 'kang-haejin') {
      r(8, 10, 16, 4, hair);
      cap = true;
    }

    if (cap) {
      r(7, 6, 18, 6, const Color(0xFF353A3E));
      r(10, 4, 12, 4, const Color(0xFF353A3E));
      r(11, 5, 10, 2, brass);
      r(22, 10, 5, 2, const Color(0xFF353A3E));
    }

    // eyes: intentionally small and asymmetrical enough to feel hand-pixelled
    r(12, 18, 2, 2, black);
    r(19, 18, 2, 2, black);
    r(15, 21, 3, 2, skinDark);

    if (glasses) {
      r(10, 16, 6, 1, black);
      r(18, 16, 6, 1, black);
      r(10, 17, 1, 4, black);
      r(15, 17, 1, 4, black);
      r(18, 17, 1, 4, black);
      r(23, 17, 1, 4, black);
      r(16, 18, 2, 1, black);
    }

    if (moustache) {
      r(12, 23, 4, 2, brown);
      r(17, 23, 4, 2, brown);
      r(15, 24, 3, 2, brown);
    } else {
      r(14, 24, 5, 1, const Color(0xFF79564A));
    }

    if (tie) {
      r(15, 31, 3, 4, navy);
      r(14, 35, 5, 5, navy);
    }

    // subtle code-specific imperfections so silhouettes do not collapse into one template.
    if (code == 'seo-yuna') {
      r(5, 32, 4, 8, const Color(0xFF35483A));
    } else if (code == 'min-seoyeon') {
      r(8, 30, 2, 10, const Color(0xFF8A4545));
    } else if (code == 'kang-haejin') {
      r(4, 33, 5, 7, const Color(0xFF242D39));
    }

    canvas.restore();
  }

  @override
  bool shouldRepaint(covariant _PixelPortraitPainter oldDelegate) =>
      oldDelegate.code != code || oldDelegate.name != name;
}
