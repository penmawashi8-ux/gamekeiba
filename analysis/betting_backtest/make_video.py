"""累計収支が日付とともに伸びていくアニメーション動画（横 1920x1080・BGM付き）を作る。

    python3 make_video.py jockey   # → videos/jockey.mp4
    python3 make_video.py ninki
    python3 make_video.py ranking  # 騎手の収支 TOP10 が入れ替わっていくバーチャートレース

backtest.py が出力した results/ の CSV を使う。ffmpeg と Noto Sans CJK JP が必要。
高配当（preset の big 以上の払戻）はカードで、重賞勝ちは上部の速報欄で馬名と一緒に出す。
"""
import os
import subprocess
import sys
import tempfile

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib import font_manager
from matplotlib.patches import Ellipse, FancyBboxPatch

import bgm

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "results")

W, H, FPS = 1920, 1080, 30
AX_RECT = [0.06, 0.08, 0.47, 0.62]  # 折れ線の位置（左, 下, 幅, 高さ）
PX = 0.73                           # 右パネルの左端
DOT = 0.012
INTRO_S, RUN_S, OUTRO_S = 2.5, 50.0, 6.5
CARD_S = 2.6   # 高配当カードを出す秒数
FEED_S = 1.6   # 重賞速報1件あたりの秒数

# 暗い背景用のカテゴリ色（順番固定。系列の色は順位ではなく系列に付く）
SURFACE = "#1a1a19"
CARD = "#262624"
TEXT = "#ffffff"
TEXT2 = "#c3c2b7"
MUTED = "#8a8980"
GRID = "#33332f"
SERIES = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181"]
PLUS, MINUS = "#4cc38a", "#e66767"

PRESETS = {
    "jockey": {
        "title": "騎手の単勝を 1年間 全部買ったら？",
        "sub": "2025年 JRA全レース ・ 1点100円 ・ 勝利数トップ3 vs 回収率1位（300騎乗以上）",
        "series": [  # (表示名, 肩書き, 累計収支の列名, 結果表, 結果表のキー列, キー)
            ("ルメール", "勝利数1位", "騎手:ルメール", "04_騎手別", "騎手", "ルメール"),
            ("戸崎圭太", "勝利数2位", "騎手:戸崎圭太", "04_騎手別", "騎手", "戸崎圭太"),
            ("松山弘平", "勝利数3位", "騎手:松山弘平", "04_騎手別", "騎手", "松山弘平"),
            ("原優介", "回収率1位", "騎手:原優介", "04_騎手別", "騎手", "原優介"),
        ],
        "big": 3000,     # 30倍以上はカードで見せる
        "feed": True,    # 重賞勝ちを速報欄に出す
    },
    "ninki": {
        "title": "人気馬と穴馬、1年間 買い続けたら？",
        "sub": "2025年 JRA全レース ・ 1点100円",
        "series": [
            ("1番人気 単勝", "", "1番人気 単勝", "01_人気別", "戦略", "1番人気の単勝"),
            ("2番人気 単勝", "", "2番人気 単勝", "01_人気別", "戦略", "2番人気の単勝"),
            ("最低人気 単勝", "", "最低人気 単勝", "02_極端な買い方", "戦略", "毎レース最低人気の単勝"),
            ("三連単 1→2→3人気", "", "1→2→3番人気 三連単", "03_人気順決着", "戦略", "1→2→3番人気の三連単"),
        ],
        "big": 10000,    # 1番人気は重賞を勝ちすぎるので、速報は出さず100倍以上だけ見せる
        "feed": False,
    },
}


def setup_font():
    for f in font_manager.findSystemFonts():
        if "NotoSansCJK" in f:
            font_manager.fontManager.addfont(f)
    plt.rcParams["font.family"] = "Noto Sans CJK JP"


def yen(v):
    return ("+" if v > 0 else "−" if v < 0 else "±") + f"{abs(int(round(v))):,}円"


def man(v):
    """軸目盛り用: 50000 → +5万"""
    if v == 0:
        return "0"
    return ("+" if v > 0 else "−") + f"{abs(v) / 10000:g}万"


def odds(payout):
    return f"{payout / 100:.1f}倍"


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
    out += np.mean(ys) - np.mean(out)
    return out


