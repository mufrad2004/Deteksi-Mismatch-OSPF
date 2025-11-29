import os
import json
import re

# ============================
# KONFIGURASI PATH
# ============================

# Folder tempat script ini berada (biasanya = 04_Evaluasi)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

INPUT_FILENAME = "ground_truth.txt"       # file input teks
OUTPUT_FILENAME = "ground_truth.json"     # file output JSON (format boolean per label)

INPUT_PATH = os.path.join(BASE_DIR, INPUT_FILENAME)
OUTPUT_PATH = os.path.join(BASE_DIR, OUTPUT_FILENAME)

# ============================
# DAFTAR LABEL MISKONFIGURASI
# ============================

LABELS = [
    "HelloMismatch",
    "DeadMismatch",
    "NetworkTypeMismatch",
    "AreaMismatch",
    "AuthMismatch",
    "AuthKeyMismatch",
    "MTUMismatch",
    "PassiveMismatch",
    "RedistributeMismatch",
    "RouterIDMismatch",
]

# Regex untuk mendeteksi label di bagian kanan baris (setelah "->")
LABEL_PATTERN = re.compile(r"\b(" + "|".join(LABELS) + r")\b")


# ============================
# FUNGSI UTILITAS
# ============================

def topo_sort_key(topo_name: str) -> int:
    """
    Mengambil angka di akhir string "Topologi X" untuk sorting.
    Contoh:
      "Topologi 1"   -> 1
      "Topologi 10"  -> 10
    """
    m = re.search(r"(\d+)$", topo_name)
    if m:
        return int(m.group(1))
    return 10**9  # jika tidak ada angka di akhir, taruh di belakang


# ============================
# FUNGSI UTAMA KONVERSI
# ============================

def build_ground_truth_boolean(input_path: str) -> dict:
    """
    Membaca ground_truth.txt dan mengubahnya menjadi dictionary:
      {
        "Topologi 1": {
          "HelloMismatch": false,
          "DeadMismatch": false,
          ...
        },
        "Topologi 2": {
          "HelloMismatch": true,
          "DeadMismatch": false,
          ...
        },
        ...
      }
    """
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Tidak menemukan file input: {input_path}")

    result = {}

    with open(input_path, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line:
                continue
            if "->" not in line:
                continue

            # Pisahkan "Topologi X" dan isi kanan setelah "->"
            left, right = line.split("->", 1)
            topo_key = left.strip()   # contoh: "Topologi 1"
            payload = right.strip()   # contoh: "Normal" atau "HelloMismatch R1 & R2"

            # Inisialisasi semua label = False
            result[topo_key] = {label: False for label in LABELS}

            # Jika Normal (tidak ada mismatch), langsung lanjut (semua False)
            if payload.lower() == "normal":
                continue

            # Cari semua label yang muncul di payload
            found_labels = LABEL_PATTERN.findall(payload)

            # Set label yang ditemukan menjadi True
            for lbl in found_labels:
                if lbl in result[topo_key]:
                    result[topo_key][lbl] = True

    # Sort topologi berdasarkan nomor (Topologi 1, 2, ..., 100)
    sorted_items = sorted(result.items(), key=lambda kv: topo_sort_key(kv[0]))
    ordered_result = {k: v for k, v in sorted_items}

    return ordered_result


def main():
    gt_boolean = build_ground_truth_boolean(INPUT_PATH)

    # Pastikan folder BASE_DIR ada (harusnya sudah ada)
    os.makedirs(BASE_DIR, exist_ok=True)

    # Simpan ke JSON dengan format baru (boolean per label)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(gt_boolean, f, ensure_ascii=False, indent=2)

    print(f"Selesai membuat ground truth boolean:")
    print(f"  Input : {INPUT_PATH}")
    print(f"  Output: {OUTPUT_PATH}")
    print(f"  Total topologi: {len(gt_boolean)}")


if __name__ == "__main__":
    main()
