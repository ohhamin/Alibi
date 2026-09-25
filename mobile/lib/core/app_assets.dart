class AppAssets {
  AppAssets._();

  static const loading = 'assets/images/ui/loading.webp';
  static const appIcon = 'assets/images/ui/app_icon.webp';
  static const evidenceSheet = 'assets/images/sheets/evidence_sheet.webp';

  static const Map<String, String> _locationAssets = {
    'hall': 'assets/images/locations/bookstore_hall.webp',
    'cafe': 'assets/images/locations/cafe.webp',
    'office': 'assets/images/locations/office.webp',
    'storage': 'assets/images/locations/storage.webp',
    'back-alley': 'assets/images/locations/back_alley.webp',
  };

  static const Map<String, String> _characterAssets = {
    'seo-yuna': 'assets/images/characters/seo_yuna.webp',
    'han-jun': 'assets/images/characters/han_jun.webp',
    'min-seoyeon': 'assets/images/characters/min_seoyeon.webp',
    'yoon-jiho': 'assets/images/characters/yoon_jiho.webp',
    'kang-haejin': 'assets/images/characters/kang_haejin.webp',
  };

  static String? locationForCode(String? code) {
    if (code == null || code.isEmpty) return null;
    return _locationAssets[code];
  }

  static String? characterForCode(String? code) {
    if (code == null || code.isEmpty) return null;
    return _characterAssets[code];
  }
}
