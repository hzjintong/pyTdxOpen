# import configparser
import os

# 该脚本是读取类通达信股票软件下的网络连接配置文件，已获得可用的服务器地址和端口
def get_ips_from_tdx(tdx_path):
    cfg_path = os.path.join(tdx_path, 'connect.cfg')
    if not os.path.exists( cfg_path ):
        print(f"未找到配置文件: {cfg_path}")
        return

    # 注意：Tdx的cfg文件可能有编码问题，建议用 gbk
    with open(cfg_path, 'r', encoding='gbk', errors='ignore') as f:
        content = f.read()

    print("--- 从本地通达信提取的扩展行情服务器 ---")
    # 查找 [ExHqServer] 板块下的 IP
    import re
    # 匹配 IPAddressX=xxx.xxx.xxx.xxx 和 PortX=7727
    ips = re.findall(r'IPAddress\d+=(.*?)\n', content)
    ports = re.findall(r'Port\d+=(\d+)', content)

    for ip, port in zip(ips, ports):
        print(f"('{ip}', {port}),")

# 请修改为您电脑上通达信的实际安装路径
get_ips_from_tdx(r'D:\new_hxzq_hc')