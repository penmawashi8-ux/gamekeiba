"""2010年〜の JRA 全レースを1つの形式にそろえ、年ごとの CSV を作る。

主データ:   iinumac/keiba_core の data/warehouse（netkeiba のレースページを解析した
            結果・払戻・レース情報。2010〜2026年）
補完と照合: keibamar/keiba_ai_ver3.0（2019年〜。主データに無いレースを足し、
            重なるレースは着順・オッズ・人気・騎手・単勝払戻を1頭ずつ突き合わせる）

    python3 build_dataset.py <keiba_core> <keiba_ai_ver3.0> <出力ディレクトリ>

出力:
    <出力>/jra_<年>.csv.gz   1行=1頭。単勝の払戻（100円あたり）付き
    coverage.md              年ごとのレース数・照合結果・既知の欠け（このスクリプトの隣に書く）
"""
import glob
import os
import re
import sys

import pandas as pd

from grades import grade as grade_by_name

YEARS = range(2010, 2027)
HERE = os.path.dirname(os.path.abspath(__file__))

# netkeiba の騎手名は全角4文字で切れるので、切れている人だけフルネームに戻す（騎手IDで対応）
FULL_NAME = {
    "01019": "秋山真一郎", "01029": "武士沢友治", "01004": "西田雄一郎", "01123": "小野寺祐太",
    "01150": "石川裕紀人", "01158": "野中悠太郎", "01164": "藤田菜七子", "01197": "佐々木大輔",
    "01204": "河原田菜々", "01212": "柴田裕一郎", "01216": "吉村誠之助", "05525": "藤井勘一郎",
    "05212": "M.デムーロ", "05473": "C.デムーロ",
}

# 主データでは、途中のレースが中止になった日はそれ以降のレースが丸ごと抜けている。
# 2019年以降は補完データで埋まるが、それより前は埋める手段が無い（公式発表で確認済み）
KNOWN_GAPS = {
    2011: "1/16 中山 5R〜12R（4Rが降雪で取りやめ。京成杯を含む8レース）",
    2014: "2/8 京都 5R〜12R、2/17 東京 5R〜12R、2/18 東京 9R〜12R（大雪の代替開催中の取りやめ。計20レース）",
    2018: "2/3 東京 5R〜12R（4Rが降雪で取りやめ。8レース）",
}

# 動画で出すときの通称
SHORT_NAME = {"東京優駿": "日本ダービー", "優駿牝馬": "オークス", "朝日フューチュリティ": "朝日杯FS",
              "阪神ジュベナイルF": "阪神JF", "マイルチャンピオンS": "マイルCS",
              "ホープフルステークス": "ホープフルS", "チャンピオンズカップ": "チャンピオンズC",
              "ジャパンカップ": "ジャパンC", "ジャパンカップダート": "ジャパンCダート"}


def parse_race_name(raw):
    """'第44回有馬記念(G1)' → ('有馬記念', 'G1')"""
    name = re.sub(r"^第\d+回", "", raw or "").strip()
    m = re.search(r"\(([^()]*)\)\s*$", name)
    tag = m.group(1) if m else ""
    if m:
        name = name[: m.start()].strip()
    name = SHORT_NAME.get(name, name)
    if tag in ("G1", "GI", "J.G1", "JGI"):
        g = "G1"
    elif tag in ("G2", "GII", "G3", "GIII", "J.G2", "J.G3", "JGII", "JGIII"):
        g = "重賞"
    else:
        g = ""
    return name, g


def load_core(core, y):
    w = f"{core}/data/warehouse"
    races = pd.read_parquet(f"{w}/races/year={y}")
    res = pd.read_parquet(f"{w}/results/year={y}")
    pay = pd.read_parquet(f"{w}/payouts/year={y}")
    tan = pay[pay.bet_type == "単勝"][["race_id", "combination", "payout"]]
    tan = tan.assign(horse_number=tan["combination"].astype(int)).drop(columns="combination")

    status = res["dnf_reason"].fillna("")
    df = pd.DataFrame({
        "race_id": res["race_id"], "horse_number": res["horse_number"], "horse_name": res["horse_name"],
        "jockey_id": res["jockey_id"].astype(str), "jockey": res["jockey_name"],
        "finish": res["finish_position"], "status": status.where(status != "", "完走"),
        "odds": res["odds"], "popularity": res["popularity"],
    })
    df = df.merge(tan, on=["race_id", "horse_number"], how="left")
    df["win_payout"] = df["payout"].fillna(0).astype(int)
    df = df.drop(columns="payout")
    names = races["race_name"].map(parse_race_name)
    meta = pd.DataFrame({"race_id": races["race_id"], "date": pd.to_datetime(races["date"]),
                         "venue": races["venue_name"], "race_name": names.str[0], "grade": names.str[1]})
    return df.merge(meta, on="race_id", how="left"), set(tan["race_id"])


