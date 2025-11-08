from netmiko import ConnectHandler
import concurrent.futures
import json
import os
import re

# Router Admin (akses awal dari laptop)
router_admin = {
    "device_type": "cisco_ios",
    "host": "192.168.6.100",   # IP Router Admin
    "username": "cisco",
    "password": "cisco",
}

# Path dinamis ke router_list.json
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
json_path = os.path.join(BASE_DIR, "01_Isi Manual", "router_list.json")

# Load router_list.json
with open(json_path) as f:
    router_list = json.load(f)


# ====== CLEAR CONFIG ====== #
def clear_config(router_name, target_ip):
    try:
        with ConnectHandler(**router_admin) as admin_conn:
            admin_conn.find_prompt()
            print(f"[+] SSH ke {router_name} ({target_ip})")

            # nested SSH ke router target
            admin_conn.write_channel(f"ssh -l cisco {target_ip}\n")
            admin_conn.read_until_pattern("Password:")
            admin_conn.write_channel("cisco\n")
            admin_conn.read_until_pattern(r"#")

            # disable paging
            admin_conn.write_channel("terminal length 0\n")
            admin_conn.read_until_pattern(r"#")

            # masuk ke config mode dan hapus OSPF + EIGRP
            admin_conn.write_channel("conf t\n")
            admin_conn.read_until_pattern(r"\(config\)#")
            admin_conn.write_channel("no router ospf 1\n")
            admin_conn.read_until_pattern(r"\(config\)#")
            admin_conn.write_channel("no router eigrp 1\n")
            admin_conn.read_until_pattern(r"\(config\)#")

            # ambil daftar interface dari "show run | s ^interface"
            admin_conn.write_channel("end\n")
            admin_conn.read_until_pattern(r"#")
            admin_conn.write_channel("show run | s ^interface\n")
            output = admin_conn.read_until_pattern(r"#")

            # regex untuk ambil nama interface
            interfaces = re.findall(r"^interface (\S+)", output, re.M)

            # masuk ke setiap interface dan hapus auth OSPF
            admin_conn.write_channel("conf t\n")
            admin_conn.read_until_pattern(r"\(config\)#")
            for intf in interfaces:
                admin_conn.write_channel(f"interface {intf}\n")
                admin_conn.read_until_pattern(r"\(config-if\)#")
                admin_conn.write_channel("no ip ospf authentication\n")
                admin_conn.read_until_pattern(r"\(config-if\)#")
                admin_conn.write_channel("no ip ospf authentication-key\n")
                admin_conn.read_until_pattern(r"\(config-if\)#")
                admin_conn.write_channel("no ip ospf  message-digest-key 1 md5\n")
                admin_conn.read_until_pattern(r"\(config-if\)#")
                admin_conn.write_channel("no ip ospf network\n")
                admin_conn.read_until_pattern(r"\(config-if\)#")
                admin_conn.write_channel("exit\n")
                admin_conn.read_until_pattern(r"\(config\)#")

            # keluar dan simpan
            admin_conn.write_channel("end\n")
            admin_conn.read_until_pattern(r"#")
            admin_conn.write_channel("wr\n")
            admin_conn.read_until_pattern(r"#")

            print(f"[✓] Clear selesai: {router_name}\n")

    except Exception as e:
        print(f"[!] Gagal {router_name}: {e}")


# ====== MAIN ====== #
if __name__ == "__main__":
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(clear_config, rname, ip) for rname, ip in router_list.items()]
        concurrent.futures.wait(futures)
