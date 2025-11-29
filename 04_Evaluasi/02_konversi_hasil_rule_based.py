import os
import re
import json
from collections import OrderedDict

# =======================
# KONFIGURASI PATH
# =======================
RULEBASED_DIR = os.path.join("03_Output", "Hasil_Rule_Based")
EVAL_DIR = "04_Evaluasi"
OUTPUT_JSON = os.path.join(EVAL_DIR, "rule_based.json")

# =======================
# URUTAN LABEL (SAMA DENGAN ground_truth.json)
# =======================
LABELS_ORDER = [
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

# set untuk validasi / pengecekan
VALID_TYPES = set(LABELS_ORDER)

# Pola untuk normalisasi nama label dari file teks rule-based
LABEL_PATTERNS = [
    (re.compile(r"hello", re.I), "HelloMismatch"),
    (re.compile(r"dead", re.I), "DeadMismatch"),
    (re.compile(r"network\s*type", re.I), "NetworkTypeMismatch"),
    (re.compile(r"\barea\b", re.I), "AreaMismatch"),
    (re.compile(r"auth(entication)?(?!\s*key)", re.I), "AuthMismatch"),
    (re.compile(r"auth[\s_-]*key|key[\s_-]*auth|authkey", re.I), "AuthKeyMismatch"),
    (re.compile(r"\bmtu\b", re.I), "MTUMismatch"),
    (re.compile(r"passive", re.I), "PassiveMismatch"),
    (re.compile(r"redistribute", re.I), "RedistributeMismatch"),
    (re.compile(r"router\s*id|duplicate", re.I), "RouterIDMismatch"),
]


def normalize_label(raw: str) -> str:
    """
    Normalisasi teks label dari file rule-based ke salah satu nama di VALID_TYPES.
    Kalau tidak cocok, dikembalikan apa adanya (tapi idealnya semua harus match).
    """
    s = raw.strip()
    s = re.sub(r"[_\-]+", " ", s)          # ubah _ / - jadi spasi
    s = re.sub(r"\s*:\s*$", "", s)         # buang ":" di ujung jika ada
    s = re.sub(r"\s+", " ", s).strip()     # rapikan spasi

    # Cek pakai pattern
    for pat, target in LABEL_PATTERNS:
        if pat.search(s):
            return target

    # fallback: coba bentuk CamelCase + Mismatch
    s2 = s.title().replace(" ", "")
    if s2.endswith("Mismatch") and s2 in VALID_TYPES:
        return s2

    # fallback terakhir: kembalikan apa adanya
    return s


# =======================
# REGEX STRUKTUR FILE
# =======================
HDR_PAIR = re.compile(
    r"^=+\s*Mismatch\s+antara\s+(R\d+)\s+dan\s+(R\d+)\s*=+\s*$", re.I
)
HDR_SINGLE = re.compile(
    r"^=+\s*Mismatch\s+pada\s+(R\d+)\s*=+\s*$", re.I
)
LABEL_LINE = re.compile(
    r"^\s*-\s*([A-Za-z _-]+?)\s*:\s*$", re.I
)


# =======================
# PARSER 1 FILE
# =======================
def parse_rulebased_file(txt: str):
    """
    Parse isi satu file hasil rule-based, dan kembalikan list item:
    [
      {"type": "HelloMismatch", "routers": ["R1", "R2"]},
      ...
    ]
    Walaupun nanti kita tidak pakai "routers" lagi di JSON final,
    struktur ini dipertahankan supaya gampang kalau butuh debugging.
    """
    items = []
    current_routers = None

    for line in txt.splitlines():
        line = line.rstrip("\n")

        # header pasangan router
        m_pair = HDR_PAIR.match(line)
        if m_pair:
            r1, r2 = m_pair.group(1), m_pair.group(2)
            current_routers = sorted([r1, r2], key=lambda x: int(x[1:]))
            continue

        # header single router
        m_single = HDR_SINGLE.match(line)
        if m_single:
            current_routers = [m_single.group(1)]
            continue

        # baris label mismatch
        m_lbl = LABEL_LINE.match(line)
        if m_lbl and current_routers:
            raw_label = m_lbl.group(1)
            label = normalize_label(raw_label)
            items.append({"type": label, "routers": current_routers[:]})
            continue

    return items


# =======================
# TOPO KEY & SORT HELPER
# =======================
def topo_key_from_filename(fname: str) -> str | None:
    """
    Ekstrak nomor topologi dari nama file (misal: 'Topologi_12.txt' -> 'Topologi 12')
    """
    nums = re.findall(r"(\d+)", fname)
    if not nums:
        return None
    topo_id = int(nums[-1])
    return f"Topologi {topo_id}"


def topo_sort_key(topo_key: str) -> int:
    m = re.search(r"(\d+)$", topo_key)
    return int(m.group(1)) if m else 10**9


# =======================
# PARSER SEMUA FILE & SIMPAN JSON (BOOLEAN PER LABEL)
# =======================
def build_rulebased_boolean_dict() -> OrderedDict:
    """
    Bangun dictionary:
      {
        "Topologi 1": {
          "HelloMismatch": false,
          "DeadMismatch": false,
          ...
        },
        "Topologi 2": {
          "HelloMismatch": true,
          ...
        },
        ...
      }

    Struktur dan urutan label disamakan dengan ground_truth.json (boolean per label).
    """
    data: dict[str, dict[str, bool]] = {}

    if not os.path.isdir(RULEBASED_DIR):
        raise FileNotFoundError(f"Folder tidak ditemukan: {RULEBASED_DIR}")

    for fname in sorted(os.listdir(RULEBASED_DIR)):
        if not fname.lower().endswith(".txt"):
            continue

        topo_key = topo_key_from_filename(fname)
        if not topo_key:
            continue

        path = os.path.join(RULEBASED_DIR, fname)
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            txt = f.read()

        items = parse_rulebased_file(txt)

        # Inisialisasi semua label = False, dengan urutan LABELS_ORDER
        label_flags = {label: False for label in LABELS_ORDER}

        # Set True untuk setiap type mismatch yang ditemukan
        for it in items:
            t = it.get("type")
            if t in VALID_TYPES:
                label_flags[t] = True

        data[topo_key] = label_flags

    # urutkan Topologi secara numerik
    ordered = OrderedDict(sorted(data.items(), key=lambda kv: topo_sort_key(kv[0])))
    return ordered


def main():
    os.makedirs(EVAL_DIR, exist_ok=True)
    data = build_rulebased_boolean_dict()

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    total_topo = len(data)
    # jumlah topologi yang terdeteksi MISMATCH (ada minimal satu label True)
    mismatch_topo = sum(
        1 for v in data.values()
        if any(v[label] for label in LABELS_ORDER)
    )
    normal_topo = total_topo - mismatch_topo

    print(f"Selesai menulis: {OUTPUT_JSON}")
    print(f"Total topologi : {total_topo}")
    print(f"  Normal       : {normal_topo}")
    print(f"  Mismatch     : {mismatch_topo}")


if __name__ == "__main__":
    main()
