"""2025年 JRA 全レースで「1年間 ◯◯ を買い続けたら」を検証する。

データは keibamar/keiba_ai_ver3.0 (netkeiba 由来) のレース結果と払戻を使う。
取得は fetch_data.sh を参照。全券種とも 1点100円、払戻は公式の確定配当で計算する。

    python3 backtest.py <keiba_ai_ver3.0 のパス> [出力ディレクトリ]
"""
import glob
import os
import sys
from itertools import combinations

import pandas as pd

YEAR = "2025"
STAKE = 100


def load(root):
    res = pd.concat(
        pd.read_csv(f, dtype=str)
        for f in glob.glob(f"{root}/data/race_result/*/{YEAR}_race_results.csv")
    )
    res = res.rename(columns={res.columns[0]: "rid"})
    # 元データには同じレースが2回入っているものがある（福島の一部）
    res = res.drop_duplicates(["rid", "馬番"])
    res["date"] = pd.to_datetime(res["date"], format="%Y年%m月%d日")
    res["馬番"] = res["馬番"].astype(int)
    res["人気"] = pd.to_numeric(res["人気"], errors="coerce")
    res["単勝"] = pd.to_numeric(res["単勝"], errors="coerce")
    res["pos"] = pd.to_numeric(res["着順"], errors="coerce")  # 中・除・取 は NaN

    ret = pd.concat(
        pd.read_csv(f, dtype=str).assign(rid=os.path.basename(f)[:-4])
        for f in glob.glob(f"{root}/data/race_info/race_returns/*/{YEAR}/*.csv")
    )
    ret["配当"] = ret["配当"].str.replace(",", "").astype(int)
    ret = ret.drop_duplicates(["rid", "式別", "馬番"])

    # 払戻が揃っているレースだけを対象にする
    rids = set(res["rid"]) & set(ret["rid"])
    res = res[res["rid"].isin(rids)]
    ret = ret[ret["rid"].isin(rids)]
    # 出走取消・除外は買えない（返還）ので母集団から外す
    runners = res[~res["着順"].isin(["除", "取"])].copy()

    pay = {}
    for (rid, kind), g in ret.groupby(["rid", "式別"]):
        pay[(rid, kind)] = dict(zip(g["馬番"], g["配当"]))
    return runners, pay


def key(kind, nums):
    if kind in ("単勝", "複勝"):
        return str(nums[0])
    if kind in ("馬単", "三連単"):
        return "→".join(map(str, nums))
    return "-".join(map(str, sorted(nums)))


def payout(pay, rid, kind, nums):
    return pay.get((rid, kind), {}).get(key(kind, nums), 0)


def summarize(name, bets):
    """bets: DataFrame[date, rid, ret] で1行=1点100円"""
    if len(bets) == 0:
        return None
    bets = bets.sort_values(["date", "rid"])
    hit = bets["ret"] > 0
    streak = best = 0
    for h in hit:
        streak = 0 if h else streak + 1
        best = max(best, streak)
    cost = len(bets) * STAKE
    back = int(bets["ret"].sum())
    return {
        "戦略": name,
        "購入点数": len(bets),
        "投資": cost,
        "払戻": back,
        "収支": back - cost,
        "回収率%": round(back / cost * 100, 1),
        "的中率%": round(hit.mean() * 100, 1),
        "最大連敗": best,
        "最高配当": int(bets["ret"].max()),
    }


def balance_curve(bets):
    """日ごとの累計収支（動画のグラフ用）"""
    return (bets["ret"] - STAKE).groupby(bets["date"]).sum().cumsum()


