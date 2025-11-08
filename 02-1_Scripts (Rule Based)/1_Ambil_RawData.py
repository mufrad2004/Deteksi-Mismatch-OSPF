from netmiko import ConnectHandler
import os
import json
import concurrent.futures

# Router Admin (akses awal dari laptop)
router_admin = {
    "device_type": "cisco_ios",
    "host": "192.168.6.100",
    "username": "cisco",
    "password": "cisco",
}

# Direktori output → simpan di 03_Output/rawdata (selalu di root project)
script_dir = os.path.dirname(__file__)
project_root = os.path.abspath(os.path.join(script_dir, ".."))
base_dir = os.path.join(project_root, "03_Output", "rawdata")

commands = {
    "show interfaces": "interfaces",
    "show ip ospf interface": "ospf",
    "show run | section interface": "config",
    "show run | section router ospf": "ospf_config",
    "show cdp neighbor": "cdp",
    "show ip protocols" : "ip protocols"
}
for folder in set(commands.values()):
    os.makedirs(os.path.join(base_dir, folder), exist_ok=True)

# Load router_list.json (IP management)
path = os.path.join(project_root, "01_Isi Manual", "router_list.json")
with open(path) as f:
    router_list = json.load(f)


# ====== AMBIL DATA ====== #
def ambil_data(router_name, mgmt_ip):
    try:
        print(f"[+] SSH ke {router_name} ({mgmt_ip})")

        # SSH ke Router Admin
        with ConnectHandler(**router_admin) as admin_conn:
            admin_conn.find_prompt()

            # Nested SSH ke router target
            admin_conn.write_channel(f"ssh -l cisco {mgmt_ip}\n")
            admin_conn.read_until_pattern("Password:")
            admin_conn.write_channel("cisco\n")
            admin_conn.read_until_pattern(r"#")

            # Disable paging
            admin_conn.write_channel("terminal length 0\n")
            admin_conn.read_until_pattern(r"#")

            # Jalankan semua command & simpan hasil
            for cmd, folder in commands.items():
                result = admin_conn.send_command(cmd, expect_string=r"#")
                if result.strip():
                    filename = f"{router_name}_{cmd.replace(' ', '_').replace('|', '').replace('/', '')}.txt"
                    path = os.path.join(base_dir, folder, filename)
                    with open(path, "w") as f:
                        f.write(result)

            # Exit dari router target
            admin_conn.write_channel("exit\n")
            admin_conn.read_until_pattern(r"#")

        print(f"[✓] Selesai: {router_name}")

    except Exception as e:
        print(f"[!] Error {router_name}: {e}")


# ====== MAIN ====== #
if __name__ == "__main__":
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(ambil_data, rname, ip) for rname, ip in router_list.items()]
        concurrent.futures.wait(futures)
