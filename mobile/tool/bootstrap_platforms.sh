#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
flutter create --platforms=android,ios --org com.ohhamin --project-name alibi .
mkdir -p android/app/src/main/res/drawable
cp tool/android_overrides/ic_launcher.xml android/app/src/main/res/drawable/ic_launcher.xml
python - <<'PY'
from pathlib import Path
manifest = Path('android/app/src/main/AndroidManifest.xml')
text = manifest.read_text()
text = text.replace('@mipmap/ic_launcher', '@drawable/ic_launcher')
manifest.write_text(text)
PY
flutter pub get
