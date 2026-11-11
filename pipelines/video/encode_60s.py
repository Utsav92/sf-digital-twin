"""Mux the 1,800 rendered PNGs with the conformed 60 s soundtrack into H.264 + AAC MP4.
  python encode_60s.py [frames_dir] [audio.wav] [out.mp4]
Exactly 1,800 frames are required (fails otherwise); -frames:v/-t pin the result to 1,800 frames / 60 s."""
import os, shutil, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
frames = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "renders/film60/frames"
audio = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "data/film60/track_60s.wav"
out = Path(sys.argv[3]) if len(sys.argv) > 3 else ROOT / "renders/film60/SF_Musical_Digital_Twin_60s.mp4"
ff = next((c for c in (os.environ.get("FFMPEG"), str(Path.home() / ".local/bin/ffmpeg"), shutil.which("ffmpeg")) if c and Path(c).exists()), None)
if not ff:
    sys.exit("ffmpeg not found")
missing = [i for i in range(1, 1801) if not (frames / f"frame_{i:04d}.png").exists()]
if missing:
    sys.exit(f"{len(missing)} of 1800 frames missing (first: {missing[0]}); refusing to encode a short film")
cmd = [ff, "-y", "-v", "error", "-framerate", "30", "-start_number", "1", "-i", str(frames / "frame_%04d.png"), "-i", str(audio),
       "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-pix_fmt", "yuv420p", "-r", "30",
       "-vf", "scale=1920:1080:flags=lanczos,format=yuv420p", "-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-ac", "2",
       "-frames:v", "1800", "-t", "60", "-movflags", "+faststart", str(out)]
subprocess.run(cmd, check=True)
print("ENCODED", out)
