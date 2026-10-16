#!/usr/bin/env python3
"""Print level, spectral balance and width of a rendered mix.

Usage: measure_mp3.py path/to/song.mp3
"""
import os
import sys
import time

import librosa
import numpy as np

BANDS = [(20, 60), (60, 120), (120, 250), (250, 500), (500, 2000), (2000, 5000), (5000, 10000), (10000, 20000)]


def db(x):
    return 20 * np.log10(x)


def main(path):
    print("rendered", time.ctime(os.path.getmtime(path)))
    y, sr = librosa.load(path, sr=44100, mono=False)
    m = y.mean(0)
    print("dur %.1fs  peak %.2f dBFS  RMS %.2f dBFS" % (len(m) / sr, db(np.abs(y).max()), db(np.sqrt((m ** 2).mean()))))
    print("clipped samples (>= -0.1 dBFS): %d" % (np.abs(y) >= 10 ** (-0.1 / 20)).sum())
    S = np.abs(librosa.stft(m, n_fft=4096)) ** 2
    f = librosa.fft_frequencies(sr=sr, n_fft=4096)
    for lo, hi in BANDS:
        print(f"{lo:>6}-{hi:<6} {100 * S[(f >= lo) & (f < hi)].sum() / S.sum():5.1f}%")
    w = int(sr * 0.4)
    r = np.array([np.sqrt((m[i:i + w] ** 2).mean()) for i in range(0, len(m) - w, w)])
    print("short-term RMS p10/p50/p95: %.1f %.1f %.1f" % tuple(np.percentile(db(r[r > 1e-5]), [10, 50, 95])))
    s = (y[0] - y[1]) / 2
    print("side/mid %.2f" % ((s ** 2).sum() / (m ** 2).sum()))


if __name__ == "__main__":
    main(sys.argv[1])
