import os
import pandas as pd

# === Path utama === #
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
data_dir = os.path.join(ROOT_DIR, "03_Output", "Data_ML")

# === Proses semua file dataset === #
for fname in sorted(os.listdir(data_dir)):
    if not fname.endswith(".csv"):
        continue

    fpath = os.path.join(data_dir, fname)
    df = pd.read_csv(fpath)
    print(f"[✓] Membaca {fname} ({len(df)} baris awal)")

    # 🔹 Hapus baris jika kolom Hello_a kosong (NaN) atau berisi "none"
    col_hello = next((c for c in df.columns if c.lower() == "hello_a"), None)
    if col_hello:
        before = len(df)
        df[col_hello] = df[col_hello].astype(str).str.strip().str.lower()
        df = df[~df[col_hello].isin(["none", "nan", "", "null"])]
        removed = before - len(df)
        print(f"[–] Menghapus {removed} baris ({col_hello} kosong atau 'none')")

    # Reset index
    df = df.reset_index(drop=True)

    # Overwrite file lama langsung
    df.to_csv(fpath, index=False)

    print(f"[✓] File {fname} diperbarui → {len(df)} baris tersisa\n")

print(f"[✔] Semua dataset selesai dibersihkan dan diperbarui di folder: {data_dir}")
