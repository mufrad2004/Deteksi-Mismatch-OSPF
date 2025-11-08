from netmiko import ConnectHandler
import concurrent.futures
import json
import os

# Router Admin (akses awal dari laptop)
router_admin = {
    "device_type": "cisco_ios",
    "host": "192.168.6.100",   # IP Router Admin
    "username": "cisco",
    "password": "cisco",
}

# ====== LOAD FILE JSON ====== #
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# router_list.json di folder 01_Isi Manual
router_list_path = os.path.join(BASE_DIR, "01_Isi Manual", "router_list.json")
with open(router_list_path) as f:
    router_list = json.load(f)

# router_roles.json di folder yang sama dengan script
roles_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "router_roles.json")
with open(roles_path) as f:
    roles = json.load(f)

ROLES = roles["ROLES"]


# ====== HELPER ====== #
def is_mgmt_ip(ip: str) -> bool:
    """Cek apakah IP adalah IP management (100.100.100.x)"""
    return ip.startswith("100.100.100.")


def parse_show_ip_int_br(output: str):
    """Parse output 'show ip int br' → list (intf, ip)"""
    interfaces = []
    for line in output.splitlines():
        parts = line.split()
        if len(parts) < 6:
            continue
        name, ip, status, proto = parts[0], parts[1], parts[-2], parts[-1]
        if ip != "unassigned" and status == "up" and proto == "up":
            if not is_mgmt_ip(ip):
                interfaces.append((name, ip))
    return interfaces


# ====== GENERATE CONFIG ====== #
def generate_config(router_name: str, interfaces):
    ospf_config, eigrp_config, ospf_interfaces = [], [], []

    # router-id dari loopback kalau ada, fallback ambil IP mgmt
    loopbacks = [ip for name, ip in interfaces if name.lower().startswith("loopback")]
    router_id = loopbacks[0] if loopbacks else router_list[router_name]

    # Ambil role router
    role = ROLES.get(router_name, {})
    ospf_area = role.get("ospf_area")
    eigrp_only = role.get("eigrp_only", False)
    extra = role.get("extra", {})

    # Advertise interface aktif
    for intf, ip in interfaces:
        if intf in extra:  # mapping spesial di role
            val = extra[intf]
            if isinstance(val, int):  # area lain
                ospf_config.append(f" network {ip} 0.0.0.0 area {val}")
                ospf_interfaces.append(intf)
            elif isinstance(val, str) and val.upper() == "EIGRP":
                eigrp_config.append(f" network {ip} 0.0.0.0")
        else:
            if eigrp_only:
                eigrp_config.append(f" network {ip} 0.0.0.0")
            elif ospf_area is not None:
                ospf_config.append(f" network {ip} 0.0.0.0 area {ospf_area}")
                ospf_interfaces.append(intf)

    # Kalau router ASBR, tambahkan redistribute
    if any(isinstance(v, str) and v.upper() == "EIGRP" for v in extra.values()):
        ospf_config.append(" redistribute eigrp 1 subnets")
        eigrp_config.append(" redistribute ospf 1 metric 1 1 1 1 1")

    # Final config
    config_lines = []
    if ospf_config:
        config_lines.append("router ospf 1")
        config_lines.append(f" router-id {router_id}")
        config_lines.extend(ospf_config)

        # tambahkan auth OSPF hanya untuk interface OSPF (skip loopback & EIGRP)
        for intf in ospf_interfaces:
            # skip loopback
            if intf.lower().startswith("loopback"):
                continue
            # skip interface EIGRP
            val = extra.get(intf, None)
            if isinstance(val, str) and val.upper() == "EIGRP":
                continue

            config_lines.append(f"interface {intf}")
            # ! Kalo mo konfig pake message-digest
            # config_lines.append(" ip ospf authentication message-digest")
            # config_lines.append(" ip ospf message-digest-key 1 md5 cisco123")
            # ! Kalo mo konfig pake auth biasa
            config_lines.append(" ip ospf authentication")
            config_lines.append(" ip ospf authentication-key cisco123")
            
            config_lines.append(" ip ospf network point-to-point") 

    if eigrp_config:
        config_lines.append("router eigrp 1")
        config_lines.append(" no auto-summary")
        config_lines.extend(eigrp_config)

    return config_lines


# ====== PUSH CONFIG ====== #
def push_config(router_name, target_ip):
    try:
        with ConnectHandler(**router_admin) as admin_conn:
            admin_conn.find_prompt()
            print(f"[+] SSH ke {router_name} ({target_ip})")

            # nested SSH ke router tujuan
            admin_conn.write_channel(f"ssh -l cisco {target_ip}\n")
            admin_conn.read_until_pattern("Password:")
            admin_conn.write_channel("cisco\n")
            admin_conn.read_until_pattern(r"#")

            # ambil interface aktif
            admin_conn.write_channel("terminal length 0\n")
            admin_conn.read_until_pattern(r"#")
            admin_conn.write_channel("show ip int br\n")
            output = admin_conn.read_until_pattern(r"#")
            interfaces = parse_show_ip_int_br(output)

            # generate config
            cfg = generate_config(router_name, interfaces)

            # push config
            admin_conn.write_channel("conf t\n")
            admin_conn.read_until_pattern(r"\(config\)#")
            for cmd in cfg:
                admin_conn.write_channel(cmd + "\n")
                admin_conn.read_until_pattern(r"#")

            admin_conn.write_channel("end\n")
            admin_conn.read_until_pattern(r"#")
            admin_conn.write_channel("wr\n")
            admin_conn.read_until_pattern(r"#")

            print(f"[✓] Selesai: {router_name}\n")

    except Exception as e:
        print(f"[!] Gagal {router_name}: {e}")


# ====== MAIN ====== #
if __name__ == "__main__":
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(push_config, rname, ip) for rname, ip in router_list.items()]
        concurrent.futures.wait(futures)
