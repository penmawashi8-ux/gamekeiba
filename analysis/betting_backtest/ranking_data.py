"""年ごとの「騎手の単勝を全部買ったら」ランキング動画用データを作る。

    python3 ranking_data.py <build_dataset.py の出力ディレクトリ> [年 ...]

出力（results/ranking/<年>/）:
    curves.csv   日ごとの累計収支（列＝騎手）
    jockeys.csv  騎手ごとの1年の成績（騎乗数・勝利数・回収率・収支）
    events.csv   100倍以上の的中と G1 勝ち
"""
import json
import os
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
STAKE = 100
FULL_YEAR_RIDES = 300  # 丸1年での対象騎手の下限。途中の年は開催日数で按分する
BIG = 10000           # 100倍以上を高配当として出す


def build(data_dir, year):
    d = pd.read_csv(f"{data_dir}/jra_{year}.csv.gz", dtype={"jockey_id": str, "race_id": str},
                    parse_dates=["date"]).fillna({"race_name": "", "grade": ""})
    bets = d[~d["status"].isin(["除", "取"])].copy()  # 取消・除外は返還

    days = bets["date"].dt.date.nunique()
    # 途中経過の年（12月の開催まで無い年）だけ、例年の開催日数（約108日）で按分する
    partial = bets["date"].max().month < 12
    min_rides = int(round(FULL_YEAR_RIDES * days / 108)) if partial else FULL_YEAR_RIDES

    # 同名の別人がいたら名前の後ろに騎手IDを付ける
    names = bets.groupby("jockey_id")["jockey"].agg(lambda s: s.mode().iloc[0])
    dup = names[names.duplicated(keep=False)]
    names.loc[dup.index] = dup + "(" + dup.index + ")"
    bets["name"] = bets["jockey_id"].map(names)

    st = bets.groupby("name").agg(rides=("race_id", "size"), wins=("finish", lambda x: int((x == 1).sum())),
                                  payout=("win_payout", "sum"))
    st = st[st["rides"] >= min_rides]
    st["回収率%"] = (st["payout"] / st["rides"]).round(1)
    st["収支"] = st["payout"] - st["rides"] * STAKE
    st = st.rename(columns={"rides": "騎乗数", "wins": "勝利数", "payout": "払戻"}).sort_values("収支", ascending=False)

    b = bets[bets["name"].isin(st.index)]
    daily = (b["win_payout"] - STAKE).groupby([b["date"], b["name"]]).sum().unstack(fill_value=0)
    all_days = pd.DatetimeIndex(sorted(bets["date"].unique()))
    curves = daily.reindex(all_days, fill_value=0).cumsum()
    curves.index.name = "date"

    hit = b[(b["win_payout"] >= BIG) | ((b["grade"] == "G1") & (b["win_payout"] > 0))]
    events = pd.DataFrame({"騎手": hit["name"], "date": hit["date"].dt.date, "race_id": hit["race_id"],
                           "レース名": hit["race_name"], "格": hit["grade"], "馬名": hit["horse_name"],
                           "払戻": hit["win_payout"]}).sort_values(["date", "race_id"])

    out = os.path.join(HERE, "results", "ranking", str(year))
    os.makedirs(out, exist_ok=True)
    curves.to_csv(f"{out}/curves.csv")
    st.to_csv(f"{out}/jockeys.csv")
    events.to_csv(f"{out}/events.csv", index=False)
    from build_dataset import KNOWN_GAPS
    meta = {"year": year, "races": int(d.race_id.nunique()), "days": int(days), "min_rides": min_rides,
            "partial": bool(partial), "last_date": str(bets["date"].max().date()), "known_gap": KNOWN_GAPS.get(year, "")}
    json.dump(meta, open(f"{out}/meta.json", "w"), ensure_ascii=False, indent=1)
    print(f"{year}: {d.race_id.nunique()}レース {days}日 対象{len(st)}人（{min_rides}騎乗以上） "
          f"プラス{int((st['収支'] > 0).sum())}人 1位 {st.index[0]} {st['収支'].iloc[0]:+,}円")


if __name__ == "__main__":
    data_dir = sys.argv[1]
    years = [int(y) for y in sys.argv[2:]] or range(2010, 2027)
    for y in years:
        build(data_dir, y)
