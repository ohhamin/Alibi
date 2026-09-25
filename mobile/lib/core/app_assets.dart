class AppAssets {
  AppAssets._();

  static const loading = 'assets/images/ui/loading.webp';

  static const Map<String, String> _locationAssets = {
    'hall': 'assets/images/locations/bookstore_hall.webp',
  };

  static const Map<String, String> _characterAssets = {
    'seo-yuna': 'assets/images/characters/seo_yuna.webp',
    'han-jun': 'assets/images/characters/han_jun.webp',
    'yoon-jiho': 'assets/images/characters/yoon_jiho.webp',
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
