"""累計収支が日付とともに伸びていくアニメーション動画（横 1920x1080）を作る。

    python3 make_video.py jockey   # → videos/jockey.mp4
    python3 make_video.py ninki

backtest.py が出力した results/ の CSV を使う。ffmpeg と Noto Sans CJK JP が必要。
"""
import os
import subprocess
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib import font_manager
from matplotlib.patches import Ellipse

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "results")

W, H, FPS = 1920, 1080, 30
AX_RECT = [0.06, 0.10, 0.47, 0.70]  # 折れ線の位置（左, 下, 幅, 高さ）
PX = 0.73                           # 右パネルの左端
DOT = 0.012
INTRO_S, RUN_S, OUTRO_S = 2.0, 30.0, 5.0

# 暗い背景用のカテゴリ色（順番固定。系列の色は順位ではなく系列に付く）
SURFACE = "#1a1a19"
TEXT = "#ffffff"
TEXT2 = "#c3c2b7"
MUTED = "#8a8980"
GRID = "#33332f"
SERIES = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181"]
PLUS, MINUS = "#4cc38a", "#e66767"

PRESETS = {
    "jockey": {
        "title": "トップ騎手の単勝を\n1年間 全部買ったら？",
        "series": [  # (表示名, 累計収支の列名, 結果表, 結果表のキー列, キー)
            ("ルメール", "騎手:ルメール", "04_騎手別", "騎手", "ルメール"),
            ("川田将雅", "騎手:川田将雅", "04_騎手別", "騎手", "川田将雅"),
            ("武豊", "騎手:武豊", "04_騎手別", "騎手", "武豊"),
            ("原優介", "騎手:原優介", "04_騎手別", "騎手", "原優介"),
        ],
        "unit": "騎乗",
    },
    "ninki": {
        "title": "人気馬と穴馬、\n1年間 買い続けたら？",
        "series": [
            ("1番人気 単勝", "1番人気 単勝", "01_人気別", "戦略", "1番人気の単勝"),
            ("2番人気 単勝", "2番人気 単勝", "01_人気別", "戦略", "2番人気の単勝"),
            ("最低人気 単勝", "最低人気 単勝", "02_極端な買い方", "戦略", "毎レース最低人気の単勝"),
            ("三連単 1→2→3人気", "1→2→3番人気 三連単", "03_人気順決着", "戦略", "1→2→3番人気の三連単"),
        ],
        "unit": "レース",
    },
}


def setup_font():
    for f in font_manager.findSystemFonts():
        if "NotoSansCJK" in f:
            font_manager.fontManager.addfont(f)
    plt.rcParams["font.family"] = "Noto Sans CJK JP"


def yen(v, sign=True):
    s = f"{abs(int(round(v))):,}円"
    if not sign:
        return s
    return ("+" if v > 0 else "−" if v < 0 else "±") + s


def man(v):
    """軸目盛り用: 50000 → +5万"""
    if v == 0:
        return "0"
    return ("+" if v > 0 else "−") + f"{abs(v) / 10000:g}万"


def sign_color(v):
    return PLUS if v > 0 else MINUS if v < 0 else TEXT2


def nice_step(span):
    for s in (5000, 10000, 20000, 25000, 50000, 100000):
        if span / s <= 6:
            return s
    return 200000


def spread_labels(ys, gap):
    """ラベルが重ならないよう、y 順を保ったまま最小間隔 gap を空ける"""
    order = np.argsort(ys)
    out = np.array(ys, dtype=float)
    for i in range(1, len(order)):
        a, b = order[i - 1], order[i]
        if out[b] - out[a] < gap:
            out[b] = out[a] + gap
    # 全体を元の中心に戻す
    out += np.mean(ys) - np.mean(out)
    return out


