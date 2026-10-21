"""Encode a playback copy without changing inference frames or tracking data."""
import subprocess
from pathlib import Path


def prepare_playback(source: Path, output: Path) -> None:
    import imageio_ffmpeg

    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-i", str(source),
                    "-an", "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                    "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output)],
                   check=True, capture_output=True)