def main(root, out):
    os.makedirs(out, exist_ok=True)
    runners, pay = load(root)
    races = runners.groupby("rid")
    meta = runners.groupby("rid")["date"].first()
    print(f"対象: {YEAR}年 {runners['rid'].nunique()}レース / のべ{len(runners)}頭")

    def single(df, kind="単勝"):
        return pd.DataFrame({
            "date": df["date"].values, "rid": df["rid"].values,
            "ret": [payout(pay, r, kind, [n]) for r, n in zip(df["rid"], df["馬番"])],
        })

    curves = {}
    out_tables = {}

    # 1. 人気別（元ネタの再現）
    rows = []
    for p in range(1, 19):
        sel = runners[runners["人気"] == p]
        for kind in ("単勝", "複勝"):
            s = summarize(f"{p}番人気の{kind}", single(sel, kind))
            if s:
                s.update(人気=p, 券種=kind)
                rows.append(s)
    out_tables["01_人気別"] = pd.DataFrame(rows)

    # 2. 両極端と「全部買い」
    rows = []
    fav = single(runners[runners["人気"] == 1])
    rows.append(summarize("毎レース1番人気の単勝", fav)); curves["1番人気 単勝"] = balance_curve(fav)
    last = runners[runners["人気"] == runners.groupby("rid")["人気"].transform("max")]
    lb = single(last)
    rows.append(summarize("毎レース最低人気の単勝", lb)); curves["最低人気 単勝"] = balance_curve(lb)
    allb = single(runners)
    rows.append(summarize("毎レース全頭の単勝（全通り買い）", allb))
    rows.append(summarize("毎レース全頭の複勝（全通り買い）", single(runners, "複勝")))
    out_tables["02_極端な買い方"] = pd.DataFrame(rows)

    # 3. 人気順どおりの決着に賭ける
    rows = []
    top = {rid: g.sort_values("人気")["馬番"].tolist()[:3] for rid, g in races if g["人気"].notna().sum() >= 3}
    for kind, label in [("馬連", "1-2番人気の馬連"), ("ワイド", "1-2番人気のワイド"),
                        ("馬単", "1→2番人気の馬単"), ("三連複", "1-2-3番人気の三連複"),
                        ("三連単", "1→2→3番人気の三連単")]:
        nums = lambda t: t[:2] if kind in ("馬連", "ワイド", "馬単") else t
        b = pd.DataFrame({"date": [meta[r] for r in top], "rid": list(top),
                          "ret": [payout(pay, r, kind, nums(t)) for r, t in top.items()]})
        rows.append(summarize(label, b))
        if kind == "三連単":
            curves["1→2→3番人気 三連単"] = balance_curve(b)
    # 1-2-3番人気の三連単ボックス（6点）
    from itertools import permutations
    bx = []
    for r, t in top.items():
        for p in permutations(t):
            bx.append((meta[r], r, payout(pay, r, "三連単", list(p))))
    rows.append(summarize("1-2-3番人気の三連単ボックス(6点)", pd.DataFrame(bx, columns=["date", "rid", "ret"])))
    out_tables["03_人気順決着"] = pd.DataFrame(rows)

    # 4. 騎手別：「〇〇騎手の単勝を1年間全部買ったら」
    rows = []
    for j, g in runners.groupby("騎手"):
        if len(g) < 300:
            continue
        b = single(g)
        s = summarize(f"{j}騎手の単勝を全部", b)
        s["騎手"] = j
        s["平均人気"] = round(g["人気"].mean(), 1)
        rows.append(s)
        curves[f"騎手:{j}"] = balance_curve(b)
    out_tables["04_騎手別"] = pd.DataFrame(rows).sort_values("回収率%", ascending=False)

    # 5. 馬番別：「毎レース◯番の単勝」
    rows = []
    for n in range(1, 19):
        s = summarize(f"毎レース{n}番の単勝", single(runners[runners["馬番"] == n]))
        s["馬番"] = n
        rows.append(s)
    out_tables["05_馬番別"] = pd.DataFrame(rows)

    # 6. 誕生日馬券：月-日 の馬連を、その2頭が出ている全レースで買う
    rows = []
    nums_in = {rid: set(g["馬番"]) for rid, g in races}
    for m in range(1, 13):
        for d in range(1, 32):
            try:
                pd.Timestamp(2024, m, d)
            except ValueError:
                continue
            if m == d or d > 18:
                rows.append({"誕生日": f"{m}/{d}", "月": m, "日": d, "購入点数": 0})
                continue
            b = [(meta[r], r, payout(pay, r, "馬連", [m, d])) for r, s in nums_in.items() if m in s and d in s]
            s = summarize(f"{m}月{d}日生まれ：{min(m, d)}-{max(m, d)}の馬連", pd.DataFrame(b, columns=["date", "rid", "ret"]))
            s.update(誕生日=f"{m}/{d}", 月=m, 日=d)
            rows.append(s)
    out_tables["06_誕生日馬連"] = pd.DataFrame(rows)

    # 7. 馬名の文字数
    rows = []
    runners["名前長"] = runners["馬名"].str.len()
    for n, g in runners.groupby("名前長"):
        if len(g) < 200:
            continue
        s = summarize(f"馬名{n}文字の馬の単勝", single(g))
        s["文字数"] = n
        rows.append(s)
    out_tables["07_馬名文字数"] = pd.DataFrame(rows)

    # 8. 性別（牝馬限定じゃないレースで牝馬だけ買う、など）
    rows = []
    runners["性"] = runners["性齢"].str[0]
    for sx, g in runners.groupby("性"):
        rows.append(summarize(f"{sx}馬の単勝を全部", single(g)))
    out_tables["08_性別"] = pd.DataFrame(rows)

    for name, t in out_tables.items():
        t.to_csv(f"{out}/{name}.csv", index=False)
    pd.DataFrame(curves).ffill().fillna(0).astype(int).to_csv(f"{out}/累計収支_日別.csv")
    return out_tables, curves


if __name__ == "__main__":
    root = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(__file__), "results")
    tables, _ = main(root, out)
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 20)
    for name, t in tables.items():
        print(f"\n=== {name} ===")
        print(t.to_string(index=False))