def load(preset):
    curves = pd.read_csv(os.path.join(RES, "累計収支_日別.csv"), index_col=0, parse_dates=True)
    names, tags, cols, finals = [], [], [], []
    for name, tag, col, table, kcol, key in preset["series"]:
        t = pd.read_csv(os.path.join(RES, f"{table}.csv"))
        finals.append(t[t[kcol] == key].iloc[0])
        names.append(name)
        tags.append(tag)
        cols.append(col)
    data = curves[cols].to_numpy(dtype=float)
    # 1月1日を 0 円のスタート地点にする
    dates = np.concatenate([[pd.Timestamp("2025-01-01")], curves.index])
    data = np.vstack([np.zeros(len(cols)), data])

    ev = pd.read_csv(os.path.join(RES, "的中イベント.csv"), parse_dates=["date"]).fillna("")
    ev = ev[ev["系列"].isin(cols)].copy()
    ev["i"] = ev["系列"].map({c: i for i, c in enumerate(cols)})
    ev["day"] = ev["date"].map({d: k for k, d in enumerate(dates)})
    return names, tags, dates, data, finals, ev


def schedule(preset, ev, day_frame):
    """どのフレームで何を出すか決める。返り値: (大穴カード, 重賞速報, 効果音)"""
    cards = []
    for _, e in ev[ev["払戻"] >= preset["big"]].sort_values("date").iterrows():
        cards.append(dict(e, f0=day_frame(e["day"])))
    feed = []
    if preset["feed"]:
        t = 0
        for _, e in ev[ev["格"] != ""].sort_values(["date", "格"]).iterrows():
            # 同じ週に重なったら順番に出す
            t = max(day_frame(e["day"]), t)
            feed.append(dict(e, f0=t))
            t += int(FEED_S * FPS * 0.6)
    sfx = [(c["f0"] / FPS, "coin") for c in cards]
    sfx += [(x["f0"] / FPS, "fanfare" if x["格"] == "G1" else "bell") for x in feed]
    return cards, feed, sfx


