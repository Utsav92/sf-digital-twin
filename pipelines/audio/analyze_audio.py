"""Precompute per-video-frame audio features (deterministic) for the 60 s render.
  python analyze_audio.py track.wav features.json [--fps 30] [--frames 1800]
Same algorithm as the Three.js app (apps src/audio/features.ts): Hann FFT, bass/mid/treble band amplitude with
adaptive peak normalisation, RMS, spectral centroid, spectral flux, adaptive-threshold beats + tempo.
Each frame k analyses a 2048-sample window centred on t=k/fps, so the features for frame k are a pure function of
the audio — rendering is reproducible and frame-accurate."""
import json
import sys
import wave
import numpy as np

FFT = 2048
BANDS = {"bass": (20, 250), "mid": (250, 2000), "treble": (2000, 12000)}


def opt(name, default, cast=float):
    return cast(sys.argv[sys.argv.index(name) + 1]) if name in sys.argv else default


def load(path):
    with wave.open(path, "rb") as w:
        assert w.getsampwidth() == 2, "expected 16-bit wav (run prepare_audio.py first)"
        sr, ch = w.getframerate(), w.getnchannels()
        x = np.frombuffer(w.readframes(w.getnframes()), "<i2").astype(np.float64) / 32768
    return sr, x.reshape(-1, ch).mean(1)


def main():
    path, out = sys.argv[1], sys.argv[2]
    fps, nf = opt("--fps", 30.0), opt("--frames", 1800, int)
    sr, x = load(path)
    win = 0.5 - 0.5 * np.cos(2 * np.pi * np.arange(FFT) / FFT)
    binhz = sr / FFT
    idx = {k: (max(1, int(lo / binhz)), min(FFT // 2 - 1, int(np.ceil(hi / binhz)))) for k, (lo, hi) in BANDS.items()}
    freqs = np.arange(FFT // 2) * binhz
    cmask = (freqs >= 20) & (freqs <= 12000)
    fmax = int(np.ceil(4000 / binhz))
    peaks = dict(bass=1e-4, mid=1e-4, treble=1e-4, rms=1e-4)
    prev = None
    hist = []  # (t, flux)
    flux_mean, last_beat, prev_flux = 1e-6, -1e9, 0.0
    beat_times, tempo = [], 0.0
    rows = []
    dt = 1.0 / fps
    for k in range(nf):
        t = k / fps
        c = int(t * sr)
        seg = np.zeros(FFT)
        a, b = c - FFT // 2, c + FFT // 2
        lo, hi = max(a, 0), min(b, len(x))
        if hi > lo:
            seg[lo - a:hi - a] = x[lo:hi]
        mags = np.abs(np.fft.rfft(seg * win))[: FFT // 2] * 4 / FFT
        f = {}
        for key, (i0, i1) in idx.items():
            v = float(np.sqrt(np.sum(mags[i0:i1 + 1] ** 2)))
            peaks[key] = max(v, peaks[key] * np.exp(-dt / 6), 1e-4)
            f[key] = float(min(1, v / peaks[key]) ** 0.8)
        r = float(np.sqrt(np.mean(seg ** 2)))
        peaks["rms"] = max(r, peaks["rms"] * np.exp(-dt / 6), 1e-4)
        f["rms"] = float(min(1, r / peaks["rms"]) ** 0.8)
        den = mags[cmask].sum()
        cen = float((freqs[cmask] * mags[cmask]).sum() / den) if den > 1e-9 else 0.0
        f["centroid"] = cen
        f["centroidNorm"] = float(np.clip(np.log2(cen / 100) / np.log2(80), 0, 1)) if cen > 0 else 0.0
        flux = float(np.maximum(0, mags[1:fmax] - prev[1:fmax]).sum()) if prev is not None else 0.0
        prev = mags.copy()
        hist.append((t, flux))
        while hist and t - hist[0][0] > 1:
            hist.pop(0)
        v = np.array([h[1] for h in hist])
        mean, std = v.mean(), v.std()
        flux_mean = flux_mean * 0.98 + flux * 0.02
        thr = max(mean + 1.4 * std, flux_mean * 1.5, 1e-3)
        beat, strength = False, 0.0
        if flux > thr and flux >= prev_flux and t - last_beat >= 0.2:
            beat, strength = True, float(np.clip((flux - thr) / (thr * 2) + 0.4, 0, 1))
            last_beat = t
            beat_times.append(t)
            iv = np.diff(beat_times[-16:])
            iv = np.sort(iv[(iv >= 0.25) & (iv <= 1.2)])
            if len(beat_times) >= 5 and len(iv) >= 3:
                bpm = 60 / iv[len(iv) // 2]
                while bpm < 70: bpm *= 2
                while bpm > 180: bpm /= 2
                tempo = float(bpm)
        prev_flux = flux
        f.update(beat=beat, beatStrength=strength, tempo=tempo, flux=flux / max(flux_mean, 1e-6), t=round(t, 6))
        rows.append(f)
    json.dump({"fps": fps, "frames": nf, "sampleRate": sr, "fft": FFT, "beats": beat_times, "features": rows}, open(out, "w"))
    print(f"WROTE {out}: {nf} frames @ {fps:g} fps, {len(beat_times)} beats, final tempo {tempo:.1f} BPM")


main()
