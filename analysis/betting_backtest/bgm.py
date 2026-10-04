"""動画用のBGMと効果音をその場で合成する（素材ファイル不要・権利フリー）。

128BPM、王道進行（IV-V-iii-vi）のループ。キック・スネア・ハイハット、ベース、
パッド、アルペジオで構成し、結果発表のタイミングでジャーンと終わる。
"""
import wave

import numpy as np

SR = 44100
BPM = 128
BEAT = 60 / BPM
BAR = BEAT * 4

# 王道進行（キー C）: F - G - Em - Am
PROG = [
    (53, [65, 69, 72]),  # F
    (55, [67, 71, 74]),  # G
    (52, [64, 67, 71]),  # Em
    (57, [69, 72, 76]),  # Am
]


def hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def env(n, a=0.005, d=0.1, s=0.6, r=0.05, length=None):
    """ADSR エンベロープ。length は鍵盤を押している長さ（秒）"""
    length = length if length is not None else n / SR
    t = np.arange(n) / SR
    e = np.where(t < a, t / a, np.where(t < a + d, 1 - (1 - s) * (t - a) / d, s))
    rel = t > length
    e[rel] *= np.exp(-(t[rel] - length) / max(r, 1e-3))
    return e


def lowpass(x, cutoff):
    a = np.exp(-2 * np.pi * cutoff / SR)
    y = np.empty_like(x)
    acc = 0.0
    for i, v in enumerate(x):
        acc = (1 - a) * v + a * acc
        y[i] = acc
    return y


def saw(f, n, detune=0.0):
    t = np.arange(n) / SR
    out = 0
    for d in (-detune, 0, detune):
        ph = (f * (1 + d) * t) % 1.0
        out = out + (2 * ph - 1)
    return out / 3


def square(f, n, duty=0.5):
    t = np.arange(n) / SR
    return np.where((f * t) % 1.0 < duty, 1.0, -1.0)


def sine(f, n):
    return np.sin(2 * np.pi * f * np.arange(n) / SR)


class Mix:
    def __init__(self, seconds):
        self.buf = np.zeros(int(seconds * SR) + SR)

    def add(self, t, sig, gain=1.0):
        i = int(t * SR)
        if i >= len(self.buf):
            return
        sig = sig[: len(self.buf) - i]
        self.buf[i:i + len(sig)] += sig * gain


def kick(n=int(0.35 * SR)):
    t = np.arange(n) / SR
    f = 50 + 120 * np.exp(-t * 30)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 9)


def snare(rng, n=int(0.2 * SR)):
    t = np.arange(n) / SR
    noise = rng.uniform(-1, 1, n) * np.exp(-t * 22)
    body = np.sin(2 * np.pi * 190 * t) * np.exp(-t * 30)
    return 0.7 * noise + 0.4 * body


def hat(rng, n=int(0.05 * SR)):
    t = np.arange(n) / SR
    x = rng.uniform(-1, 1, n)
    x = x - lowpass(x, 6000)  # 高域だけ残す
    return x * np.exp(-t * 80)


def crash(rng, n=int(2.5 * SR)):
    t = np.arange(n) / SR
    x = rng.uniform(-1, 1, n)
    x = x - lowpass(x, 3000)
    return x * np.exp(-t * 1.6)


def coin():
    """大穴的中：チャリーン（B5→E6）"""
    out = []
    for m, l in ((83, 0.07), (88, 0.45)):
        n = int(l * SR)
        out.append(square(hz(m), n, 0.25) * env(n, 0.002, 0.05, 0.5, 0.25, l * 0.6))
    return np.concatenate(out) * 0.5


def fanfare():
    """G1勝利：短いファンファーレ（ド・ミ・ソ・ド）"""
    out = []
    for m, l in ((72, 0.1), (76, 0.1), (79, 0.1), (84, 0.5)):
        n = int(l * SR)
        s = saw(hz(m), n, 0.004) + 0.5 * square(hz(m) * 2, n, 0.5)
        out.append(s * env(n, 0.005, 0.05, 0.7, 0.3, l * 0.8))
    return lowpass(np.concatenate(out), 4500) * 0.45


