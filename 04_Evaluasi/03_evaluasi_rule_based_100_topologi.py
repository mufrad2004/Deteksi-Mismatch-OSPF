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
    # sort berdasarkan nomor topologi
    return OrderedDict(sorted(data.items(), key=lambda kv: topo_sort_key(kv[0])))

def safe_div(a, b):
    return a / b if b else 0.0

# =======================
# EVALUASI (BERBASIS BOOLEAN PER LABEL)
# =======================
def evaluate(gt: OrderedDict, rb: OrderedDict):
    """
    gt[topo][label] -> bool
    rb[topo][label] -> bool
    label ∈ VALID_TYPES
    """
    labels = VALID_TYPES[:]  # urutan tetap

    # inisialisasi statistik per label
    stats = {
        lbl: {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
        for lbl in labels
    }

    micro_tp = micro_fp = micro_fn = micro_tn = 0
    subset_acc_list = []
    total_topo = 0

    # loop per topologi
    for topo, gt_labels in gt.items():
        rb_labels = rb.get(topo, {})

        # set label yang bernilai True (untuk subset accuracy & Jaccard)
        truth_pos = {lbl for lbl in labels if gt_labels.get(lbl, False)}
        pred_pos  = {lbl for lbl in labels if rb_labels.get(lbl, False)}

        # Jaccard components (hanya positif)
        tp_set = truth_pos & pred_pos
        fp_set = pred_pos - truth_pos
        fn_set = truth_pos - pred_pos

        micro_tp += len(tp_set)
        micro_fp += len(fp_set)
        micro_fn += len(fn_set)

        # hitung TP/FP/FN/TN per label (berbasis boolean)
        for lbl in labels:
            y_true = bool(gt_labels.get(lbl, False))
            y_pred = bool(rb_labels.get(lbl, False))

            if y_true and y_pred:
                stats[lbl]["tp"] += 1
                # micro_tp sudah dihitung dari tp_set
            elif (not y_true) and (not y_pred):
                stats[lbl]["tn"] += 1
                micro_tn += 1
            elif y_true and (not y_pred):
                stats[lbl]["fn"] += 1
                # micro_fn sudah dihitung dari fn_set
            elif (not y_true) and y_pred:
                stats[lbl]["fp"] += 1
                # micro_fp sudah dihitung dari fp_set

        # subset accuracy (exact match, semua label sama)
        subset_acc_list.append(1.0 if truth_pos == pred_pos else 0.0)
        total_topo += 1

    # hitung metrik per label
    per_label = OrderedDict()
    for lbl in labels:
        tp = stats[lbl]["tp"]
        fp = stats[lbl]["fp"]
        fn = stats[lbl]["fn"]
        tn = stats[lbl]["tn"]

        p = safe_div(tp, tp + fp)
        r = safe_div(tp, tp + fn)
        f1 = safe_div(2 * p * r, (p + r))

        support_pos = tp + fn      # jumlah kasus positif (ground truth = True)
        support_neg = tn + fp      # jumlah kasus negatif
        support_all = support_pos + support_neg

        acc_label = safe_div(tp + tn, support_all)

        per_label[lbl] = {
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "tn": tn,
            "precision": round(p, 4),
            "recall": round(r, 4),
            "f1": round(f1, 4),
            "accuracy": round(acc_label, 4),
            "support_pos": support_pos,
            "support_neg": support_neg,
            "support_all": support_all,
        }

    # macro-average (rata-rata per label)
    if per_label:
        macro_p = sum(v["precision"] for v in per_label.values()) / len(per_label)
        macro_r = sum(v["recall"]    for v in per_label.values()) / len(per_label)
        macro_f1= sum(v["f1"]        for v in per_label.values()) / len(per_label)
        macro_acc = sum(v["accuracy"] for v in per_label.values()) / len(per_label)
    else:
        macro_p = macro_r = macro_f1 = macro_acc = 0.0

    # micro (berbasis semua label & topologi)
    micro_p = safe_div(micro_tp, micro_tp + micro_fp)
    micro_r = safe_div(micro_tp, micro_tp + micro_fn)
    micro_f1= safe_div(2 * micro_p * micro_r, (micro_p + micro_r))

    # micro accuracy Jaccard (pakai TP/FP/FN saja)
    micro_jaccard = safe_div(micro_tp, (micro_tp + micro_fp + micro_fn))

    # micro accuracy klasik (pakai TN juga)
    total_micro = micro_tp + micro_fp + micro_fn + micro_tn
    micro_acc_std = safe_div(micro_tp + micro_tn, total_micro)

    # Hamming Accuracy
    total_labels = len(VALID_TYPES) * total_topo
    hamming_accuracy = safe_div(micro_tp + micro_tn, total_labels)

    subset_acc_mean = sum(subset_acc_list) / len(subset_acc_list) if subset_acc_list else 1.0

    summary = {
        "macro": {
            "precision": round(macro_p, 4),
            "recall": round(macro_r, 4),
            "f1": round(macro_f1, 4),
            "accuracy": round(macro_acc, 4),
        },
        "micro": {
            "precision": round(micro_p, 4),
            "recall": round(micro_r, 4),
            "f1": round(micro_f1, 4),
            "accuracy_jaccard": round(micro_jaccard, 4),
            "accuracy_standard": round(micro_acc_std, 4),
            "hamming_accuracy": round(hamming_accuracy, 4),
        },
        "global_counts": {
            "tp_total": micro_tp,
            "fp_total": micro_fp,
            "fn_total": micro_fn,
            "tn_total": micro_tn,
        },
        "subset_accuracy": {
            "mean_exact_match": round(subset_acc_mean, 4),
            "num_topologies": total_topo,
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
        f.write("Label                  | TP  FP  FN  TN  | Prec   Rec    F1     Acc    | Pos  Neg  All\n")
        f.write("-" * 96 + "\n")
        for lbl, v in per_label.items():
            f.write(
                f"{lbl:22} | "
                f"{v['tp']:3} {v['fp']:3} {v['fn']:3} {v['tn']:3} | "
                f"{v['precision']:.4f} {v['recall']:.4f} {v['f1']:.4f} {v['accuracy']:.4f} | "
                f"{v['support_pos']:4} {v['support_neg']:4} {v['support_all']:4}\n"
            )

        f.write("\n== Rata-rata (Macro) ==\n")
        f.write(f"Macro Precision       : {summary['macro']['precision']}\n")
        f.write(f"Macro Recall          : {summary['macro']['recall']}\n")
        f.write(f"Macro F1-Score        : {summary['macro']['f1']}\n")
        f.write(f"Macro Accuracy        : {summary['macro']['accuracy']}\n")

        f.write("\n== Metrik Mikro (Global) ==\n")
        f.write(f"Micro Precision       : {summary['micro']['precision']}\n")
        f.write(f"Micro Recall          : {summary['micro']['recall']}\n")
        f.write(f"Micro F1-Score        : {summary['micro']['f1']}\n")
        f.write(f"Micro Accuracy Jaccard: {summary['micro']['accuracy_jaccard']}\n")
        f.write(f"Micro Accuracy Std    : {summary['micro']['accuracy_standard']}\n")
        f.write(f"Hamming Accuracy      : {summary['micro']['hamming_accuracy']}\n")

        f.write("\n== TN & Subset Accuracy ==\n")
        f.write(
            f"Total TP/FP/FN/TN     : "
            f"{summary['global_counts']['tp_total']}/"
            f"{summary['global_counts']['fp_total']}/"
            f"{summary['global_counts']['fn_total']}/"
            f"{summary['global_counts']['tn_total']}\n"
        )
        f.write(
            f"Subset Accuracy (Exact Match, mean) : "
            f"{summary['subset_accuracy']['mean_exact_match']}\n"
        )
        f.write(
            f"Total Topology Evaluated           : "
            f"{summary['subset_accuracy']['num_topologies']}\n"
        )
    print(f"Hasil disimpan ke: {out_path}")

# =======================
# MAIN
# =======================
def main():
    gt_all = load_json(GT_PATH)
    rb_all = load_json(RB_PATH)

    per_label, summary = evaluate(gt_all, rb_all)
    save_txt(per_label, summary, OUT_TXT)

if __name__ == "__main__":
    main()
