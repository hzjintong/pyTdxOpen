import struct, os

def try_decrypt_header(file_path):
    print(f"尝试分析加密文件: {os.path.basename(file_path)}")
    with open(file_path, 'rb') as f:
        header_block = f.read(64)  # 读取前64字节用于测试

    print("原始前16字节(hex):", header_block[:16].hex())

    # 方法1: 尝试与可能的魔数进行XOR（最常见的简单加密）
    common_magics = [b'WDT\x00', b'WDF\x00', b'WDZ\x00', b'\x00\x00\x00\x00']
    for magic in common_magics:
        # 假设用魔数循环XOR了文件头
        decrypted = bytes([header_block[i] ^ magic[i % len(magic)] for i in range(min(len(header_block), 16))])
        print(f"尝试与魔数 {magic} XOR 后: {decrypted[:16].hex()} -> ASCII: {decrypted[:16]}")

    # 方法2: 尝试字节反转（大小端转换）
    print(f"\n尝试字节反转(大端序解读):")
    try:
        # 将前16字节按大端序重新解读为4个整数
        as_big_endian = struct.unpack('>IIII', header_block[:16])
        print(f"  解读为4个整数: {as_big_endian}")
        # 尝试将第一个整数视为记录数或日期
        if 1000 < as_big_endian[0] < 10000000:
            print(f"  第一个数 {as_big_endian[0]} 可能在合理记录数范围")
    except:
        pass

    # 方法3: 跳过可能存在的固定长度加密头
    print(f"\n尝试跳过固定长度头后查看:")
    for skip in [4, 8, 16, 32]:
        if len(header_block) > skip + 4:
            potential_magic = header_block[skip:skip+4]
            ascii_repr = potential_magic.decode('ascii', errors='ignore')
            print(f"  跳过 {skip} 字节后: {potential_magic.hex()} -> ASCII: '{ascii_repr}'")

# 使用您的路径
file_path = r"G:\D盘备份1\证券股票\分钟数据\wstock_SHSZ_201701_5Min.wdz"
if os.path.exists(file_path):
    try_decrypt_header(file_path)
else:
    print("文件不存在。")