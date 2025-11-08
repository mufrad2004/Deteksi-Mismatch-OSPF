import json, os, re

# === Fungsi Dasar === #
def load_json(filename):
    with open(filename, "r") as f:
        return json.load(f)

def write_output(filename, results):
    with open(filename, "w", encoding="utf-8") as f:
        f.write("\n".join(results))

def short_ifname(iname: str) -> str:
    """Singkatkan nama interface (FastEthernet0/1 -> Fa0/1)"""
    return (
        iname.replace("FastEthernet", "Fa")
        .replace("GigabitEthernet", "Gi")
        .replace("Loopback", "Lo")
    )

def normalize_ifname(name: str) -> str:
    """Hilangkan spasi seperti 'FastEthernet 0/1' -> 'FastEthernet0/1'"""
    return name.replace(" ", "")

def has_overlap(dict1, dict2):
    """Cek apakah ada pasangan key-id dan key yang sama"""
    for k, v in dict1.items():
        if k in dict2 and dict2[k] == v:
            return True
    return False

# === RULE 1: Cek Neighbor Attributes === #
def check_neighbors(routers):
    results = []
    checked_pairs = set()

    for rname, rdata in routers.items():
        for iname, idata in rdata["interfaces"].items():
            # --- Hanya cek interface yang punya OSPF ---
            if "ospf" not in idata:
                continue
            if iname.startswith("Loopback") or iname == "FastEthernet0/0":
                continue
            if "neighbor" not in idata:
                continue

            nrouter = idata["neighbor"]["router"]
            nintf_raw = idata["neighbor"]["interface"]
            nintf = normalize_ifname(nintf_raw)

            if nrouter not in routers:
                continue

            # --- Cari interface neighbor yang cocok ---
            match_intf = None
            for intf in routers[nrouter]["interfaces"].keys():
                if normalize_ifname(intf) == nintf:
                    match_intf = intf
                    break

            if not match_intf:
                continue

            ndata = routers[nrouter]["interfaces"][match_intf]

            # --- Skip kalau neighbor tidak punya OSPF ---
            if "ospf" not in ndata:
                print(f"[⚠️] Warning: {nrouter} interface {match_intf} tidak punya key 'ospf' (skip)")
                continue

            # --- Hindari perbandingan ganda (A-B dan B-A) ---
            pair_key = tuple(sorted([(rname, iname), (nrouter, match_intf)]))
            if pair_key in checked_pairs:
                continue
            checked_pairs.add(pair_key)

            # === Perbandingan atribut utama === #
            for key in ["Hello", "Dead", "area", "Network Type", "MTU", "passive", "ospf auth"]:
                val1 = idata.get("ospf", {}).get(key) if key != "MTU" else idata.get("MTU")
                val2 = ndata.get("ospf", {}).get(key) if key != "MTU" else ndata.get("MTU")

                # --- PASSIVE khusus (tampilkan format berbeda) ---
                if key == "passive":
                    if val1 != val2 or (val1 is True and val2 is True):
                        results.append(f"=== Mismatch antara {rname} dan {nrouter} ===")
                        results.append("=========================================================")
                        results.append("- passive Mismatch :")
                        results.append(f"\t* {rname} {short_ifname(iname)} : {val1}")
                        results.append(f"\t* {nrouter} {short_ifname(match_intf)} : {val2}")
                        results.append("=========================================================")
                        # --- kondisi keduanya True
                        if val1 is True and val2 is True:
                            results.append("+ Solusi :")
                            results.append(f"\t* Matikan passive interface pada interface {short_ifname(iname)} di {rname} dan interface {short_ifname(match_intf)} di {nrouter}")
                        # --- kondisi beda
                        elif val1 is True and val2 is False:
                            results.append(f"+ Solusi :\n\t* Matikan passive interface pada interface {short_ifname(iname)} di {rname}")
                        elif val2 is True and val1 is False:
                            results.append(f"+ Solusi :\n\t* Matikan passive interface pada interface {short_ifname(match_intf)} di {nrouter}")
                        results.append("=========================================================\n")
                        continue  # skip lanjut ke format default

                # --- Default mismatch ---
                if val1 != val2:
                    results.append(f"=== Mismatch antara {rname} dan {nrouter} ===")
                    results.append("=========================================================")
                    results.append(f"- {key} Mismatch :")
                    results.append(f"\t* {rname} {short_ifname(iname)} : {val1}")
                    results.append(f"\t* {nrouter} {short_ifname(match_intf)} : {val2}")
                    results.append("=========================================================")
                    results.append(f"+ Solusi :\n\t* Samakan nilai {key} pada {rname} dan {nrouter}")
                    results.append("=========================================================\n")

            # === AUTH KEY MISMATCH === #
            key1 = idata.get("ospf", {}).get("auth_key", {})
            key2 = ndata.get("ospf", {}).get("auth_key", {})

            if key1 or key2:
                # --- Simple vs MD5 mismatch ---
                if ("simple" in key1 and "simple" not in key2) or ("simple" in key2 and "simple" not in key1):
                    results.append(f"=== Mismatch antara {rname} dan {nrouter} ===")
                    results.append("=========================================================")
                    results.append("- auth_key Mismatch :")
                    results.append(f"\t* {rname} {short_ifname(iname)} :")
                    for k, v in key1.items():
                        results.append(f"\t\t* {k} : {v}")
                    results.append(f"\t* {nrouter} {short_ifname(match_intf)} :")
                    for k, v in key2.items():
                        results.append(f"\t\t* {k} : {v}")
                    results.append("=========================================================")
                    results.append("+ Solusi :")
                    results.append(f"\t* {rname} dan {nrouter} memiliki jenis Authentication yang berbeda")
                    results.append(f"\t* Samakan jenis Authentication dan Authentication Key")
                    results.append("=========================================================\n")

                # --- Simple key mismatch ---
                elif "simple" in key1 or "simple" in key2:
                    if key1.get("simple") != key2.get("simple"):
                        results.append(f"=== Mismatch antara {rname} dan {nrouter} ===")
                        results.append("=========================================================")
                        results.append("- auth_key Mismatch :")
                        results.append(f"\t* {rname} {short_ifname(iname)} : {key1.get('simple')}")
                        results.append(f"\t* {nrouter} {short_ifname(match_intf)} : {key2.get('simple')}")
                        results.append("=========================================================")
                        results.append("+ Solusi :")
                        results.append(f"\t* {rname} dan {nrouter} memiliki Authentication Key yang berbeda")
                        results.append(f"\t* Samakan Authentication Key")
                        results.append("=========================================================\n")

                # --- MD5 / multi-key mismatch ---
                elif key1 != key2:
                    results.append(f"=== Mismatch antara {rname} dan {nrouter} ===")
                    results.append("=========================================================")
                    results.append("- auth_key Mismatch :")
                    results.append(f"\t* {rname} {short_ifname(iname)} :")
                    for k, v in key1.items():
                        results.append(f"\t\t* {k} : {v}")
                    results.append(f"\t* {nrouter} {short_ifname(match_intf)} :")
                    for k, v in key2.items():
                        results.append(f"\t\t* {k} : {v}")
                    results.append("=========================================================")
                    results.append("+ Solusi :")
                    results.append(f"\t* {rname} dan {nrouter} memiliki Authentication Key yang berbeda")
                    results.append(f"\t* Samakan Authentication Key antara kedua router")
                    results.append("=========================================================\n")

    return results