def load_mama(mama, y):
    fs = glob.glob(f"{mama}/data/race_result/*/{y}_race_results.csv")
    if not fs:
        return None, None
    m = pd.concat(pd.read_csv(f, dtype=str) for f in fs)
    m = m.rename(columns={m.columns[0]: "race_id"}).drop_duplicates(["race_id", "馬番"])
    ret = glob.glob(f"{mama}/data/race_info/race_returns/*/{y}/*.csv")
    tan = None
    if ret:
        t = pd.concat(pd.read_csv(f, dtype=str).assign(race_id=os.path.basename(f)[:-4]) for f in ret)
        t = t[t["式別"] == "単勝"].drop_duplicates(["race_id", "馬番"])
        tan = pd.DataFrame({"race_id": t["race_id"], "horse_number": t["馬番"].astype(int),
                            "payout": t["配当"].str.replace(",", "").astype(int)})
    return m, tan


def from_mama(m, tan, rids, names):
    """補完データの行を主データと同じ形にする"""
    x = m[m["race_id"].isin(rids)]
    pos = pd.to_numeric(x["着順"], errors="coerce")
    st = x["着順"].where(x["着順"].isin(["中", "除", "取"]), "完走")
    df = pd.DataFrame({
        "race_id": x["race_id"].values, "horse_number": x["馬番"].astype(int).values, "horse_name": x["馬名"].values,
        "jockey_id": x["jockey_id"].astype(str).values, "jockey": x["騎手"].values,
        "finish": pos.values, "status": st.values,
        "odds": pd.to_numeric(x["単勝"], errors="coerce").values, "popularity": pd.to_numeric(x["人気"], errors="coerce").values,
        "date": pd.to_datetime(x["date"], format="%Y年%m月%d日").values, "venue": "",
    })
    if tan is not None:
        df = df.merge(tan, on=["race_id", "horse_number"], how="left")
    else:
        df["payout"] = float("nan")
    # 払戻表が無いレースは、同着でなければ確定オッズ×100円が単勝の払戻になる
    wins = df[df["finish"] == 1].groupby("race_id").size()
    no_table = df["payout"].isna() & (df["finish"] == 1)
    dead = df["race_id"].map(wins).fillna(0) > 1
    if (no_table & dead).any():
        raise ValueError(f"払戻表の無い同着レース: {sorted(df[no_table & dead].race_id.unique())}")
    df.loc[no_table, "payout"] = (df.loc[no_table, "odds"] * 100).round()
    df["win_payout"] = df["payout"].fillna(0).astype(int)
    df = df.drop(columns="payout")
    rn = df["race_id"].map(names).fillna("")
    df["race_name"] = rn
    df["grade"] = rn.map(grade_by_name)
    return df


def check_overlap(core_df, m, tan):
    """主データと補完データが重なるレースを1頭ずつ比べ、食い違いの数を返す"""
    mm = m.assign(horse_number=m["馬番"].astype(int))
    j = core_df.merge(mm, on=["race_id", "horse_number"])
    started = ~j["status"].isin(["除", "取"])
    out = {
        "照合した頭数": int(started.sum()),
        "着順": int((pd.to_numeric(j["着順"], errors="coerce").fillna(-1) != j["finish"].fillna(-1)).sum()),
        "単勝オッズ": int((pd.to_numeric(j.loc[started, "単勝"], errors="coerce").round(1) != j.loc[started, "odds"].round(1)).sum()),
        "人気": int((pd.to_numeric(j.loc[started, "人気"], errors="coerce") != j.loc[started, "popularity"]).sum()),
        "騎手ID": int((j["jockey_id_x"] != j["jockey_id_y"].astype(str)).sum()),
        "馬名": int((j["horse_name"] != j["馬名"]).sum()),
    }
    if tan is not None:
        a = core_df[core_df["win_payout"] > 0][["race_id", "horse_number", "win_payout"]]
        both = set(a["race_id"]) & set(tan["race_id"])
        k = a[a.race_id.isin(both)].merge(tan[tan.race_id.isin(both)], on=["race_id", "horse_number"], how="outer")
        out["単勝払戻"] = int((k["win_payout"] != k["payout"]).sum())
    return out


