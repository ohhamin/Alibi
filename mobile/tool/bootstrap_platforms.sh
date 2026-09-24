#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
flutter create --platforms=android,ios --org com.ohhamin --project-name alibi .
flutter pub get
