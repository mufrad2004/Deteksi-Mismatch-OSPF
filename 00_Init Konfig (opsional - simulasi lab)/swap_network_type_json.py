import os
import json

# === Path utama (ubah sesuai struktur kamu) ===
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "03_Output", "Data_Rule_Based")

def swap_network_type(data):
    """Menukar nilai Network Type: Point_to_point ↔ Broadcast"""
    for router_name, router_data in data.items():
        if not isinstance(router_data, dict):
            continue
        interfaces = router_data.get("interfaces", {})
        for iface_name, iface_data in interfaces.items():
            if not isinstance(iface_data, dict):
                continue
            ospf_data = iface_data.get("ospf", {})
            if not isinstance(ospf_data, dict):
                continue

            ntype = str(ospf_data.get("Network Type", "")).strip().lower()

            if ntype == "point_to_point":
                ospf_data["Network Type"] = "Broadcast"
            elif ntype == "broadcast":
                ospf_data["Network Type"] = "Point_to_point"

    return data


# === Proses semua file topologi ===
count = 0
for fname in sorted(os.listdir(DATA_DIR)):
    if not fname.endswith(".json"):
        continue
    fpath = os.path.join(DATA_DIR, fname)
    try:
        with open(fpath, "r") as f:
            data = json.load(f)

        updated = swap_network_type(data)

        # Overwrite file asli
        with open(fpath, "w") as f:
            json.dump(updated, f, indent=2)

        count += 1
        print(f"[✓] Updated: {fname}")

    except Exception as e:
        print(f"[!] Error processing {fname}: {e}")

print(f"\n=== Selesai. Total file diproses: {count} ===")
print(f"Hasil disimpan langsung di folder: {DATA_DIR}")
