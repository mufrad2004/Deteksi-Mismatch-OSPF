from netmiko import ConnectHandler
import concurrent.futures
import json
import os
import time

# ==================== ROUTER ADMIN ==================== #
router_admin = {
    "device_type": "cisco_ios",
    "host": "192.168.6.100",  # IP Router Admin
    "username": "cisco",
    "password": "cisco",
}

# ==================== LOAD FILE JSON ==================== #
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

router_list_path = os.path.join(BASE_DIR, "01_Isi Manual", "router_list.json")
with open(router_list_path) as f:
    router_list = json.load(f)

topo_index = 99  # ubah sesuai topologi yang ingin dikonfig
topo_path = os.path.join(BASE_DIR, "03_Output", "Data_Rule_Based", f"topologi_{topo_index}.json")
with open(topo_path) as f:
    topo_data = json.load(f)


# ==================== FUNGSI GENERATE KONFIG ==================== #
def generate_config(router_name, data):
    cfg = []
    router_id = data.get("router_id")
    interfaces = data.get("interfaces", {})
    routing = data.get("routing", {})

    ospf_ifaces = []
    eigrp_ifaces = []

    # ---------- INTERFACE CONFIG ---------- #
    for iface, info in interfaces.items():
        cfg.append(f"interface {iface}")

        # IP & MTU
        if "ip" in info and "subnet" in info:
            cfg.append(f" ip address {info['ip']} {info['subnet']}")
        if "MTU" in info:
            cfg.append(f" mtu {info['MTU']}")

            # ----- Konfigurasi OSPF per-interface ----- #
            if "ospf" in info:
                ospf = info["ospf"]
                auth_type = ospf.get("ospf auth", "none").lower()
                auth_keys = ospf.get("auth_key", {})
                # Tetap konfigurasikan semua kemungkinan kombinasi auth_key
                if auth_keys:
                    # Jika ada key simple
                    if "simple" in auth_keys:
                        key_val = auth_keys["simple"]
                        cfg.append(f" ip ospf authentication-key {key_val}")
                        cfg.append(" ip ospf authentication")
                    # Jika ada key id:key (untuk MD5)
                    for key_id, key_val in auth_keys.items():
                        if key_id != "simple":
                            cfg.append(f" ip ospf message-digest-key {key_id} md5 {key_val}")
                            cfg.append(" ip ospf authentication message-digest")
                # Pastikan baris auth_type juga tetap dikonfigurasikan sesuai deklarasi
                if auth_type == "simple":
                    cfg.append(" ip ospf authentication")
                elif auth_type == "message-digest":
                    cfg.append(" ip ospf authentication message-digest")

                # OSPF attributes
                if "Network Type" in ospf:
                    cfg.append(f" ip ospf network {ospf['Network Type'].lower().replace('_', '-')}")
                if "Hello" in ospf:
                    cfg.append(f" ip ospf hello-interval {ospf['Hello']}")
                if "Dead" in ospf:
                    cfg.append(f" ip ospf dead-interval {ospf['Dead']}")

        cfg.append(" no shutdown")
        cfg.append(" exit")



    # ---------- ROUTING OSPF ---------- #
    if "ospf" in routing.get("protocol", []):
        cfg.append("router ospf 1")
        if router_id:
            cfg.append(f" router-id {router_id}")
        cfg.append(" log-adjacency-changes")

        # Advertise interface OSPF, skip FastEthernet0/0 (management)
        for iface, info in interfaces.items():
            if "fa0/0" in iface.lower() or "fastethernet0/0" in iface.lower():
                continue
            if "ospf" in info and "ip" in info:
                area = info["ospf"].get("area", 0)
                cfg.append(f" network {info['ip']} 0.0.0.0 area {area}")
                ospf_ifaces.append(iface)

        # Passive-interface
        for iface, info in interfaces.items():
            if "fa0/0" in iface.lower() or "fastethernet0/0" in iface.lower():
                continue
            ospf = info.get("ospf", {})
            if ospf.get("passive", False):
                cfg.append(f" passive-interface {iface}")

        # Redistribute EIGRP kalau aktif
        if "eigrp" in routing.get("protocol", []) and routing.get("redistribute", False):
            cfg.append(" redistribute eigrp 1 subnets")
        cfg.append(" exit")

    # ---------- ROUTING EIGRP ---------- #
    if "eigrp" in routing.get("protocol", []):
        cfg.append("router eigrp 1")
        cfg.append(" no auto-summary")

        # Advertise interface tanpa OSPF, skip FastEthernet0/0 (management)
        for iface, info in interfaces.items():
            if "fa0/0" in iface.lower() or "fastethernet0/0" in iface.lower():
                continue
            if "ip" in info and "ospf" not in info:
                cfg.append(f" network {info['ip']} 0.0.0.0")
                eigrp_ifaces.append(iface)

        # Redistribute OSPF ke EIGRP kalau aktif
        if "ospf" in routing.get("protocol", []) and routing.get("redistribute", False):
            cfg.append(" redistribute ospf 1 metric 1 1 1 1 1")

        cfg.append(" exit")

    # ---------- WRITE CONFIG ---------- #
    cfg.append("wr")

    # ---------- DEBUG RINGKAS ---------- #
    if ospf_ifaces or eigrp_ifaces:
        print(f"[✓] {router_name} → OSPF: {ospf_ifaces or '-'} | EIGRP: {eigrp_ifaces or '-'}")
    else:
        print(f"[i] {router_name} tidak ada interface aktif untuk advertise")

    return cfg


# ==================== PUSH CONFIG VIA ADMIN ==================== #
def push_config(router_name, target_ip):
    try:
        with ConnectHandler(**router_admin) as admin_conn:
            admin_conn.find_prompt()
            print(f"[+] SSH ke {router_name} ({target_ip})")

            # Nested SSH ke router tujuan
            admin_conn.write_channel(f"ssh -l cisco {target_ip}\n")
            admin_conn.read_until_pattern("Password:")
            admin_conn.write_channel("cisco\n")
            admin_conn.read_until_pattern(r"#")

            # Ambil data topologi router ini
            if router_name not in topo_data:
                print(f"[!] {router_name} tidak ditemukan di file topologi.")
                return

            router_cfg = generate_config(router_name, topo_data[router_name])

            # Apply konfigurasi
            admin_conn.write_channel("conf t\n")
            admin_conn.read_until_pattern(r"\(config\)#")
            for cmd in router_cfg:
                admin_conn.write_channel(cmd + "\n")
                admin_conn.read_until_pattern(r"#")

            admin_conn.write_channel("end\n")
            admin_conn.read_until_pattern(r"#")
            admin_conn.write_channel("wr\n")
            admin_conn.read_until_pattern(r"#")
            print(f"[✓] Selesai konfigurasi {router_name}")

    except Exception as e:
        print(f"[X] Gagal konfigurasi {router_name}: {e}")


# ==================== MAIN EXECUTION ==================== #
if __name__ == "__main__":
    print(f"=== Mulai konfigurasi dari topologi_{topo_index}.json ===\n")
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(push_config, rname, ip) for rname, ip in router_list.items()]
        concurrent.futures.wait(futures)
    print("\n=== Semua router selesai dikonfigurasi ===")
