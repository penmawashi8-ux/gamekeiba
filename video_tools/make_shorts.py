#!/usr/bin/env python3
"""縦録画からYouTubeショート向け動画を生成する

events_v.json のイベントログから:
- 余計な部分(ログイン・待ち時間)をカットした約55秒の編集タイムラインを構成
- レース展開・勝敗に応じた実況台本を自動生成し、VOICEVOXで合成
- 自前合成のチップチューンBGMを低音量でミックス
- 大きめの焼き込み字幕を付与
"""
import json
import os
import subprocess
import urllib.parse
import urllib.request
import wave

import numpy as np

VV = "http://127.0.0.1:50021"
SPEAKER = 13  # 青山龍星
OUT = os.environ.get("VIDEO_OUT", "/home/user/video_work")
RAW = f"{OUT}/raw_v.webm"
SRC = f"{OUT}/shorts_src.mp4"
SUBS = f"{OUT}/subs_shorts.ass"
BGM = f"{OUT}/bgm.wav"
FINAL = f"{OUT}/keiba_shorts.mp4"

# 冒頭のサイト紹介カード(ボドゲ広場 https://boardgamecat.com)
INTRO_IMG = os.environ.get(
    "INTRO_IMG",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "intro_shorts.png"))
INTRO_SEC = 3.2

STYLE = {
    "calm": {"speedScale": 1.25, "intonationScale": 1.2, "pitchScale": 0.0},
    "hype": {"speedScale": 1.35, "intonationScale": 1.45, "pitchScale": 0.03},
}

ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, BorderStyle, Encoding
Style: calm,Noto Sans CJK JP,62,&H00FFFFFF,&H00000000,&H7F000000,1,4,2,2,40,40,400,1,1
Style: hype,Noto Sans CJK JP,68,&H0000E6FF,&H00000000,&H7F000000,1,4,2,2,40,40,400,1,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def ass_time(sec):
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def wrap_jp(text, width=15):
    lines, cur = [], ""
    for ch in text:
        cur += ch
        if len(cur) >= width:
            cut = max(cur.rfind(p) for p in "、。！？")
            if cut >= width // 2:
                lines.append(cur[:cut + 1])
                cur = cur[cut + 1:]
            else:
                lines.append(cur)
                cur = ""
    if cur:
        lines.append(cur)
    return "\\N".join(lines)


def synth(text, style, path):
    q = urllib.parse.urlencode({"speaker": SPEAKER, "text": text})
    req = urllib.request.Request(f"{VV}/audio_query?{q}", method="POST")
    query = json.loads(urllib.request.urlopen(req).read())
    query.update(STYLE[style])
    query["prePhonemeLength"] = 0.05
    query["postPhonemeLength"] = 0.05
    req = urllib.request.Request(
        f"{VV}/synthesis?speaker={SPEAKER}", method="POST",
        data=json.dumps(query).encode(), headers={"Content-Type": "application/json"})
    with open(path, "wb") as f:
        f.write(urllib.request.urlopen(req).read())
    with wave.open(path) as w:
        return w.getnframes() / w.getframerate()


