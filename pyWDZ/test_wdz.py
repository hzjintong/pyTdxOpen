import struct, os


def diagnose_wdz(file_path):
    print(f"诊断文件: {os.path.basename(file_path)}")
    print(f"文件大小: {os.path.getsize(file_path):,} 字节\n")

    with open(file_path, 'rb') as f:
        # 读取前128字节（通常足够包含文件头）
        data = f.read(128)

    print("=== 文件头原始字节 (十六进制) ===")
    hex_str = data.hex()
    for i in range(0, len(hex_str), 32):
        print(hex_str[i:i + 32])

    print("\n=== 文件头原始字节 (ASCII) ===")
    for i in range(0, len(data), 16):
        chunk = data[i:i + 16]
        hex_part = ' '.join(f'{b:02x}' for b in chunk)
        ascii_part = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
        print(f'{i:04x}:  {hex_part:<48}  {ascii_part}')


# 使用您的文件路径
file_path = r"G:\D盘备份1\证券股票\分钟数据\wstock_SHSZ_201701_5Min.wdz"
if os.path.exists(file_path):
    diagnose_wdz(file_path)
else:
    print("文件不存在，请检查路径。")