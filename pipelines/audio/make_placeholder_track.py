"""Synthesise an ORIGINAL 60 s placeholder soundtrack (48 kHz stereo) that follows the storyboard energy curve.
Used only when no real track is supplied; replace it with your own music via prepare_audio.py.
  0-10 pad + soft kick | 10-20 + bass | 20-30 + hats/arp | 30-40 breakdown (filtered, riser) | 40-50 climax | 50-60 resolve
Deterministic (seeded). Usage: python make_placeholder_track.py out.wav [--bpm 120]"""
import sys
import wave
import numpy as np

SR, DUR = 48000, 60.0
BPM = float(sys.argv[sys.argv.index("--bpm") + 1]) if "--bpm" in sys.argv else 120.0
rng = np.random.default_rng(7)
N = int(SR * DUR)
t = np.arange(N) / SR
beat = 60.0 / BPM


def env_between(a, b, ramp=1.0):
    """1 inside [a,b] with linear ramps, 0 outside."""
    return np.clip((t - a) / ramp, 0, 1) * np.clip((b - t) / ramp, 0, 1)


def add(buf, start, sig, gain=1.0):
    i = int(start * SR)
    if i >= len(buf):
        return
    seg = sig[: len(buf) - i]
    buf[i:i + len(seg)] += seg * gain


def kick():
    n = int(0.35 * SR); x = np.arange(n) / SR
    f = 48 + 110 * np.exp(-x * 28)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-x * 9)


def hat():
    n = int(0.06 * SR); x = np.arange(n) / SR
    nz = rng.standard_normal(n)
    nz = nz - np.convolve(nz, np.ones(8) / 8, mode="same")  # crude high-pass
    return nz * np.exp(-x * 70)


def tone(freq, dur, saw=True, harmonics=6):
    n = int(dur * SR); x = np.arange(n) / SR
    s = sum(np.sin(2 * np.pi * freq * k * x) / k for k in range(1, harmonics + 1)) if saw else np.sin(2 * np.pi * freq * x)
    a = np.minimum(1, x / 0.01) * np.minimum(1, (dur - x) / 0.05)
    return s * a


L = np.zeros(N); R = np.zeros(N)
roots = [55.0, 43.65, 48.99, 41.2]  # A1 F1 G1 E1 loop, one chord per 2 bars
bar = 4 * beat
nbeats = int(DUR / beat)

# Pad (always, swells to the climax)
for bi in range(int(DUR / (2 * bar)) + 1):
    r = roots[bi % 4] * 4
    s = sum(tone(r * m, 2 * bar, harmonics=4) for m in (1, 1.2, 1.5)) * 0.06
    add(L, bi * 2 * bar, s); add(R, bi * 2 * bar, np.roll(s, 40))
pad_gain = 0.5 + 0.5 * env_between(30, 50, 8)

# Kick on every beat except the breakdown (30-38), dropping in with a fill
for b in range(nbeats):
    tb = b * beat
    if 30 <= tb < 38:
        continue
    g = 0.55 if tb < 10 else 0.85
    add(L, tb, kick(), g); add(R, tb, kick(), g)

# Bass (10-30, 38-56)
for b in range(nbeats * 2):
    tb = b * beat / 2
    if not (10 <= tb < 30 or 38 <= tb < 56):
        continue
    root = roots[int(tb // (2 * bar)) % 4]
    note = root * (2 if (b % 4 == 3) else 1)
    s = tone(note, beat / 2 * 0.9, harmonics=3) * 0.35
    add(L, tb, s); add(R, tb, s)

# Hats / arp (20-30, 38-56)
for b in range(nbeats * 2):
    tb = b * beat / 2
    if (20 <= tb < 30 or 38 <= tb < 56) and b % 2 == 1:
        h = hat() * 0.3; add(L, tb, h, 0.9); add(R, tb, h, 1.1)
    if 20 <= tb < 30 or 40 <= tb < 52:
        f = roots[int(tb // (2 * bar)) % 4] * 8 * (1, 1.5, 2, 1.5)[b % 4]
        s = tone(f, beat / 4, harmonics=5) * 0.07
        add(L, tb, s, 1.0); add(R, tb + 0.011, s, 1.0)

# Riser through the breakdown (30-40): filtered noise sweeping up
rise = rng.standard_normal(N)
k = np.cumsum(rise) * 0.002
rise = (rise - np.convolve(rise, np.ones(30) / 30, mode="same")) * env_between(30, 40, 9) * ((t - 30).clip(0) / 10) ** 2 * 0.25
L += rise; R += np.roll(rise, 100)

L += 0; R += 0
L *= (pad_gain * 0 + 1); R *= (pad_gain * 0 + 1)
out = np.stack([L, R], 1)
# Master: soft clip, fade in 0.5 s / fade out 3 s
out = np.tanh(out * 1.4) * 0.8
out *= np.clip(t / 0.5, 0, 1)[:, None] * np.clip((DUR - t) / 3.0, 0, 1)[:, None]
pcm = (np.clip(out, -1, 1) * 32767).astype("<i2")
with wave.open(sys.argv[1], "wb") as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm.tobytes())
print(f"WROTE {sys.argv[1]} {N} samples/ch = {N / SR:.3f} s @ {SR} Hz stereo, {BPM:g} BPM")