# === RULE 2: Cek Redistribute === #
def check_redistribute(routers):
    results = []
    for rname, rdata in routers.items():
        prots = rdata["routing"]["protocol"]
        need_redist = len(prots) > 1
        if need_redist and not rdata["routing"]["redistribute"]:
            results.append(f"=== Mismatch pada {rname} ===")
            results.append("=========================================================")
            results.append("- Redistribute Mismatch :")
            results.append(f"\t* {rname} belum melakukan redistribute atau command kurang \"subnets\"")
            results.append("=========================================================")
            results.append("+ Solusi :\n\t* Tambahkan command \"redistribute eigrp <as number> subnets\"")
            results.append("=========================================================\n")
    return results


# === RULE 3: Cek Duplicate Router ID === #
def check_router_id(routers):
    results = []
    ids = {}
    all_ids = {}

    for rname, rdata in routers.items():
        if "ospf" in rdata["routing"]["protocol"]:
            rid = rdata.get("router_id")
            if rid:
                ids.setdefault(rid, []).append(rname)
                all_ids[rname] = rid

    for rid, rtrs in ids.items():
        if len(rtrs) > 1:
            r1, r2 = rtrs[0], rtrs[1]
            results.append(f"=== Mismatch antara {r1} dan {r2} ===")
            results.append("=========================================================")
            results.append("- Router ID Mismatch :")
            for r in rtrs:
                results.append(f"\t* {r} : {rid}")
            results.append("=========================================================")
            results.append("+ Solusi :")
            results.append("\t* Router ID pada OSPF (semua router saat ini) :")
            for r, idv in all_ids.items():
                pointer = " <-" if idv == rid else ""
                results.append(f"\t\t- {r} : {idv}{pointer}")
            results.append("\n\t* Ubahlah Router ID agar unik")
            results.append("=========================================================\n")

    return results


# === MAIN PROGRAM === #
if __name__ == "__main__":
    ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_rule_based_dir = os.path.join(ROOT_DIR, "03_Output", "Data_Rule_Based")
    hasil_dir = os.path.join(ROOT_DIR, "03_Output", "Hasil_Rule_Based")
    os.makedirs(hasil_dir, exist_ok=True)

    json_files = sorted([f for f in os.listdir(data_rule_based_dir) if re.match(r"topologi_\d+\.json$", f)])

    if not json_files:
        print("[!] Tidak ada file JSON ditemukan di Data_Rule_Based/")
    else:
        for json_file in json_files:
            input_path = os.path.join(data_rule_based_dir, json_file)
            topo_num = re.findall(r"\d+", json_file)[0]
            output_path = os.path.join(hasil_dir, f"hasil_deteksi_{topo_num}.txt")

            routers = load_json(input_path)
            results = []
            results += check_neighbors(routers)
            results += check_redistribute(routers)
            results += check_router_id(routers)

            if not results:
                results = [f"[✓] Tidak ditemukan mismatch pada topologi {topo_num}"]

            write_output(output_path, results)
            print(f"[✓] Deteksi selesai untuk {json_file} → {output_path}")
