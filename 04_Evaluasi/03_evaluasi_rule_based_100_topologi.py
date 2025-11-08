import os
import json
import re
from collections import OrderedDict

# =======================
# KONFIGURASI PATH
# =======================
EVAL_DIR = "04_Evaluasi"
GT_PATH = os.path.join(EVAL_DIR, "ground_truth.json")
RB_PATH = os.path.join(EVAL_DIR, "rule_based.json")
OUT_TXT = os.path.join(EVAL_DIR, "hasil_evaluasi_rule_based_100_topologi.txt")

VALID_TYPES = [
    "HelloMismatch", "DeadMismatch", "NetworkTypeMismatch", "AreaMismatch",
    "AuthMismatch", "AuthKeyMismatch", "MTUMismatch", "PassiveMismatch",
    "RedistributeMismatch", "RouterIDMismatch",
]

# =======================
# UTIL
# =======================
def topo_sort_key(topo_key: str) -> int:
    m = re.search(r"(\d+)$", topo_key)
    return int(m.group(1)) if m else 10**9

def load_json(path: str) -> OrderedDict:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return OrderedDict(sorted(data.items(), key=lambda kv: topo_sort_key(kv[0])))

def tuple_key(item: dict):
    t = item.get("type", "")
    routers = item.get("routers", [])
    routers_sorted = tuple(sorted(routers, key=lambda x: int(x[1:]) if x[1:].isdigit() else x))
    return (t, routers_sorted)

def set_of_instances(mismatch_list):
    return set(tuple_key(it) for it in mismatch_list)

def safe_div(a, b):
    return a / b if b else 0.0

# =======================
# EVALUASI
# =======================
def evaluate(gt, rb):
    all_labels = set(VALID_TYPES)
    for data in (gt, rb):
        for rec in data.values():
            for it in rec.get("mismatch", []):
                all_labels.add(it.get("type", ""))
    all_labels = sorted(all_labels)

    stats = {lbl: {"tp": 0, "fp": 0, "fn": 0} for lbl in all_labels}
    micro_tp = micro_fp = micro_fn = 0
    subset_acc_list = []
    total_topo = 0

    for topo in gt.keys():
        truth_set = set_of_instances(gt[topo].get("mismatch", []))
        pred_set  = set_of_instances(rb.get(topo, {}).get("mismatch", []))

        tp = truth_set & pred_set
        fp = pred_set - truth_set
        fn = truth_set - pred_set

        micro_tp += len(tp)
        micro_fp += len(fp)
        micro_fn += len(fn)

        for (lbl, _) in tp: stats[lbl]["tp"] += 1
        for (lbl, _) in fp: stats[lbl]["fp"] += 1
        for (lbl, _) in fn: stats[lbl]["fn"] += 1

        if truth_set or pred_set:
            subset_acc_list.append(1.0 if truth_set == pred_set else 0.0)
            total_topo += 1

    per_label = OrderedDict()
    for lbl in all_labels:
        tp, fp, fn = stats[lbl]["tp"], stats[lbl]["fp"], stats[lbl]["fn"]
        p = safe_div(tp, tp + fp); r = safe_div(tp, tp + fn)
        f1 = safe_div(2 * p * r, (p + r))
        support = tp + fn
        per_label[lbl] = {
            "tp": tp, "fp": fp, "fn": fn,
            "precision": round(p, 3), "recall": round(r, 3),
            "f1": round(f1, 3), "support": support,
        }

    macro_p = sum(v["precision"] for v in per_label.values()) / len(per_label) if per_label else 0.0
    macro_r = sum(v["recall"]    for v in per_label.values()) / len(per_label) if per_label else 0.0
    macro_f1= sum(v["f1"]        for v in per_label.values()) / len(per_label) if per_label else 0.0

    micro_p = safe_div(micro_tp, micro_tp + micro_fp)
    micro_r = safe_div(micro_tp, micro_tp + micro_fn)
    micro_f1= safe_div(2 * micro_p * micro_r, (micro_p + micro_r))

    micro_acc = safe_div(micro_tp, (micro_tp + micro_fp + micro_fn))
    subset_acc_mean = sum(subset_acc_list) / len(subset_acc_list) if subset_acc_list else 1.0

    summary = {
        "macro": {"p": round(macro_p, 3), "r": round(macro_r, 3), "f1": round(macro_f1, 3)},
        "micro": {"p": round(micro_p, 3), "r": round(micro_r, 3), "f1": round(micro_f1, 3)},
        "accuracy": {
            "micro_jaccard": round(micro_acc, 4),
            "subset_exact_mean": round(subset_acc_mean, 4),
            "num_topologies": total_topo,
            "tp_total": micro_tp, "fp_total": micro_fp, "fn_total": micro_fn,
        },
    }
    return per_label, summary

# =======================
# SIMPAN TXT
# =======================
def save_txt(per_label, summary, out_path):
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("=== HASIL EVALUASI RULE-BASED (100 TOPOLOGI) ===\n")

        f.write("\n== Per Label ==\n")
        for lbl, v in per_label.items():
            f.write(
                f"{lbl:22} | TP: {v['tp']:3} | FP: {v['fp']:3} | FN: {v['fn']:3} "
                f"| Prec: {v['precision']:.3f} | Rec: {v['recall']:.3f} | F1: {v['f1']:.3f} "
                f"| Support: {v['support']}\n"
            )

        f.write("\n== Rata-rata ==\n")
        f.write(f"Macro Precision : {summary['macro']['p']}\n")
        f.write(f"Macro Recall    : {summary['macro']['r']}\n")
        f.write(f"Macro F1-Score  : {summary['macro']['f1']}\n")
        f.write(f"Micro Precision : {summary['micro']['p']}\n")
        f.write(f"Micro Recall    : {summary['micro']['r']}\n")
        f.write(f"Micro F1-Score  : {summary['micro']['f1']}\n")

        f.write("\n== Akurasi ==\n")
        f.write(f"Micro Accuracy (Jaccard)    : {summary['accuracy']['micro_jaccard']}\n")
        f.write(f"Subset Accuracy (Exact, μ)  : {summary['accuracy']['subset_exact_mean']}\n")
        f.write(f"Total Topology Evaluated    : {summary['accuracy']['num_topologies']}\n")
        f.write(f"Total TP/FP/FN              : {summary['accuracy']['tp_total']}/"
                f"{summary['accuracy']['fp_total']}/{summary['accuracy']['fn_total']}\n")
    print(f"Hasil disimpan ke: {out_path}")

# =======================
# MAIN
# =======================
def main():
    gt = load_json(GT_PATH)
    rb = load_json(RB_PATH)

    per_label, summary = evaluate(gt, rb)
    save_txt(per_label, summary, OUT_TXT)

if __name__ == "__main__":
    main()