def render(key, out_path, stills=None):
    preset = PRESETS[key]
    names, tags, dates, data, finals, ev = load(preset)
    n_days = len(dates)
    xs = np.array([(d - dates[0]).days for d in dates], dtype=float)
    colors = SERIES[: len(names)]

    total_frames = int((INTRO_S + RUN_S + OUTRO_S) * FPS)
    run_frames = int(RUN_S * FPS)
    intro_frames = int(INTRO_S * FPS)
    day_frame = lambda k: intro_frames + int(round(run_frames * k / (n_days - 1)))
    cards, feed, sfx = schedule(preset, ev, day_frame)

    fig = plt.figure(figsize=(W / 100, H / 100), dpi=100, facecolor=SURFACE)
    video = out_path if stills else tempfile.mktemp(suffix=".mp4", dir=os.path.dirname(out_path))
    ffmpeg = None if stills else subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgba",
         "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", video],
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
        dot = lambda x, y, c, al=1.0, z=1: fig.patches.append(Ellipse(
            (x, y), DOT, DOT * W / H, transform=fig.transFigure, color=c, alpha=al, figure=fig, zorder=z))

        # タイトル（左上）
        fig.text(0.04, 0.955, preset["title"], ha="left", va="top", color=TEXT, fontsize=50, fontweight="bold")
        fig.text(0.04, 0.868, preset["sub"], ha="left", va="top", color=TEXT2, fontsize=22)

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
        # G1 を勝った地点に星を残す
        for x in feed:
            if x["格"] == "G1" and f >= x["f0"]:
                ax.scatter([xs[x["day"]]], [data[x["day"], x["i"]]], marker="*", s=420,
                           color=TEXT, edgecolor=colors[x["i"]], linewidth=1.5, zorder=5)

        # 線の先端ラベル（文字は白、色は線と点で示す）
        gap = (yhi - ylo) * 84 / (AX_RECT[3] * H)
        lab_y = np.clip(spread_labels(head_y, gap), ylo + gap * 0.5, yhi - gap * 0.5)
        lx = head_x + xs[-1] * 0.05
        for i, c in enumerate(colors):
            ty = lab_y[i]
            ax.plot([head_x, lx - xs[-1] * 0.01], [head_y[i], ty], color=c, linewidth=2,
                    alpha=0.7, clip_on=False, zorder=2)
            ax.text(lx, ty + gap * 0.2, names[i], color=TEXT, fontsize=23,
                    fontweight="bold", va="center", ha="left", clip_on=False)
            ax.text(lx, ty - gap * 0.22, yen(head_y[i]), color=sign_color(head_y[i]),
                    fontsize=22, va="center", ha="left", clip_on=False)

        # 重賞速報（グラフの上の帯。新しいものが上、最大2件）
        live = [x for x in feed if x["f0"] <= f < x["f0"] + FEED_S * FPS][-2:][::-1]
        for r, x in enumerate(live):
            al = min((f - x["f0"]) / 6, 1.0, (x["f0"] + FEED_S * FPS - f) / 6)
            y = 0.795 - r * 0.048
            g1 = x["格"] == "G1"
            fig.patches.append(FancyBboxPatch(
                (0.04, y - 0.017), 0.05, 0.034, boxstyle="round,pad=0,rounding_size=0.006",
                transform=fig.transFigure, facecolor=TEXT if g1 else "none", edgecolor=TEXT,
                linewidth=1.5, alpha=al, figure=fig))
            fig.text(0.065, y, "G1" if g1 else "重賞", color=SURFACE if g1 else TEXT, fontsize=18,
                     fontweight="bold", ha="center", va="center", alpha=al)
            rt = fig.text(0.10, y, x["レース名"], color=TEXT, fontsize=26, fontweight="bold", va="center", alpha=al)
            x1 = 0.10 + rt.get_window_extent(renderer=fig.canvas.get_renderer()).width / W
            dot(x1 + 0.015, y, colors[x["i"]], al)
            fig.text(x1 + 0.028, y,
                     f"{names[x['i']]} × {x['馬名']}（単勝{odds(x['払戻'])}）",
                     color=TEXT2, fontsize=24, va="center", alpha=al)

        # 高配当カード：線の先端と反対側の上部に出す
        live = [c for c in cards if c["f0"] <= f < c["f0"] + CARD_S * FPS]
        for r, c in enumerate(live[-2:]):
            t = (f - c["f0"]) / FPS
            al = min(t / 0.15, 1.0, (CARD_S - t) / 0.25)
            pop = 1 + 0.08 * max(0, 1 - t / 0.2)
            # 横は線の先端ラベルより右（先端が右半分なら左端）、縦はその系列の線と反対側
            hf = head_x / xs[-1]
            fx = max(0.55, hf + 0.40) if hf < 0.5 else 0.03
            x0 = min(AX_RECT[0] + AX_RECT[2] * fx, PX - 0.02 - 0.27)
            w, h = 0.27 * pop, 0.19 * pop
            up = (head_y[c["i"]] - ylo) / (yhi - ylo) < 0.5
            y0 = (AX_RECT[1] + AX_RECT[3] - 0.01 - h - r * (h + 0.02)) if up else (AX_RECT[1] + 0.03 + r * (h + 0.02))
            fig.patches.append(FancyBboxPatch(
                (x0, y0), w, h, boxstyle="round,pad=0,rounding_size=0.012", transform=fig.transFigure,
                facecolor=CARD, edgecolor=colors[c["i"]], linewidth=4, alpha=al, figure=fig, zorder=8))
            dot(x0 + 0.02, y0 + h - 0.04, colors[c["i"]], al, 9)
            fig.text(x0 + 0.035, y0 + h - 0.04, f"{names[c['i']]}　高配当！", color=TEXT, fontsize=24,
                     fontweight="bold", va="center", alpha=al, zorder=9)
            kind = "三連単" if "三連単" in names[c["i"]] else "単勝"
            fig.text(x0 + 0.02, y0 + h * 0.45, f"{kind} {odds(c['払戻'])}", color=PLUS, fontsize=46 * pop,
                     fontweight="bold", va="center", alpha=al, zorder=9)
            sub = f"{c['馬名']}　{c['レース名']}" if c["馬名"] else c["レース名"]
            fig.text(x0 + 0.02, y0 + 0.03, sub, color=TEXT2, fontsize=20, va="center", alpha=al, zorder=9)

        # 右：途中は現在の順位、最後は1年間の結果に切り替える
        rank = np.argsort(-head_y)
        a = min(max((f - intro_frames - run_frames) / (0.6 * FPS), 0.0), 1.0)
        row_h = 0.13
        if a < 1:
            al = 1 - a
            fig.text(PX, 0.66, "現在の順位", color=TEXT2, fontsize=26, va="top", alpha=al)
            for r, i in enumerate(rank):
                y = 0.56 - r * row_h
                fig.text(PX, y, f"{r + 1}位", color=TEXT2, fontsize=28, va="center", fontweight="bold", alpha=al)
                dot(PX + 0.05, y, colors[i], al)
                fig.text(PX + 0.065, y, names[i], color=TEXT, fontsize=28, va="center", fontweight="bold", alpha=al)
                if tags[i]:
                    fig.text(0.975, y, tags[i], color=MUTED, fontsize=18, va="center", ha="right", alpha=al)
                fig.text(0.965, y - 0.05, yen(head_y[i]), color=sign_color(head_y[i]),
                         fontsize=34, va="center", ha="right", fontweight="bold", alpha=al)
        if a > 0:
            fig.text(PX, 0.66, "1年間の結果", color=TEXT, fontsize=34, va="top", fontweight="bold", alpha=a)
            for r, i in enumerate(rank):
                fr = finals[i]
                y = 0.56 - r * row_h
                dot(PX + 0.007, y, colors[i], a)
                fig.text(PX + 0.022, y, names[i], color=TEXT, fontsize=28, va="center", fontweight="bold", alpha=a)
                if tags[i]:
                    fig.text(0.975, y, tags[i], color=MUTED, fontsize=18, va="center", ha="right", alpha=a)
                fig.text(PX, y - 0.05, f"回収率 {fr['回収率%']:.1f}%", color=TEXT, fontsize=34,
                         va="center", ha="left", fontweight="bold", alpha=a)
                fig.text(0.975, y - 0.05, f"的中{fr['的中率%']:.1f}%", color=TEXT2, fontsize=20,
                         va="center", ha="right", alpha=a)

        fig.canvas.draw()
        if stills:
            fig.savefig(out_path.replace(".mp4", f"_{f}.png"), facecolor=SURFACE)
            continue
        ffmpeg.stdin.write(fig.canvas.buffer_rgba().tobytes())

    plt.close(fig)
    if not ffmpeg:
        return
    ffmpeg.stdin.close()
    ffmpeg.wait()

    mux_audio(video, out_path, total_frames, sfx)


