"""テスト用CSV生成スクリプト。 python make_test_csv.py [行数] [出力先]"""
import csv, sys, random, datetime

rows = int(sys.argv[1]) if len(sys.argv) > 1 else 100_000
out = sys.argv[2] if len(sys.argv) > 2 else "test_data.csv"

names = ["佐藤","鈴木","高橋","田中","渡辺","伊藤","山本","中村","小林","加藤"]
depts = ["営業","開発","総務","経理","人事","企画","製造","品質"]
statuses = ["active","inactive","pending"]
cities = ["東京","大阪","名古屋","福岡","札幌","仙台","広島","横浜"]
base = datetime.date(2020, 1, 1)

with open(out, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.writer(f)
    w.writerow(["id","氏名","部署","都市","年齢","給与","ステータス","入社日","スコア","メモ"])
    for i in range(1, rows + 1):
        w.writerow([
            i,
            random.choice(names) + str(random.randint(1, 999)),
            random.choice(depts),
            random.choice(cities),
            random.randint(22, 65),
            random.randint(250, 1200) * 1000,
            random.choice(statuses),
            (base + datetime.timedelta(days=random.randint(0, 2000))).isoformat(),
            round(random.uniform(0, 100), 2),
            f"備考{random.randint(1, 50)}",
        ])
print(f"生成完了: {out} ({rows:,} 行)")
