#!/usr/bin/env bash
# Idempotent, quiet. Installs only pip wheels (no apt, no GPU).
set -e
python3 - <<'EOF' 2>/dev/null && exit 0
import numpy, scipy, PIL, cv2, imageio_ffmpeg, faster_whisper, fontTools
EOF
pip install -q --disable-pip-version-check numpy scipy pillow "opencv-python-headless<5" imageio-ffmpeg faster-whisper fonttools 2>&1 | grep -vi -E "warning|notice|already" | tail -3 || \
pip install -q --break-system-packages numpy scipy pillow "opencv-python-headless<5" imageio-ffmpeg faster-whisper fonttools 2>&1 | tail -3
python3 -c "import numpy,scipy,PIL,cv2,imageio_ffmpeg;print('setup ok')"
