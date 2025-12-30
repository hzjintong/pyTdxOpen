#!/usr/bin/env python3
import struct
import os


def quick_wdz_check(file_path):
    """快速检查WDZ文件"""

    print(f"检查文件: {os.path.basename(file_path)}")

    with open(file_path, 'rb') as f:
        # 读取前100字节
        data = f.read(100)

        print(f"文件大小: {os.path.getsize(file_path):,} 字节")
        print(f"前100字节十六进制:")

        # 以十六进制显示
        for i in range(0, len(data), 16):
            line = data[i:i + 16]
            hex_str = ' '.join(f'{b:02x}' for b in line)
            ascii_str = ''.join(chr(b) if 32 <= b < 127 else '.' for b in line)
            print(f"{i:04x}: {hex_str:<48} {ascii_str}")

        # 尝试常见的Wind文件头
        possible_magic = data[:4]
        print(f"\n可能的文件标识: {possible_magic}")

        # 常见Wind文件头
        if possible_magic in [b'WDT\x00', b'WDF\x00', b'WDZ\x00']:
            print("✓ 检测到Wind数据文件头")

            # 尝试解析头信息
            try:
                # 常见头结构: magic(4), version(4), record_size(4), record_count(4)
                magic, version, rec_size, rec_count = struct.unpack('<4sIII', data[:16])
                print(f"  版本: {version}")
                print(f"  记录大小: {rec_size}")
                print(f"  记录数: {rec_count}")

                # 如果有记录数，估计总大小
                if rec_count > 0 and rec_size > 0:
                    estimated_size = 16 + rec_count * rec_size
                    print(f"  估计文件大小: {estimated_size:,} 字节")

            except struct.error:
                print("  无法解析头信息")

        else:
            print("⚠ 未知文件格式")

        # 检查是否可能是压缩文件
        common_compression = {
            b'PK\x03\x04': 'ZIP文件',
            b'\x1f\x8b\x08': 'GZIP文件',
            b'BZh': 'BZIP2文件',
            b'\xfd7zXZ': 'XZ文件',
            b'Rar!\x1a\x07': 'RAR文件',
            b'7z\xbc\xaf\x27\x1c': '7-Zip文件',
        }

        for magic_bytes, desc in common_compression.items():
            if data.startswith(magic_bytes):
                print(f"✓ 检测到压缩文件: {desc}")
                return


# 使用示例
if __name__ == "__main__":
    import sys
    file_to_check = r"G:\D盘备份1\证券股票\分钟数据\wstock_SHSZ_201701_5Min.wdz"
    if len(sys.argv) > 1:
        file_to_check = sys.argv[1]
    else:
        # 查找当前目录的wdz文件
        import glob

        wdz_files = glob.glob("*.wdz")
        if wdz_files:
            file_to_check = wdz_files[0]
        else:
            print("请指定.wdz文件路径")
            sys.exit(1)

    if os.path.exists(file_to_check):
        quick_wdz_check(file_to_check)
    else:
        print(f"文件不存在: {file_to_check}")