def load(preset):
    curves = pd.read_csv(os.path.join(RES, "累計収支_日別.csv"), index_col=0, parse_dates=True)
    names, cols, finals = [], [], []
    for name, col, table, kcol, key in preset["series"]:
        t = pd.read_csv(os.path.join(RES, f"{table}.csv"))
        row = t[t[kcol] == key].iloc[0]
        names.append(name)
        cols.append(col)
        finals.append(row)
    data = curves[cols].to_numpy(dtype=float)
    # 1月1日を 0 円のスタート地点にする
    dates = np.concatenate([[pd.Timestamp("2025-01-01")], curves.index])
    data = np.vstack([np.zeros(len(cols)), data])
    return names, dates, data, finals


def render(key, out_path, stills=None):
    preset = PRESETS[key]
    names, dates, data, finals = load(preset)
    n_days = len(dates)
    xs = np.array([(d - dates[0]).days for d in dates], dtype=float)
    colors = SERIES[: len(names)]

    fig = plt.figure(figsize=(W / 100, H / 100), dpi=100, facecolor=SURFACE)

    total_frames = int((INTRO_S + RUN_S + OUTRO_S) * FPS)
    run_frames = int(RUN_S * FPS)
    intro_frames = int(INTRO_S * FPS)

    ffmpeg = None if stills else subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgba",
         "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-movflags", "+faststart", out_path],
        stdin=subprocess.PIPE,
    )

    ylo, yhi = -10000.0, 10000.0
    for f in range(total_frames):
        # 進行度 → 何日目まで描くか（小数部分は次の開催日への補間）
        p = min(max((f - intro_frames) / run_frames, 0.0), 1.0)
        pos = p * (n_days - 1)
        k = int(np.floor(pos))
        frac = pos - k
        if k >= n_days - 1:
            k, frac = n_days - 2, 1.0
        head_x = xs[k] + (xs[k + 1] - xs[k]) * frac
        head_y = data[k] + (data[k + 1] - data[k]) * frac
        line_x = np.append(xs[: k + 1], head_x)
        line_y = np.vstack([data[: k + 1], head_y])

        # 縦軸は見えているデータに合わせてなめらかに広げる
        want_lo = min(line_y.min(), 0) * 1.15 - 3000
        want_hi = max(line_y.max(), 0) * 1.15 + 3000
        ylo += (min(want_lo, -10000) - ylo) * 0.2
        yhi += (max(want_hi, 10000) - yhi) * 0.2
        # 大穴が当たった瞬間も線が枠外に出ないようにする
        pad = (yhi - ylo) * 0.04
        ylo = min(ylo, line_y.min() - pad)
        yhi = max(yhi, line_y.max() + pad)
        if stills and f not in stills:
            continue

        fig.clf()
        fig.set_facecolor(SURFACE)
        ax = fig.add_axes(AX_RECT, facecolor=SURFACE)

        # タイトル（左上）
        fig.text(0.04, 0.95, preset["title"].replace("、\n", "、").replace("\n", " "), ha="left", va="top", color=TEXT,
                 fontsize=50, fontweight="bold")
        fig.text(0.04, 0.865, "2025年 JRA全レース ・ 1点100円", ha="left", va="top",
                 color=TEXT2, fontsize=26)

        # 日付（右上）
        cur = dates[0] + pd.Timedelta(days=float(head_x))
        fig.text(PX, 0.87, "2025年", ha="left", va="bottom", color=TEXT2, fontsize=30)
        fig.text(PX, 0.865, f"{cur.month}月{cur.day}日", ha="left", va="top",
                 color=TEXT, fontsize=64, fontweight="bold")

        # 折れ線
        step = nice_step(yhi - ylo)
        ticks = np.arange(np.ceil(ylo / step) * step, yhi + 1, step)
        ax.set_yticks(ticks)
        ax.set_yticklabels([man(t) for t in ticks], color=MUTED, fontsize=22)
        ax.set_ylim(ylo, yhi)
        ax.set_xlim(0, xs[-1])
        months = [pd.Timestamp(2025, m, 1) for m in range(1, 13)]
        ax.set_xticks([(m - dates[0]).days for m in months[::2]])
        ax.set_xticklabels([f"{m.month}月" for m in months[::2]], color=MUTED, fontsize=22)
        ax.tick_params(length=0, pad=10)
        for s in ax.spines.values():
            s.set_visible(False)
        ax.grid(axis="y", color=GRID, linewidth=1.5)
        ax.axhline(0, color=TEXT2, linewidth=2.5, zorder=1)
        for i, c in enumerate(colors):
            ax.plot(line_x, line_y[:, i], color=c, linewidth=5, solid_capstyle="round", zorder=3)
            ax.scatter([head_x], [head_y[i]], s=240, color=c, edgecolor=SURFACE, linewidth=4, zorder=4)

        # 線の先端ラベル（文字は白、色は線と点で示す）
        ax_h_px = AX_RECT[3] * H
        gap = (yhi - ylo) * 84 / ax_h_px
        lab_y = spread_labels(head_y, gap)
        lab_y = np.clip(lab_y, ylo + gap * 0.5, yhi - gap * 0.5)
        lx = head_x + xs[-1] * 0.05
        for i, c in enumerate(colors):
            ty = lab_y[i]
            ax.plot([head_x, lx - xs[-1] * 0.01], [head_y[i], ty], color=c, linewidth=2,
                    alpha=0.7, clip_on=False, zorder=2)
            ax.text(lx, ty + gap * 0.2, names[i], color=TEXT, fontsize=23,
                    fontweight="bold", va="center", ha="left", clip_on=False)
            ax.text(lx, ty - gap * 0.22, yen(head_y[i]), color=sign_color(head_y[i]),
                    fontsize=22, va="center", ha="left", clip_on=False)

        # 右：途中は現在の順位、最後は1年間の結果に切り替える
        rank = np.argsort(-head_y)
        a = min(max((f - intro_frames - run_frames) / (0.6 * FPS), 0.0), 1.0)
        dot = lambda x, y, c, al: fig.patches.append(Ellipse(
            (x, y), DOT, DOT * W / H, transform=fig.transFigure, color=c, alpha=al, figure=fig))
        row_h = 0.13
        if a < 1:
            al = 1 - a
            fig.text(PX, 0.66, "現在の順位", color=TEXT2, fontsize=26, va="top", alpha=al)
            for r, i in enumerate(rank):
                y = 0.56 - r * row_h
                fig.text(PX, y, f"{r + 1}位", color=TEXT2, fontsize=28, va="center", fontweight="bold", alpha=al)
                dot(PX + 0.05, y, colors[i], al)
                fig.text(PX + 0.065, y, names[i], color=TEXT, fontsize=28, va="center", fontweight="bold", alpha=al)
                fig.text(0.965, y - 0.05, yen(head_y[i]), color=sign_color(head_y[i]),
                         fontsize=36, va="center", ha="right", fontweight="bold", alpha=al)
        if a > 0:
            fig.text(PX, 0.66, "1年間の結果", color=TEXT, fontsize=34, va="top", fontweight="bold", alpha=a)
            for r, i in enumerate(rank):
                fr = finals[i]
                y = 0.56 - r * row_h
                dot(PX + 0.007, y, colors[i], a)
                fig.text(PX + 0.022, y, names[i], color=TEXT, fontsize=28, va="center", fontweight="bold", alpha=a)
                fig.text(PX, y - 0.05, f"回収率 {fr['回収率%']:.1f}%", color=TEXT, fontsize=34,
                         va="center", ha="left", fontweight="bold", alpha=a)
                fig.text(0.975, y - 0.05, f"的中{fr['的中率%']:.1f}%", color=TEXT2, fontsize=20,
                         va="center", ha="right", alpha=a)

        fig.canvas.draw()
        if stills:
            fig.savefig(out_path.replace(".mp4", f"_{f}.png"), facecolor=SURFACE)
            continue
        ffmpeg.stdin.write(fig.canvas.buffer_rgba().tobytes())

    if ffmpeg:
        ffmpeg.stdin.close()
        ffmpeg.wait()
    plt.close(fig)


if __name__ == "__main__":
    setup_font()
    os.makedirs(os.path.join(HERE, "videos"), exist_ok=True)
    keys = sys.argv[1:] or list(PRESETS)
    for k in keys:
        out = os.path.join(HERE, "videos", f"{k}.mp4")
        render(k, out)
        print(out)
