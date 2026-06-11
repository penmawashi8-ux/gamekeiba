#!/usr/bin/env python3
"""実況台本をVOICEVOXで合成し、録画に音声トラックを乗せる"""
import json
import os
import subprocess
import urllib.parse
import urllib.request
import wave

VV = "http://127.0.0.1:50021"
SPEAKER = 13  # 青山龍星
OUT = "/home/user/video_work"
VIDEO = f"{OUT}/video_nosound.mp4"
FINAL = f"{OUT}/keiba_jikkyo.mp4"

# (開始希望秒, テキスト, スタイル)  スタイル: calm=通常 / hype=レース実況
LINES = [
    (1.2,  "みなさんこんにちは！AI実況のリュウセイです。今日はブラウザで遊べるリアルタイム競馬ゲームをプレイしていきます。まずは名前を入力して、レースに参加しましょう。", "calm"),
    (14.0, "第1レース、出走は8頭。注目は4つ星トリオ、ツキノソルジャー、ハナノクイーン、ライジングムーン。中でもツキノソルジャーとハナノクイーンは追い込み型、最後の直線が見ものです。", "calm"),
    (27.0, "さあ、オッズが出ました！1番人気はハナノクイーン、単勝2.9倍。2番人気はツキノソルジャー、3.4倍です。", "calm"),
    (33.5, "私は2番人気、ツキノソルジャーの単勝に5000円！", "calm"),
    (37.5, "さらに1番人気ハナノクイーンの複勝に、残りの5000円。持ち金1万円、全額勝負です！", "calm"),
    (48.0, "馬券は買いました。あとは祈るだけ。まもなくスタートです。", "calm"),
    (56.9, "スタートしました！", "hype"),
    (58.8, "先手を取ったのは7番スターブレイズ！6番カゼノダンサーが続く！", "hype"),
    (65.5, "レースは中盤、依然スターブレイズが先頭！私のツキノソルジャーは3番手、じっと脚をためている！", "hype"),
    (73.5, "さあ勝負どころ！スターブレイズまだ粘る！外からツキノソルジャーが伸びてくる、伸びてくる！", "hype"),
    (80.3, "ツキノソルジャー、先頭に立ったー！", "hype"),
    (83.2, "ツキノソルジャー、1着でゴールイン！やりました！", "hype"),
    (86.5, "2着には大穴ソラノドリーム！3着ハナノクイーン、複勝も的中です！", "hype"),
    (92.0, "いやあ、追い込みが見事に決まりました。あとは最後尾のバラードキング。ゆっくりでいいぞ、がんばれ。", "calm"),
    (100.5, "全馬ゴールして、結果発表です。", "calm"),
    (105.5, "1着ツキノソルジャー、2着ソラノドリーム、3着ハナノクイーン！", "calm"),
    (110.3, "払い戻しは2万4500円、大勝利です！ご視聴ありがとうございました！", "calm"),
]

STYLE = {
    "calm": {"speedScale": 1.15, "intonationScale": 1.15, "pitchScale": 0.0},
    "hype": {"speedScale": 1.3, "intonationScale": 1.45, "pitchScale": 0.03},
}


def synth(text, style, path):
    q = urllib.parse.urlencode({"speaker": SPEAKER, "text": text})
    req = urllib.request.Request(f"{VV}/audio_query?{q}", method="POST")
    query = json.loads(urllib.request.urlopen(req).read())
    query.update(STYLE[style])
    query["volumeScale"] = 1.0
    query["prePhonemeLength"] = 0.05
    query["postPhonemeLength"] = 0.05
    req = urllib.request.Request(
        f"{VV}/synthesis?speaker={SPEAKER}", method="POST",
        data=json.dumps(query).encode(), headers={"Content-Type": "application/json"})
    with open(path, "wb") as f:
        f.write(urllib.request.urlopen(req).read())
    with wave.open(path) as w:
        return w.getnframes() / w.getframerate()


def main():
    dur_video = float(subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", VIDEO]))

    clips = []   # (start_sec, path)
    cursor = 0.0
    for i, (want, text, style) in enumerate(LINES):
        path = f"{OUT}/line_{i:02d}.wav"
        dur = synth(text, style, path)
        start = max(want, cursor + 0.25)
        if start + dur > dur_video - 0.2:
            start = max(cursor + 0.25, dur_video - 0.2 - dur)
        clips.append((start, path))
        cursor = start + dur
        print(f"{i:2d} start={start:6.2f} dur={dur:5.2f} (希望 {want}) {text[:18]}…")

    cmd = ["ffmpeg", "-y", "-v", "error", "-i", VIDEO]
    for _, p in clips:
        cmd += ["-i", p]
    parts, labels = [], []
    for i, (start, _) in enumerate(clips):
        ms = int(start * 1000)
        parts.append(f"[{i+1}:a]adelay={ms}:all=1[a{i}]")
        labels.append(f"[a{i}]")
    fc = ";".join(parts) + f";{''.join(labels)}amix=inputs={len(clips)}:normalize=0[aout]"
    cmd += ["-filter_complex", fc, "-map", "0:v", "-map", "[aout]",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-ar", "44100", FINAL]
    subprocess.run(cmd, check=True)
    print("done:", FINAL)


main()
