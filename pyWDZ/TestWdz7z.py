import struct, os


def identify_compression(file_path):
    print(f"尝试识别文件压缩格式: {os.path.basename(file_path)}")

    # 常见压缩格式的文件头签名 (Magic Bytes)
    compression_signatures = {
        b'\x1f\x8b\x08': 'GZIP',
        b'\x42\x5a\x68': 'BZIP2',
        b'\xfd7zXZ\x00': 'XZ',
        b'\x04\x22\x4d\x18': 'LZ4',
        b'\x28\xb5\x2f\xfd': 'Zstandard (ZSTD)',
        b'PK\x03\x04': 'ZIP Archive',
        b'Rar!\x1a\x07\x00': 'RAR',
        b'7z\xbc\xaf\x27\x1c': '7-Zip',
        b'MSCF\x00\x00\x00': 'Microsoft CAB',
        # Windows/DOS 可执行文件常见头，有时会包裹压缩数据
        b'MZ': 'DOS/Windows Executable (可能内嵌数据)'
    }

    with open(file_path, 'rb') as f:
        header = f.read(64)  # 多读一些以匹配长签名

    found = False
    for magic, format_name in compression_signatures.items():
        if header.startswith(magic):
            print(f"✅ 匹配到格式: {format_name}")
            print(f"   魔术字节 (十六进制): {magic.hex()}")
            found = True

    if not found:
        print("❌ 未匹配到已知的压缩格式头。")
        print("这可能意味着：")
        print("  1. 使用了自定义或较冷门的压缩算法。")
        print("  2. 文件有一个自定义的文件头（例如几个字节的版本号），压缩数据在后面。")
        print("  3. 进行了简单的流式压缩，没有标准头部。")
        print("\n正在分析可能存在的自定义头部...")

        # 尝试查找任何可能表示“数据开始”的偏移量
        # 有时在自定义头之后会有明显的模式变化
        for offset in [4, 8, 16, 32, 128]:
            if len(header) > offset:
                print(f"  跳过 {offset} 字节后的16位: {header[offset:offset + 16].hex()}")

    # 额外的线索：VC++常用库
    print("\n💡 VC++项目常用的压缩库有：")
    print("  - Zlib (通常包装为GZIP或原始DEFLATE流)")
    print("  - LZMA (7-Zip SDK)")
    print("  - 早期项目可能使用自研的简易RLE或LZ77变种")


# 运行识别
file_path = r"G:\D盘备份1\证券股票\分钟数据\wstock_SHSZ_201701_5Min.wdz"
if os.path.exists(file_path):
    identify_compression(file_path)
else:
    print("文件不存在。")