def mux_audio(video, out_path, total_frames, sfx):
    """BGM と効果音を合成して載せる（音量は放送基準くらいに揃える）"""
    wav = video.replace(".mp4", ".wav")
    bgm.render(wav, total_frames / FPS, INTRO_S, INTRO_S + RUN_S, sfx)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", video, "-i", wav,
                    "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                    "-ar", "44100", "-shortest", "-movflags", "+faststart", out_path], check=True)
    os.remove(video)
    os.remove(wav)


# ---------------------------------------------------------------------------
# 騎手の収支ランキング TOP10 の変動（バーチャートレース）
# ---------------------------------------------------------------------------
RACE_TOP = 10
RACE_BIG = 10000  # 100倍以上の的中と G1 勝ちを右の速報に出す


def render_race(out_path, stills=None):
    curves = pd.read_csv(os.path.join(RES, "累計収支_日別.csv"), index_col=0, parse_dates=True)
    cols = [c for c in curves.columns if c.startswith("騎手:")]
    names = [c[3:] for c in cols]
    table = pd.read_csv(os.path.join(RES, "04_騎手別.csv")).set_index("騎手")
    dates = np.concatenate([[pd.Timestamp("2025-01-01")], curves.index])
    data = np.vstack([np.zeros(len(cols)), curves[cols].to_numpy(dtype=float)])
    n_days, n = len(dates), len(cols)
    xs = np.array([(d - dates[0]).days for d in dates], dtype=float)

    total_frames = int((INTRO_S + RUN_S + OUTRO_S) * FPS)
    run_frames = int(RUN_S * FPS)
    intro_frames = int(INTRO_S * FPS)
    day_frame = lambda k: intro_frames + int(round(run_frames * k / (n_days - 1)))

    ev = pd.read_csv(os.path.join(RES, "的中イベント.csv"), parse_dates=["date"]).fillna("")
    ev = ev[ev["系列"].isin(cols) & ((ev["払戻"] >= RACE_BIG) | (ev["格"] == "G1"))].copy()
    ev["i"] = ev["系列"].map({c: i for i, c in enumerate(cols)})
    ev["day"] = ev["date"].map({d: k for k, d in enumerate(dates)})
    ev = ev.sort_values(["date", "払戻"])
    ev["f0"] = [day_frame(d) for d in ev["day"]]
    sfx = [(r.f0 / FPS, "fanfare" if r.格 == "G1" else "coin") for r in ev.itertuples()]

    fig = plt.figure(figsize=(W / 100, H / 100), dpi=100, facecolor=SURFACE)
    video = out_path if stills else tempfile.mktemp(suffix=".mp4", dir=os.path.dirname(out_path))
    ffmpeg = None if stills else subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgba",
         "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", video],
        stdin=subprocess.PIPE,
    )

    bx = [0.17, 0.06, 0.45, 0.72]  # 棒グラフの位置
    pos_y = np.full(n, RACE_TOP + 2.0)  # 表示上の順位（なめらかに動かす）
    xlo, xhi = -5000.0, 5000.0
    for f in range(total_frames):
        p = min(max((f - intro_frames) / run_frames, 0.0), 1.0)
        pos = p * (n_days - 1)
        k = int(np.floor(pos))
        frac = pos - k
        if k >= n_days - 1:
            k, frac = n_days - 2, 1.0
        head_x = xs[k] + (xs[k + 1] - xs[k]) * frac
        val = data[k] + (data[k + 1] - data[k]) * frac
        # 同額なら名前順で固定（ちらつき防止）
        order = sorted(range(n), key=lambda i: (-round(val[i]), names[i]))
        rank = np.empty(n)
        rank[order] = np.arange(n)
        pos_y += (rank - pos_y) * 0.25
        top = order[:RACE_TOP]
        lo, hi = min(0, val[top].min()), max(0, val[top].max())
        xlo += (lo * 1.3 - 2000 - xlo) * 0.15
        xhi += (hi * 1.3 + 2000 - xhi) * 0.15
        if stills and f not in stills:
            continue

        fig.clf()
        fig.set_facecolor(SURFACE)
        ax = fig.add_axes(bx, facecolor=SURFACE)
        fig.text(0.04, 0.955, "騎手の単勝を 1年間 全部買ったら？ 収支TOP10", ha="left", va="top",
                 color=TEXT, fontsize=44, fontweight="bold")
        fig.text(0.04, 0.868, f"2025年 JRA全レース ・ 1点100円 ・ 300騎乗以上の{n}人", ha="left", va="top",
                 color=TEXT2, fontsize=22)
        cur = dates[0] + pd.Timedelta(days=float(head_x))
        fig.text(PX, 0.87, "2025年", ha="left", va="bottom", color=TEXT2, fontsize=30)
        fig.text(PX, 0.865, f"{cur.month}月{cur.day}日", ha="left", va="top",
                 color=TEXT, fontsize=64, fontweight="bold")

        ax.set_xlim(xlo, xhi)
        ax.set_ylim(RACE_TOP - 0.4, -0.6)
        ax.set_yticks([])
        step = nice_step(xhi - xlo)
        ticks = np.arange(np.ceil(xlo / step) * step, xhi + 1, step)
        ax.set_xticks(ticks)
        ax.set_xticklabels([man(t) for t in ticks], color=MUTED, fontsize=20)
        ax.xaxis.tick_top()
        ax.tick_params(length=0, pad=6)
        for s in ax.spines.values():
            s.set_visible(False)
        ax.grid(axis="x", color=GRID, linewidth=1.5)
        ax.axvline(0, color=TEXT2, linewidth=2.5, zorder=1)

        recent = {r.i for r in ev.itertuples() if r.f0 <= f < r.f0 + 1.8 * FPS}
        span = xhi - xlo
        for i in range(n):
            y = pos_y[i]
            if y > RACE_TOP - 0.3:
                continue
            al = float(np.clip((RACE_TOP - 0.3 - y) / 0.5, 0, 1))
            v = val[i]
            ax.barh(y, v, height=0.72, color=PLUS if v >= 0 else MINUS, alpha=0.85 * al, zorder=3,
                    edgecolor=TEXT if i in recent else "none", linewidth=3)
            # 順位と名前は左の列に固定、金額は棒の先に出す
            ax.text(xlo - span * 0.03, y, names[i], color=TEXT, fontsize=26, fontweight="bold",
                    ha="right", va="center", alpha=al, clip_on=False)
            ax.text(xlo - span * 0.30, y, f"{int(rank[i]) + 1}", color=MUTED, fontsize=24,
                    fontweight="bold", ha="right", va="center", alpha=al, clip_on=False)
            ax.text(v + (span * 0.012 if v >= 0 else -span * 0.012), y, yen(v), color=TEXT, fontsize=21,
                    ha="left" if v >= 0 else "right", va="center", alpha=al, zorder=4)

        # 右：速報（新しいものが上）→ 最後は1年間の回収率 TOP10
        a = min(max((f - intro_frames - run_frames) / (0.6 * FPS), 0.0), 1.0)
        if a < 1:
            al = 1 - a
            fig.text(PX, 0.66, "速報", color=TEXT2, fontsize=26, va="top", alpha=al)
            shown = [r for r in ev.itertuples() if r.f0 <= f][-5:][::-1]
            for j, r in enumerate(shown):
                y = 0.585 - j * 0.105
                fa = al * min((f - r.f0) / 8, 1.0)
                g1 = r.格 == "G1"
                fig.patches.append(FancyBboxPatch(
                    (PX, y - 0.016), 0.05, 0.032, boxstyle="round,pad=0,rounding_size=0.006",
                    transform=fig.transFigure, facecolor=TEXT if g1 else PLUS, edgecolor="none",
                    alpha=fa, figure=fig))
                fig.text(PX + 0.025, y, "G1" if g1 else "高配当", color=SURFACE, fontsize=15,
                         fontweight="bold", ha="center", va="center", alpha=fa)
                head = r.レース名 if g1 else f"単勝 {odds(r.払戻)}"
                fig.text(PX + 0.06, y, head, color=TEXT, fontsize=24, fontweight="bold", va="center", alpha=fa)
                fig.text(PX, y - 0.042, f"{r.date.month}/{r.date.day}  {names[r.i]} × {r.馬名}",
                         color=TEXT2, fontsize=19, va="center", alpha=fa)
        if a > 0:
            fig.text(PX, 0.66, "1年間の回収率", color=TEXT, fontsize=30, va="top", fontweight="bold", alpha=a)
            for j, i in enumerate(order[:RACE_TOP]):
                y = 0.59 - j * 0.052
                fig.text(PX, y, f"{j + 1}", color=MUTED, fontsize=20, fontweight="bold", va="center", alpha=a)
                fig.text(PX + 0.025, y, names[i], color=TEXT, fontsize=22, fontweight="bold", va="center", alpha=a)
                fig.text(0.975, y, f"{table.loc[names[i], '回収率%']:.1f}%", color=TEXT, fontsize=22,
                         ha="right", va="center", alpha=a)

        fig.canvas.draw()
        if stills:
            fig.savefig(out_path.replace(".mp4", f"_{f}.png"), facecolor=SURFACE)
            continue
        ffmpeg.stdin.write(fig.canvas.buffer_rgba().tobytes())

    plt.close(fig)
    if ffmpeg:
        ffmpeg.stdin.close()
        ffmpeg.wait()
        mux_audio(video, out_path, total_frames, sfx)


if __name__ == "__main__":
    setup_font()
    os.makedirs(os.path.join(HERE, "videos"), exist_ok=True)
    for k in sys.argv[1:] or list(PRESETS) + ["ranking"]:
        out = os.path.join(HERE, "videos", f"{k}.mp4")
        render_race(out) if k == "ranking" else render(k, out)
        print(out)