def bell():
    """重賞勝利：キラッ"""
    n = int(0.6 * SR)
    t = np.arange(n) / SR
    return (sine(hz(91), n) + 0.5 * sine(hz(98), n)) * np.exp(-t * 7) * 0.35


def render(path, total, run_start, outro_start, sfx=()):
    """sfx: [(秒, "coin" | "fanfare" | "bell")]"""
    rng = np.random.default_rng(7)
    band = Mix(total)
    k, sn, ht = kick(), snare(rng), hat(rng)

    # イントロ：パッドだけでふわっと始める
    t = 0.0
    bar = 0
    while t < outro_start:
        root, chord = PROG[bar % 4]
        intro = t < run_start
        n = int(BAR * SR)
        # パッド
        pad = sum(saw(hz(m), n, 0.006) for m in chord) / 3
        band.add(t, lowpass(pad * env(n, 0.08, 0.3, 0.8, 0.2, BAR * 0.95), 1800), 0.24)
        # アルペジオ（16分）。イントロから鳴らす
        seq = chord + [chord[0] + 12, chord[1] + 12, chord[2] + 12, chord[1] + 12, chord[0] + 12]
        for i in range(16):
            m = seq[i % len(seq)] + 12
            na = int(BEAT / 4 * 0.9 * SR)
            ar = square(hz(m), na, 0.3) * env(na, 0.002, 0.06, 0.3, 0.03)
            band.add(t + i * BEAT / 4, lowpass(ar, 5000), 0.05 if intro else 0.09)
        if not intro:
            for b in range(4):
                bt = t + b * BEAT
                band.add(bt, k, 0.55)  # 4つ打ち
                if b in (1, 3):
                    band.add(bt, sn, 0.35)
                for h in (0, 0.5):
                    band.add(bt + h * BEAT, ht, 0.2 if h else 0.1)
                # ベース（8分）
                for h in (0, 0.5):
                    nb = int(BEAT * 0.45 * SR)
                    bs = saw(hz(root - 12), nb) + 0.6 * sine(hz(root - 12), nb)
                    band.add(bt + h * BEAT, lowpass(bs * env(nb, 0.003, 0.08, 0.6, 0.03), 900), 0.3)
        t += BAR
        bar += 1

    # 演奏は結果発表の瞬間でぴたっと止める
    mix = Mix(total)
    cut = int(outro_start * SR)
    fade = int(0.03 * SR)
    band.buf[cut - fade:cut] *= np.linspace(1, 0, fade)
    band.buf[cut:] = 0
    mix.buf += band.buf
    # イントロのライザー（ノイズが上がっていく）
    n = int(run_start * SR)
    x = rng.uniform(-1, 1, n)
    rise = (x - lowpass(x, 2000)) * np.linspace(0, 1, n) ** 2
    mix.add(0, rise, 0.25)

    # 結果発表：クラッシュ + Cメジャーでジャーン
    mix.add(outro_start, crash(rng), 0.35)
    mix.add(outro_start, k, 1.0)
    n = int((total - outro_start) * SR)
    for m in (48, 60, 64, 67, 72, 76):
        tone = saw(hz(m), n, 0.006)
        mix.add(outro_start, lowpass(tone * env(n, 0.01, 0.4, 0.7, 1.2, (total - outro_start) * 0.55), 2500), 0.16)

    shots = {"coin": coin(), "fanfare": fanfare(), "bell": bell()}
    for st, kind in sfx:
        mix.add(st, shots[kind], 1.0)

    out = mix.buf[: int(total * SR)]
    # 最後の0.5秒でフェードアウト
    fade = int(0.5 * SR)
    out[-fade:] *= np.linspace(1, 0, fade)
    out = out / max(1e-9, np.abs(out).max()) * 0.85
    pcm = (out * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