def make_bgm(path, duration):
    """アップテンポなチップチューン風ループを合成(著作権フリー)"""
    sr = 44100
    bpm = 136
    beat = 60.0 / bpm
    bar = beat * 4
    loop_bars = 8
    loop = np.zeros(int(sr * bar * loop_bars))
    t_loop = np.arange(len(loop)) / sr

    def note(freq, start, dur, vol, duty=0.5, kind="sq"):
        i0, i1 = int(start * sr), min(int((start + dur) * sr), len(loop))
        if i1 <= i0:
            return
        t = np.arange(i1 - i0) / sr
        env = np.exp(-t * 6.0)
        if kind == "sq":
            sig = np.where((t * freq) % 1 < duty, 1.0, -1.0)
        elif kind == "tri":
            sig = 2 * np.abs(2 * ((t * freq) % 1) - 1) - 1
        else:  # noise
            sig = np.random.uniform(-1, 1, len(t))
        loop[i0:i1] += sig * env * vol

    # コード進行: Am - F - C - G ×2
    roots = [110.0, 87.31, 130.81, 98.0] * 2          # A2 F2 C3 G2
    chords = [[220.0, 261.63, 329.63], [174.61, 220.0, 261.63],
              [261.63, 329.63, 392.0], [196.0, 246.94, 293.66]] * 2
    for b in range(loop_bars):
        t0 = b * bar
        ch = chords[b]
        for step in range(8):                          # ベース8分
            note(roots[b], t0 + step * beat / 2, beat * 0.4, 0.20, duty=0.3)
        for step in range(16):                         # アルペジオ16分
            note(ch[step % 3] * 2, t0 + step * beat / 4, beat * 0.22, 0.10)
        for bt in range(4):                            # キック(サイン風トライアングル)
            note(50, t0 + bt * beat, 0.10, 0.85, kind="tri")
        for bt in range(8):                            # ハイハット(裏打ち)
            note(0, t0 + bt * beat / 2 + beat / 4, 0.03, 0.10, kind="noise")
        note(0, t0 + beat, 0.08, 0.25, kind="noise")   # スネア 2拍4拍
        note(0, t0 + beat * 3, 0.08, 0.25, kind="noise")

    reps = int(np.ceil(duration * sr / len(loop)))
    sig = np.tile(loop, reps)[:int(duration * sr)]
    sig = sig / np.max(np.abs(sig)) * 0.9
    fade = int(2.0 * sr)
    sig[-fade:] *= np.linspace(1, 0, fade)
    with wave.open(path, "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((sig * 32767).astype(np.int16).tobytes())


def main():
    ev = json.load(open(f"{OUT}/events_v.json"))
    t0 = next(e["t"] for e in ev if e["kind"] == "video_open")

    def tv(e):
        return e["t"] - t0

    horses = {h["number"]: h for e in ev if e["kind"] == "horses" for h in e["data"]}
    odds_t = tv(next(e for e in ev if e["kind"] == "odds"))
    bet_win = next(e for e in ev if e["kind"] == "bet_win")
    bet_show = next(e for e in ev if e["kind"] == "bet_show")
    race_start_t = tv(next(e for e in ev if e["kind"] == "race_start"))
    results_e = next(e for e in ev if e["kind"] == "results")
    scrolled_t = tv(next(e for e in ev if e["kind"] == "scrolled_results"))
    updates = [e for e in ev if e["kind"] == "race_update"]

    ranking = results_e["data"]["ranking"]
    payouts = results_e["data"]["payouts"]
    my_win_horse, my_show_horse = bet_win["data"]["horse"], bet_show["data"]["horse"]
    name = lambda n: horses[n]["name"]

    finishes = {}
    for e in updates:
        for n, p in e["data"].items():
            if p["finished"] and int(n) not in finishes:
                finishes[int(n)] = tv(e)
    goal_t = finishes[ranking[0]]
    third_t = finishes[ranking[2]]

    def leader_at(t):
        e = min(updates, key=lambda e: abs(tv(e) - t))
        order = sorted(e["data"].items(), key=lambda kv: -kv[1]["progress"])
        return [int(n) for n, _ in order]

    def t_lead_frac(frac):
        for e in updates:
            if max(p["progress"] for p in e["data"].values()) >= frac:
                return tv(e)
        return goal_t

    src_dur = float(subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", RAW]))

    # ── 編集セグメント(元動画の秒数)──
    segs = [
        (odds_t - 0.8, tv(bet_show) + 3.0),      # オッズ発表〜ベット完了
        (race_start_t - 1.2, third_t + 1.8),     # レース(スタート〜3着確定)
        (scrolled_t + 0.4, min(scrolled_t + 9.0, src_dur - 0.3)),  # 払い戻し
    ]
    total = INTRO_SEC + sum(b - a for a, b in segs)
    print("segments:", [(round(a, 1), round(b, 1)) for a, b in segs], "total", round(total, 1))

    def dst(src_t):
        acc = INTRO_SEC
        for a, b in segs:
            if src_t <= b:
                return acc + max(0.0, src_t - a)
            acc += b - a
        return acc

    # ── 実況台本の自動生成 ──
    win_hit = any(p["bet_type"] == "win" for p in payouts)
    show_hit = any(p["bet_type"] == "show" for p in payouts)
    total_payout = sum(p["payout_amount"] for p in payouts)

    mid_t = t_lead_frac(0.55)
    charge = next((tv(e) for e in updates
                   if sorted(e["data"].items(), key=lambda kv: -kv[1]["progress"])[0][0] == str(ranking[0])
                   and max(p["progress"] for p in e["data"].values()) > 0.55), t_lead_frac(0.85))

    def pos_phrase(t, horse):
        order = leader_at(t)
        i = order.index(horse) + 1
        return "先頭" if i == 1 else f"{i}番手"

    lines = [
        # 冒頭カードはカード自体に文字があるので字幕なし(末尾フラグ False)
        (0.4, "この競馬ゲームは、ボドゲ広場でいつでも遊べます！", "calm", False),
        (INTRO_SEC + 0.3, "今日はAIが全財産1万円、勝負します！", "hype"),
        (INTRO_SEC + 4.0, f"買ったのは2番人気{name(my_win_horse)}の単勝と、"
              f"1番人気{name(my_show_horse)}の複勝、5000円ずつ！", "calm"),
        (dst(race_start_t), "スタート！", "hype"),
        (dst(race_start_t) + 2.8, f"先頭は{name(leader_at(race_start_t + 4)[0])}！", "hype"),
        (dst(mid_t), f"レースは中盤、{name(my_win_horse)}は{pos_phrase(mid_t, my_win_horse)}、"
                     f"{name(my_show_horse)}は{pos_phrase(mid_t, my_show_horse)}だ！", "hype"),
        (dst(charge), f"{name(ranking[0])}が伸びる伸びる！", "hype"),
        (dst(goal_t) + 0.2, f"{name(ranking[0])}、1着でゴールイン！", "hype"),
        (dst(third_t) + 0.3, f"2着{name(ranking[1])}、3着{name(ranking[2])}！", "hype"),
    ]
    seg3_t = dst(segs[2][0] + 0.1)
    if win_hit and show_hit:
        lines += [(seg3_t + 0.6, f"単勝も複勝もダブル的中！払い戻し{total_payout}円！", "hype"),
                  (seg3_t + 5.0, "全財産勝負、大勝利です！次のレースもお楽しみに！", "calm")]
    elif show_hit:
        lines += [(seg3_t + 0.6, f"単勝は外れ…でも複勝が的中して{total_payout}円回収！", "calm"),
                  (seg3_t + 5.0, "1万円が6500円に。これが競馬です。リベンジするぞ！", "calm")]
    elif win_hit:
        lines += [(seg3_t + 0.6, f"単勝的中！払い戻し{total_payout}円！", "hype"),
                  (seg3_t + 5.0, "全財産勝負、勝ちました！次のレースもお楽しみに！", "calm")]
    else:
        lines += [(seg3_t + 0.6, "単勝も複勝も外れ…全財産が消えました…", "calm"),
                  (seg3_t + 5.0, "これが競馬です。リベンジは次の動画で！", "calm")]

    # ── 合成・スケジューリング ──
    clips = []
    cursor = 0.0
    for i, line in enumerate(lines):
        want, text, style = line[:3]
        with_sub = line[3] if len(line) > 3 else True
        path = f"{OUT}/sline_{i:02d}.wav"
        dur = synth(text, style, path)
        start = max(want, cursor + 0.2)
        if start + dur > total - 0.2:
            start = max(cursor + 0.2, total - 0.2 - dur)
        clips.append((start, dur, path, text, style, with_sub))
        cursor = start + dur
        print(f"{i:2d} {start:6.2f} +{dur:5.2f} {text[:22]}")

    with open(SUBS, "w") as f:
        f.write(ASS_HEADER)
        for start, dur, _, text, style, with_sub in clips:
            if not with_sub:
                continue
            f.write(f"Dialogue: 0,{ass_time(start)},{ass_time(min(start + dur + 0.3, total))},"
                    f"{style},,0,0,0,,{wrap_jp(text)}\n")

    make_bgm(BGM, total)

    # 元webm → CFR mp4
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", RAW, "-r", "30",
                    "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                    "-pix_fmt", "yuv420p", SRC], check=True)

    # イントロカード + カット編集 + 拡大 + 字幕 + 音声ミックス を1パスで
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", SRC,
           "-loop", "1", "-framerate", "30", "-t", f"{INTRO_SEC}", "-i", INTRO_IMG]
    for _, _, p, _, _, _ in clips:
        cmd += ["-i", p]
    cmd += ["-i", BGM]
    n = len(clips)
    fc = []
    for i, (a, b) in enumerate(segs):
        fc.append(f"[0:v]trim={a:.3f}:{b:.3f},setpts=PTS-STARTPTS[v{i}]")
    fc.append("".join(f"[v{i}]" for i in range(len(segs))) +
              f"concat=n={len(segs)}:v=1:a=0[vc]")
    fc.append(f"[vc]scale=1080:1920:flags=lanczos[vs]")
    fc.append("[1:v]scale=1080:1920,setsar=1[vi]")
    fc.append(f"[vi][vs]concat=n=2:v=1:a=0,format=yuv420p,ass={SUBS}[vout]")
    for i, (start, *_r) in enumerate(clips):
        fc.append(f"[{i+2}:a]adelay={int(start*1000)}:all=1[na{i}]")
    fc.append(f"[{n+2}:a]volume=0.13[bgm]")
    fc.append("".join(f"[na{i}]" for i in range(n)) + "[bgm]" +
              f"amix=inputs={n+1}:normalize=0,volume=5dB[aout]")
    cmd += ["-filter_complex", ";".join(fc), "-map", "[vout]", "-map", "[aout]",
            "-c:v", "libx264", "-preset", "fast", "-crf", "21", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-t", f"{total:.3f}", FINAL]
    subprocess.run(cmd, check=True)
    print("done:", FINAL, f"({total:.1f}s)")


main()
