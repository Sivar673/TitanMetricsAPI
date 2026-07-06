"""Local-disk storage for uploaded pose images.

Paths are stored relative to settings.upload_dir so the tree can be
relocated (or swapped for object storage) without a data migration.
"""

import re
from pathlib import Path
from typing import Dict, List, Tuple

from app.config import settings

_EXTENSIONS = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}


def save_pose_images(
    user_id: str,
    timestamp: str,
    images: List[Tuple[str, bytes, str]],
) -> Dict[str, str]:
    """Persist raw pose images to disk; returns {pose: relative_path}."""
    safe_stamp = re.sub(r"[^0-9T]", "", timestamp)[:15]  # 20260706T174200
    user_dir = Path(settings.upload_dir) / user_id
    user_dir.mkdir(parents=True, exist_ok=True)

    paths: Dict[str, str] = {}
    for pose, raw, media_type in images:
        ext = _EXTENSIONS.get(media_type, "bin")
        filename = f"{safe_stamp}_{pose}.{ext}"
        (user_dir / filename).write_bytes(raw)
        paths[pose] = f"{user_id}/{filename}"
    return paths
