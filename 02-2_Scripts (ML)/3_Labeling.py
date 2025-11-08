import os
import pandas as pd

# === Path utama === #
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
input_dir = os.path.join(ROOT_DIR, "03_Output", "Data_ML")
output_dir = os.path.join(ROOT_DIR, "03_Output", "Data_ML_Labeled")

os.makedirs(output_dir, exist_ok=True)


# === Fungsi bantu === #
def normalize_case(value):
    """Ubah nilai menjadi lowercase string untuk perbandingan aman."""
    return str(value).strip().lower()


def check_redistribute(row):
    """
    Cek RedistributeMismatch sesuai logika terbaru:
    - Hanya router dengan routing 'ospf,eigrp' yang dicek.
    - Jika redistributenya False → mismatch (True)
    - Jika redistributenya True → match (False)
    """
    routing_a = str(row.get("routing_a", "")).lower()
    routing_b = str(row.get("routing_b", "")).lower()
    redist_a = bool(row.get("redistribute_a", False))
    redist_b = bool(row.get("redistribute_b", False))

    if "ospf,eigrp" in routing_a and not redist_a:
        return True
    if "ospf,eigrp" in routing_b and not redist_b:
        return True
    return False


# === Fungsi utama === #
for fname in sorted(os.listdir(input_dir)):
    if not fname.endswith(".csv"):
        continue

    fpath = os.path.join(input_dir, fname)
    df = pd.read_csv(fpath)
    print(f"[✓] Membaca {fname} ({len(df)} baris)")

    # === RouterIDMismatch === #
    # Ambil pasangan unik router dan router_id
    router_ids = df[["router_a", "router_id_a"]].drop_duplicates()
    duplicate_ids = router_ids["router_id_a"][router_ids["router_id_a"].duplicated(keep=False)].unique().tolist()

    df["RouterIDMismatch"] = df.apply(
        lambda x: (x["router_id_a"] in duplicate_ids) or (x["router_id_b"] in duplicate_ids),
        axis=1
    )

    # === Labeling sesuai logika baru === #
    df["HelloMismatch"] = df["hello_a"] != df["hello_b"]
    df["DeadMismatch"] = df["dead_a"] != df["dead_b"]
    df["NetworkTypeMismatch"] = df["network_type_a"].apply(normalize_case) != df["network_type_b"].apply(normalize_case)
    df["AreaMismatch"] = df["area_a"] != df["area_b"]
    df["AuthMismatch"] = df["ospf_auth_a"].apply(normalize_case) != df["ospf_auth_b"].apply(normalize_case)
    df["AuthKeyMismatch"] = df["auth_key_a"].apply(normalize_case) != df["auth_key_b"].apply(normalize_case)
    df["MTUMismatch"] = df["MTU_a"] != df["MTU_b"]
    df["PassiveMismatch"] = df.apply(lambda x: bool(x["passive_a"]) or bool(x["passive_b"]), axis=1)
    df["RedistributeMismatch"] = df.apply(check_redistribute, axis=1)

    # === Urutan kolom label === #
    label_cols = [
        "HelloMismatch", "DeadMismatch", "NetworkTypeMismatch",
        "RouterIDMismatch", "AuthMismatch", "AuthKeyMismatch",
        "PassiveMismatch", "RedistributeMismatch", "AreaMismatch", "MTUMismatch"
    ]

    # === Simpan hasil === #
    out_csv = os.path.join(output_dir, fname.replace("clean_", "labeled_").replace("dataset_", "labeled_"))
    df.to_csv(out_csv, index=False)
    print(f"[✓] File {fname} selesai diberi label ({len(df)} baris) → {out_csv}\n")

print(f"[✔] Semua dataset selesai diberi label. Hasil tersimpan di folder: {output_dir}")
