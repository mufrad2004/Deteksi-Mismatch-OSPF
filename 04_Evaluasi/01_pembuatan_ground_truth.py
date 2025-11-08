import os
import re
import json
from collections import defaultdict

# === Konfigurasi path ===
BASE_DIR = "04_Evaluasi"
INPUT_FILENAME = "ground_truth.txt"
OUTPUT_FILENAME = "ground_truth.json"

INPUT_PATH = os.path.join(BASE_DIR, INPUT_FILENAME)
OUTPUT_PATH = os.path.join(BASE_DIR, OUTPUT_FILENAME)

# (Opsional) Jika ingin juga menyimpan per-label:
SAVE_BY_LABEL = False
OUTPUT_BY_LABEL = os.path.join(BASE_DIR, "ground_truth_by_label.json")

# === Daftar label yang valid (untuk sanitasi opsional) ===
VALID_TYPES = {
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
}

# --- Util: normalisasi spasi ---
def norm_space(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip())

# --- Ekstrak pasangan router (R\d+) dari suatu teks ---
ROUTER_RE = re.compile(r"R\d+")

# --- Ekstrak semua grup dalam tanda kurung. Jika tak ada, kembalikan satu grup utuh ---
PAREN_GROUP_RE = re.compile(r"\(([^)]*?)\)")

def split_into_groups(payload: str):
    """
    Memecah bagian kanan setelah '->' menjadi grup-grup mismatch.
    - Jika ada tanda kurung, ambil tiap isi kurung sebagai satu grup.
    - Jika tidak ada tanda kurung, seluruh payload dianggap satu grup.
    """
    groups = PAREN_GROUP_RE.findall(payload)
    if groups:
        return [norm_space(g) for g in groups if norm_space(g)]
    else:
        return [norm_space(payload)] if norm_space(payload) else []

def parse_group_to_items(group_text: str):
    """
    Parse satu grup menjadi list item mismatch:
      - Bisa kasus: 'HelloMismatch R1 & R2'
      - Bisa kasus: 'AuthKeyMismatch & AuthMismatch R2 & R3' (banyak tipe share router)
      - Bisa kasus: 'RedistributeMismatch R3' (single router)
    Return: list of dict: {"type": <label>, "routers": [ ... ]}
    """
    # Temukan pertama kali kemunculan router (posisi index) agar pemisah type vs router jelas
    match_router = ROUTER_RE.search(group_text)
    if not match_router:
        # Edge case: tidak ada router sama sekali — anggap invalid, skip
        return []

    split_idx = match_router.start()
    types_part = norm_space(group_text[:split_idx])
    routers_part = norm_space(group_text[split_idx:])

    # Ekstrak semua router
    routers = ROUTER_RE.findall(routers_part)
    routers = [r.strip() for r in routers]
    routers_sorted = sorted(routers, key=lambda x: int(x[1:]))  # sort by number

    # Pecah types (bisa 'A & B' atau hanya 'A')
    # Gunakan '&' sebagai delimiter antar type
    type_tokens = [norm_space(t) for t in group_text[:split_idx].split("&")]
    type_tokens = [t for t in type_tokens if t]

    items = []
    for t in type_tokens:
        # Sanitasi nama tipe: hilangkan sisa kata selain tipe known (opsional)
        # Coba cocokkan langsung jika sudah valid
        if t in VALID_TYPES:
            label = t
        else:
            # Coba cari token tipe yang valid di dalam t
            # contoh: "AuthKeyMismatch " -> exact
            found = None
            for vt in VALID_TYPES:
                if re.search(rf"\b{re.escape(vt)}\b", t):
                    found = vt
                    break
            if not found:
                # Jika tidak ketemu, tetap pakai t apa adanya (biar tidak hilang)
                label = t
            else:
                label = found

        items.append({
            "type": label,
            "routers": routers_sorted
        })

    return items

def parse_line_to_record(line: str):
    """
    Parse satu baris seperti:
      'Topologi 20 -> (RedistributeMismatch R3) & (DeadMismatch R1 & R9)'
    Return:
      topo_key: "Topologi 20"
      status: "Normal" atau "Mismatch"
      mismatch_list: list of dict {type, routers}
    """
    line = line.strip()
    if not line or "->" not in line:
        return None, None, None

    left, right = line.split("->", 1)
    topo_key = norm_space(left)

    payload = norm_space(right)
    if not payload or payload.lower() == "normal":
        return topo_key, "Normal", []

    # Jika bukan Normal, treat as Mismatch
    status = "Mismatch"

    # Potong payload jadi grup
    groups = split_into_groups(payload)

    mismatch_list = []
    for g in groups:
        mismatch_list.extend(parse_group_to_items(g))

    return topo_key, status, mismatch_list

def build_ground_truth(input_path: str):
    data = {}
    with open(input_path, "r", encoding="utf-8") as f:
        for line in f:
            topo_key, status, mismatch_list = parse_line_to_record(line)
            if topo_key is None:
                continue
            data[topo_key] = {
                "status": status,
                "mismatch": mismatch_list
            }
    return data

def build_by_label(ground_truth: dict):
    by_label = defaultdict(lambda: defaultdict(list))
    for topo, rec in ground_truth.items():
        for m in rec.get("mismatch", []):
            label = m.get("type", "")
            routers = m.get("routers", [])
            by_label[label][topo].append(routers)
    # convert defaultdict to dict
    return {lbl: dict(topo_map) for lbl, topo_map in by_label.items()}

def main():
    if not os.path.exists(INPUT_PATH):
        raise FileNotFoundError(f"Tidak menemukan file input: {INPUT_PATH}")

    gt = build_ground_truth(INPUT_PATH)

    # Simpan ground_truth.json
    os.makedirs(BASE_DIR, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(gt, f, ensure_ascii=False, indent=2)

    # (Opsional) simpan per label
    if SAVE_BY_LABEL:
        by_label = build_by_label(gt)
        with open(OUTPUT_BY_LABEL, "w", encoding="utf-8") as f:
            json.dump(by_label, f, ensure_ascii=False, indent=2)

    # (Opsional) ringkasan di console
    total_topo = len(gt)
    total_mismatch_items = sum(len(v.get("mismatch", [])) for v in gt.values())
    print(f"Selesai. Menulis: {OUTPUT_PATH}")
    print(f"Total topologi: {total_topo}")
    print(f"Total item mismatch (type+routers): {total_mismatch_items}")
    if SAVE_BY_LABEL:
        print(f"Juga menulis by-label: {OUTPUT_BY_LABEL}")

if __name__ == "__main__":
    main()