def main(core, mama, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    rows = []
    for y in YEARS:
        df, has_tan = load_core(core, y)
        m, tan = load_mama(mama, y)
        report = {"年": y, "主データ": df.race_id.nunique()}
        added = []
        if m is not None:
            report.update(check_overlap(df, m, tan))
            extra = sorted(set(m["race_id"]) - set(df["race_id"]))
            if extra:
                sched = glob.glob(f"{mama}/data/race_schedule/race_time_id_list/{y}*.csv")
                names = {}
                if sched:
                    sc = pd.concat(pd.read_csv(f, dtype=str) for f in sched).drop_duplicates("race_id")
                    names = dict(zip(sc["race_id"], sc["race_name"]))
                df = pd.concat([df, from_mama(m, tan, extra, names)], ignore_index=True)
                added = extra
        report["補完で追加"] = len(added)

        # 全体の検査
        df["jockey"] = df["jockey_id"].map(FULL_NAME).fillna(df["jockey"])
        fin = df[df["finish"] == 1]
        no_win = set(df.race_id) - set(fin.race_id)
        unpaid = fin[fin["win_payout"] == 0]
        dead = fin.groupby("race_id").size()
        dead = set(dead[dead > 1].index)
        # 同着以外は「払戻＝確定オッズ×100円」になるはず
        nd = fin[~fin.race_id.isin(dead)]
        odd = nd[(nd["odds"] * 100).round() != nd["win_payout"]]
        # 確定後に失格になった馬は、着順は繰り上がっても払戻は確定時のまま（JRAの規定）。
        # その場合は「払戻の無い1着馬」と「払戻のある失格馬」が同じレースに出る
        dq_paid = df[(df["status"] == "失") & (df["win_payout"] > 0)]
        unpaid = unpaid[~unpaid.race_id.isin(dq_paid.race_id)]
        odd = odd[~odd.race_id.isin(dq_paid.race_id)]
        report.update({"レース数": df.race_id.nunique(), "開催日数": df.date.dt.date.nunique(),
                       "勝ち馬なし": len(no_win), "払戻なしの勝ち馬": len(unpaid), "同着": len(dead),
                       "確定後の失格": len(dq_paid),
                       "払戻とオッズの不一致": len(odd), "既知の欠け": KNOWN_GAPS.get(y, "")})
        assert not no_win and unpaid.empty and odd.empty, (y, no_win, unpaid, odd)
        if len(odd):
            print(y, "払戻とオッズの不一致", odd[["race_id", "horse_number", "odds", "win_payout"]].head().to_string())
        rows.append(report)
        cols = ["race_id", "date", "venue", "race_name", "grade", "horse_number", "horse_name",
                "jockey_id", "jockey", "status", "finish", "popularity", "odds", "win_payout"]
        df[cols].sort_values(["race_id", "horse_number"]).to_csv(f"{out_dir}/jra_{y}.csv.gz", index=False)
        print(y, report)
    write_coverage(pd.DataFrame(rows))


def write_coverage(rep):
    lines = ["# データの網羅性と照合結果", "",
             "`build_dataset.py` が出力する。主データ＝iinumac/keiba_core、補完・照合＝keibamar/keiba_ai_ver3.0。", "",
             "| 年 | レース数 | 開催日 | 補完で追加 | 照合した頭数 | 着順 | 単勝オッズ | 人気 | 騎手ID | 単勝払戻 | 同着 | 確定後の失格 | 既知の欠け |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|"]
    for r in rep.to_dict("records"):
        g = lambda k: "" if pd.isna(r.get(k)) else str(int(r[k]))
        lines.append(f"| {r['年']} | {r['レース数']:,} | {r['開催日数']} | {r['補完で追加']} | {g('照合した頭数')} | {g('着順')} | "
                     f"{g('単勝オッズ')} | {g('人気')} | {g('騎手ID')} | {g('単勝払戻')} | {r['同着']} | {r['確定後の失格']} | {r['既知の欠け'] or 'なし'} |")
    lines += ["", "- 「着順」〜「単勝払戻」は、2つのデータで食い違った数（0なら完全一致）。照合は2019年以降のみ",
              "- 全年で「勝ち馬のいないレース」「払戻の無い勝ち馬」「同着以外で払戻≠確定オッズ×100円」は0件",
              "  （確定後に失格した馬は、規定どおり確定時の払戻をそのまま使う。2014年12/7中山2R、2020年11/7東京4R）",
              "- 2021年の騎手ID 1件は、補完データ側のIDの書式崩れ（川又賢治）で、主データは正しい",
              "- 2026年は9月27日までの途中経過"]
    open(os.path.join(HERE, "coverage.md"), "w").write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main(*sys.argv[1:4])
