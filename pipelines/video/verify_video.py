"""Verify the final MP4: duration, frame count, resolution, fps, audio format and A/V sync.
  python verify_video.py [video.mp4] [source_audio.wav]
Exit code 1 if any check fails. Sync = cross-correlation lag between the decoded AAC track and the source wav (must be < 1 frame, 33 ms)."""
import os, re, shutil, subprocess, sys, wave
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
video = sys.argv[1] if len(sys.argv) > 1 else str(ROOT / "renders/film60/SF_Musical_Digital_Twin_60s.mp4")
src = sys.argv[2] if len(sys.argv) > 2 else str(ROOT / "data/film60/track_60s.wav")
ff = next((c for c in (os.environ.get("FFMPEG"), str(Path.home() / ".local/bin/ffmpeg"), shutil.which("ffmpeg")) if c and Path(c).exists()))
res = []
def check(name, ok, detail):
    res.append(ok); print(("PASS " if ok else "FAIL ") + f"{name}: {detail}")

info = subprocess.run([ff, "-hide_banner", "-i", video], capture_output=True, text=True).stderr
m = re.search(r"Video:.*?, (\d+)x(\d+).*?, ([\d.]+) fps", info)
check("resolution", bool(m) and (int(m[1]), int(m[2])) == (1920, 1080), f"{m[1]}x{m[2]}" if m else "no video stream")
check("frame rate", bool(m) and abs(float(m[3]) - 30) < 1e-6, f"{m[3]} fps" if m else "?")
check("video codec", "Video: h264" in info, "h264" if "Video: h264" in info else "not h264")
a = re.search(r"Audio: (\w+).*?, (\d+) Hz, (\w+)", info)
check("audio", bool(a) and a[1] == "aac" and a[2] == "48000" and a[3] == "stereo", f"{a[1]} {a[2]} Hz {a[3]}" if a else "no audio stream")
cnt = subprocess.run([ff, "-hide_banner", "-i", video, "-map", "0:v:0", "-f", "null", "-"], capture_output=True, text=True).stderr
fr = [int(x) for x in re.findall(r"frame=\s*(\d+)", cnt)]
check("frame count", bool(fr) and fr[-1] == 1800, f"{fr[-1] if fr else '?'} (want 1800)")
raw = subprocess.run([ff, "-v", "error", "-i", video, "-map", "0:a:0", "-ac", "1", "-ar", "48000", "-f", "f32le", "-"], capture_output=True).stdout
x = np.frombuffer(raw, "<f4")
check("audio duration", abs(len(x) / 48000 - 60) < 0.06, f"{len(x) / 48000:.3f} s (AAC encoder padding allowed <60 ms)")
dur = re.search(r"Duration: (\d+):(\d+):([\d.]+)", info)
vd = int(dur[1]) * 3600 + int(dur[2]) * 60 + float(dur[3]) if dur else -1
check("container duration", abs(vd - 60) < 0.06, f"{vd:.3f} s")
with wave.open(src) as w:
    s = np.frombuffer(w.readframes(w.getnframes()), "<i2").astype(np.float32).reshape(-1, w.getnchannels()).mean(1) / 32768
n = 48000 * 20
a_, b_ = x[:n], s[:n]
F = 1 << int(np.ceil(np.log2(2 * n)))
cc = np.fft.irfft(np.fft.rfft(a_, F) * np.conj(np.fft.rfft(b_, F)), F)
lags = np.r_[cc[:2400], cc[-2400:]]; k = int(np.argmax(lags)); lag = k if k < 2400 else k - 4800
check("A/V sync", abs(lag) / 48 < 33.3, f"audio offset {lag / 48:+.1f} ms vs source (limit 1 frame = 33.3 ms)")
sys.exit(0 if all(res) else 1)
