"""Solution Verification and Feasibility Benchmark for all 20 queries in Public Data 1."""

import sys
import re
import json
import csv
from pathlib import Path
import pandas as pd
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

sys.stdout.reconfigure(encoding="utf-8")

from src.normalizer import load_normalized_workbook
from src.sanitizer import sanitize_answer

def run_verification_p1():
    xlsx_dir = Path("data/data_public_1/xlsx_files")
    queries = json.load(open("data/data_public_1/queries.json", encoding="utf-8"))
    
    gt_map = {}
    with open("data/data_public_1/sample_submission.csv", "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            gt_map[row["id"]] = str(row["answer"]).strip()

    wb_cache = {}
    for f in xlsx_dir.glob("*.xlsx"):
        wb_cache[f.name] = load_normalized_workbook(f)

    def to_num(val):
        if val is None or pd.isna(val): return np.nan
        s = str(val).strip()
        s = re.sub(r'[\$,%€£¥₫]', '', s).replace(',', '').strip()
        if s.startswith('(') and s.endswith(')'):
            s = '-' + s[1:-1].strip()
        try:
            return float(s)
        except:
            return np.nan

    def get_sheet(wb):
        return list(wb.values())[0]

    solutions = {}

    # Q1: p4_t01.xlsx
    df1 = get_sheet(wb_cache["p4_t01.xlsx"]).copy()
    df1["dob"] = pd.to_datetime(df1["Date of | Birth"])
    df1["doa"] = pd.to_datetime(df1["Date of | Admission"])
    df1["age_days"] = (df1["doa"] - df1["dob"]).dt.days
    second_youngest = df1.sort_values(by="age_days").iloc[1]
    solutions["p4_q001"] = str(second_youngest["Name | Last"]).strip()

    # Q2: p4_t01.xlsx
    second_oldest = df1.sort_values(by="age_days", ascending=False).iloc[1]
    solutions["p4_q002"] = str(int(second_oldest["Score"]))

    # Q3: p4_t01.xlsx
    ten_youngest = df1.sort_values(by="age_days").iloc[:10]
    solutions["p4_q003"] = str(int(ten_youngest["Score"].max()))

    # Q4: p4_t02.xlsx
    df2 = get_sheet(wb_cache["p4_t02.xlsx"])
    row_exp = df2[df2.iloc[:, 0].str.contains("Exports", case=False, na=False)].iloc[0]
    col_24 = [c for c in df2.columns if "Fiscal year-to-date" in c and "2024" in c][0]
    col_23 = [c for c in df2.columns if "Fiscal year-to-date" in c and "2023" in c][0]
    solutions["p4_q004"] = "Yes" if to_num(row_exp[col_24]) > to_num(row_exp[col_23]) else "No"

    # Q5: p4_t03.xlsx
    df3 = get_sheet(wb_cache["p4_t03.xlsx"]).copy()
    col_chg = [c for c in df3.columns if "Unadjusted percent change" in c and "Sep. 2024" in c][0]
    df3["abs_chg"] = df3[col_chg].apply(to_num).abs()
    top_cat = df3.sort_values(by="abs_chg", ascending=False).iloc[0]
    solutions["p4_q005"] = str(top_cat["Expenditure category"]).strip()

    # Q6: p4_t04.xlsx
    df4 = get_sheet(wb_cache["p4_t04.xlsx"])
    col_ed = "2023 | Some college or associate degree | Some college, no degree"
    r_pop = df4[df4.iloc[:, 0] == "Women | Civilian noninstitutional population"][col_ed].values[0]
    r_civ = df4[df4.iloc[:, 0] == "Women | Civilian labor force"][col_ed].values[0]
    solutions["p4_q006"] = str(int(abs(to_num(r_pop) - to_num(r_civ))))

    # Q7: p4_t04.xlsx
    r_unemp = df4[df4.iloc[:, 0] == "Women | Unemployment rate"].iloc[0]
    ed_vals = [to_num(v) for k, v in r_unemp.items() if k != df4.columns[0]]
    solutions["p4_q007"] = f"{np.nanmean(ed_vals):.2f}"

    # Q8: p4_t05.xlsx
    df5 = get_sheet(wb_cache["p4_t05.xlsx"])
    r_20_24 = df5[df5.iloc[:, 0] == "TOTAL | 20 to 24 years"].iloc[0, 1:].apply(to_num).sum()
    r_16_19 = df5[df5.iloc[:, 0] == "TOTAL | 16 to 19 years"].iloc[0, 1:].apply(to_num).sum()
    solutions["p4_q008"] = str(int(abs(r_20_24 - r_16_19)))

    # Q9: p4_t05.xlsx
    r_20_24_row = df5[df5.iloc[:, 0] == "TOTAL | 20 to 24 years"].iloc[0]
    solutions["p4_q009"] = str(int(to_num(r_20_24_row["2023 | Construction"]) + to_num(r_20_24_row["2023 | Manufacturing"])))

    # Q10: p4_t05.xlsx
    r_16_19_row = df5[df5.iloc[:, 0] == "TOTAL | 16 to 19 years"].iloc[0, 1:].apply(to_num)
    top_col = r_16_19_row.sort_values(ascending=False).index[0]
    solutions["p4_q010"] = top_col.split("|")[-1].strip()

    # Q11: p4_t05.xlsx
    r_20p = df5[df5.iloc[:, 0] == "TOTAL | 20 years and over"].iloc[0]
    fin = to_num(r_20p["2023 | Financial activities"])
    trans = to_num(r_20p["2023 | Transportation and utilities"])
    solutions["p4_q011"] = "Yes" if fin > trans else "No"

    # Q12: p4_t06.xlsx
    df6 = get_sheet(wb_cache["p4_t06.xlsx"])
    r_tot6 = df6[df6.iloc[:, 0] == "Total, 16 years and over"].iloc[0]
    solutions["p4_q012"] = str(int(to_num(r_tot6["2023 | Agriculture and related industries | Unpaid family workers"])))

    # Q13: p4_t07.xlsx
    df7 = get_sheet(wb_cache["p4_t07.xlsx"])
    col_moving = [c for c in df7.columns if "Transportation and material moving occupations" in c][0]
    sec_vals = {
        "Agriculture": to_num(df7[df7.iloc[:, 0].str.contains("Agriculture", case=False, na=False)].iloc[0][col_moving]),
        "Manufacturing": to_num(df7[df7.iloc[:, 0].str.contains("Manufacturing", case=False, na=False)].iloc[0][col_moving]),
        "Construction": to_num(df7[df7.iloc[:, 0].str.contains("Construction", case=False, na=False)].iloc[0][col_moving])
    }
    sorted_secs = sorted(sec_vals.keys(), key=lambda k: sec_vals[k], reverse=True)
    solutions["p4_q013"] = ", ".join(sorted_secs)

    # Q14: p4_t07.xlsx
    r_mfg7 = df7[df7.iloc[:, 0] == "TOTAL | Manufacturing"].iloc[0]
    prot = to_num(r_mfg7["2023 | Service occupations | Protective service occupations"])
    ex_prot = to_num(r_mfg7["2023 | Service occupations | Service occupations, except protective"])
    solutions["p4_q014"] = str(int(prot + ex_prot))

    # Q15: p4_t08.xlsx
    df8 = get_sheet(wb_cache["p4_t08.xlsx"])
    r_5_14 = df8[df8.iloc[:, 0] == "5 to 14 hours"].iloc[0]
    solutions["p4_q015"] = str(int(to_num(r_5_14["2023 | Persons at work | Agriculture and related industries"])))

    # Q16: p4_t08.xlsx
    col_agri_pct = "2023 | Percent distribution | Agriculture and related industries"
    df8_sub = df8[~df8.iloc[:, 0].str.contains("Total|1 to 34 hours", case=False, na=False)].copy()
    df8_sub["agri_pct"] = df8_sub[col_agri_pct].apply(to_num)
    top_hour = df8_sub.sort_values(by="agri_pct", ascending=False).iloc[0]
    solutions["p4_q016"] = str(top_hour.iloc[0]).strip()

    # Q17: p4_t09.xlsx
    df9 = get_sheet(wb_cache["p4_t09.xlsx"])
    r_const9 = to_num(df9[df9.iloc[:, 0] == "Construction"]["2023 | Total at work"].values[0])
    r_mfg9 = to_num(df9[df9.iloc[:, 0] == "Manufacturing"]["2023 | Total at work"].values[0])
    solutions["p4_q017"] = str(int(abs(r_mfg9 - r_const9)))

    # Q18: p4_t10.xlsx
    df10 = get_sheet(wb_cache["p4_t10.xlsx"])
    r_tot10 = df10[df10.iloc[:, 0] == "AGE AND SEX | Total, 16 years and over"].iloc[0]
    h_1_34 = str(int(to_num(r_tot10["2023 | Worked 1 to 34 hours | Total"])))
    h_35p = str(int(to_num(r_tot10["2023 | Worked 35 hours or more"])))
    solutions["p4_q018"] = f"{h_1_34}, {h_35p}"

    # Q19: p4_t10.xlsx
    col_avg = "2023 | Average hours | Total at work"
    men_avg = to_num(df10[df10.iloc[:, 0].str.contains("Men", case=False, na=False) & df10.iloc[:, 0].str.contains("Widowed", case=False, na=False)][col_avg].values[0])
    women_avg = to_num(df10[df10.iloc[:, 0].str.contains("Women", case=False, na=False) & df10.iloc[:, 0].str.contains("Widowed", case=False, na=False)][col_avg].values[0])
    solutions["p4_q019"] = f"{men_avg:.2f}, {women_avg:.2f}"

    # Q20: p4_t10.xlsx
    tot_work = to_num(r_tot10["2023 | Total at work"])
    solutions["p4_q020"] = str(int(tot_work))

    match_count = 0
    print("=" * 75)
    print("EMPIRICAL VERIFICATION RESULTS ON PUBLIC DATA 1:")
    print("=" * 75)
    for q in queries:
        qid = q["id"]
        q_text = q["query"]
        raw_sol = solutions.get(qid, "")
        sol = sanitize_answer(raw_sol, q_text)
        gt = gt_map.get(qid, "")
        matched = (sol == gt)
        if matched: match_count += 1
        status = "✅ PASS" if matched else "❌ FAIL"
        print(f"[{qid}] Pred: '{sol:<35}' | GT: '{gt:<35}' | {status}")

    acc = match_count / len(queries) * 100.0
    print("=" * 75)
    print(f"VERIFICATION SCORE: {match_count}/{len(queries)} ({acc:.1f}%)")
    print("=" * 75)
    return match_count

if __name__ == "__main__":
    run_verification_p1()
