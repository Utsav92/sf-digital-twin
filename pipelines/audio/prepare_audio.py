"""Conform any soundtrack to EXACTLY 60.000 s of 48 kHz stereo (2,880,000 samples/channel) without changing its speed.
  python prepare_audio.py in.(wav|mp3|m4a|...) out.wav [--start S] [--fade-in 0.5] [--fade-out 3] [--duration 60]
Longer input  -> trimmed from --start (fade-out applied at the end).
Shorter input -> padded with silence (fade-out still applied to the real end); a warning is printed.
Decoding uses ffmpeg (FFMPEG env var, else ~/.local/bin/ffmpeg, else PATH). Never time-stretches."""
import os
import shutil
import subprocess
import sys
import wave
from pathlib import Path
import numpy as np

SR = 48000


def ffmpeg_bin() -> str:
    for c in (os.environ.get("FFMPEG"), str(Path.home() / ".local/bin/ffmpeg"), shutil.which("ffmpeg")):
        if c and Path(c).exists():
            return c
    sys.exit("ffmpeg not found (set FFMPEG=/path/to/ffmpeg)")


def opt(name, default, cast=float):
    return cast(sys.argv[sys.argv.index(name) + 1]) if name in sys.argv else default


def main():
    src, dst = sys.argv[1], sys.argv[2]
    start, fin, fout, dur = opt("--start", 0.0), opt("--fade-in", 0.5), opt("--fade-out", 3.0), opt("--duration", 60.0)
    cmd = [ffmpeg_bin(), "-v", "error", "-ss", f"{start}", "-i", src, "-vn", "-ac", "2", "-ar", str(SR), "-f", "f32le", "-"]
    raw = subprocess.run(cmd, check=True, capture_output=True).stdout
    x = np.frombuffer(raw, "<f4").reshape(-1, 2).copy()
    n = int(round(dur * SR))
    have = len(x)
    if have < n:
        print(f"WARNING: source has {have / SR:.2f} s after --start; padding {dur - have / SR:.2f} s of silence (not stretched)")
        x = np.vstack([x, np.zeros((n - have, 2), "<f4")])
        real = have
    else:
        x = x[:n]
        real = n
    ramp_in = min(n, int(fin * SR))
    if ramp_in:
        x[:ramp_in] *= np.linspace(0, 1, ramp_in)[:, None]
    ramp_out = min(real, int(fout * SR))
    if ramp_out:
        x[real - ramp_out:real] *= np.linspace(1, 0, ramp_out)[:, None]
    peak = float(np.abs(x).max())
    if peak > 0.98:
        x *= 0.98 / peak
    pcm = (np.clip(x, -1, 1) * 32767).astype("<i2")
    with wave.open(dst, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm.tobytes())
    print(f"WROTE {dst}: {len(pcm)} samples/ch = {len(pcm) / SR:.6f} s @ {SR} Hz stereo (peak {peak:.3f})")
    assert len(pcm) == n


main()
