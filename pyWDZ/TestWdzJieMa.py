import struct, os, binascii
from collections import Counter


def analyze_encoding(file_path):
    print(f"深度分析文件编码: {os.path.basename(file_path)}")
    with open(file_path, 'rb') as f:
        # 读取足够数据进行分析，重点关注文件头区域
        sample_size = min(4096, os.path.getsize(file_path))
        data = f.read(sample_size)

    print(f"分析样本大小: {sample_size} 字节\n")

    # 1. 显示已知的可疑ASCII区域
    print("1. 定位可读ASCII区域:")
    ascii_positions = []
    for i in range(len(data) - 4):
        # 寻找连续可读ASCII字符
        if all(32 <= data[i + j] < 127 for j in range(4)):
            ascii_positions.append((i, data[i:i + 4].decode('ascii')))

    for pos, text in ascii_positions[:10]:  # 显示前10个
        print(f"   偏移 0x{pos:04x}: '{text}'")

    # 特别关注之前发现的 "GTA"
    target = b'GTA'
    if target in data:
        pos = data.find(target)
        print(f"\n   🔍 关键发现: 'GTA' 位于偏移 0x{pos:04x}")
        print(f"      上下文: {data[pos - 8:pos + 12].hex()}")  # 查看前后字节

    # 2. 分析字节分布模式
    print("\n2. 分析字节值分布:")
    byte_counts = Counter(data)
    print(f"   唯一字节值数量: {len(byte_counts)}")
    # 检查是否有某些值异常多（如0x00填充）
    most_common = byte_counts.most_common(5)
    for byte_val, count in most_common:
        percentage = count / sample_size * 100
        print(
            f"     字节 0x{byte_val:02x} ({chr(byte_val) if 32 <= byte_val < 127 else '.'}): {count:5} 次 ({percentage:.1f}%)")

    # 3. 测试简单XOR密钥
    print("\n3. 测试单字节XOR解码 (寻找可读文本):")
    # 已知常见起始词，如日期、数字等
    known_patterns = [b'2017', b'202', b'1.00', b'0000', b'   ']

    for xor_key in range(256):
        decoded = bytes([b ^ xor_key for b in data[:64]])  # 只解码前64字节
        # 检查解码后是否出现已知模式
        for pattern in known_patterns:
            if pattern in decoded:
                ascii_count = sum(32 <= c < 127 for c in decoded)
                if ascii_count > 20:  # 如果有较多可读字符
                    print(f"   🔑 XOR密钥 0x{xor_key:02x} ({xor_key}) 可能有效:")
                    print(f"      解码预览: {decoded[:40]}")
                    print(f"      包含模式: {pattern}")
                    break

    # 4. 测试字节顺序交换（大小端）
    print("\n4. 测试字节顺序 (大小端):")
    # 尝试将每4字节视为整数，检查是否在合理范围
    if len(data) >= 40:
        for offset in [0, 4, 8, 16]:
            # 以小端序解读
            le_val = struct.unpack('<I', data[offset:offset + 4])[0]
            # 以大端序解读
            be_val = struct.unpack('>I', data[offset:offset + 4])[0]

            # 检查哪个看起来更像合理数据
            plausible_le = 20000000 < le_val < 21000000  # 像日期
            plausible_be = 20000000 < be_val < 21000000

            if plausible_le or plausible_be:
                print(f"   偏移 0x{offset:02x}:")
                if plausible_le:
                    date_str = str(le_val)
                    print(f"     小端序: {le_val} -> 可能日期 {date_str[:4]}-{date_str[4:6]}-{date_str[6:]}")
                if plausible_be:
                    date_str = str(be_val)
                    print(f"     大端序: {be_val} -> 可能日期 {date_str[:4]}-{date_str[4:6]}-{date_str[6:]}")

    # 5. 测试可能的文件结构
    print("\n5. 搜索可能的记录边界:")
    # 寻找重复的字节模式，可能表示固定长度记录
    for test_len in [32, 36, 40, 44, 48, 52, 60, 64]:
        if len(data) > test_len * 3:
            # 检查前几个"记录"是否相似
            chunks = [data[i * test_len:(i + 1) * test_len] for i in range(3)]
            if chunks[0] and chunks[1] and chunks[0][:4] == chunks[1][:4]:
                print(f"   ⚠️  发现可能的记录长度: {test_len} 字节")
                print(f"      前3条记录的前4字节: {chunks[0][:4].hex()}, {chunks[1][:4].hex()}, {chunks[2][:4].hex()}")

    # 6. 查找可能的"魔数"或文件标识
    print("\n6. 搜索可能的文件标识/魔数:")
    common_magics = {
        b'WDT': 'Wind数据文件',
        b'WDF': 'Wind数据文件',
        b'WDZ': 'Wind数据文件',
        b'\x00\x00\x00': '可能的长度字段',
        b'\xFF\xFE': 'UTF-16 LE BOM',
        b'\xFE\xFF': 'UTF-16 BE BOM',
    }

    for magic, desc in common_magics.items():
        if magic in data[:64]:
            pos = data.find(magic)
            print(f"   在偏移 0x{pos:04x} 找到: {magic.hex()} -> {desc}")


def brute_force_simple_decode(file_path):
    """尝试几种最简单的解码假设"""
    print("\n" + "=" * 70)
    print("尝试简单解码假设")
    print("=" * 70)

    with open(file_path, 'rb') as f:
        header_block = f.read(256)  # 读取前256字节

    # 假设1: 整个文件是简单的字节反转 (整个文件以小端存储但误读为大端)
    print("\n假设1: 4字节分组反转 (大小端问题)")
    decoded = bytearray()
    for i in range(0, min(64, len(header_block)), 4):
        chunk = header_block[i:i + 4]
        if len(chunk) == 4:
            decoded.extend(chunk[::-1])  # 4字节内反转
        else:
            decoded.extend(chunk)

    # 检查反转后是否有可读内容
    ascii_text = ''.join(chr(b) if 32 <= b < 127 else '.' for b in decoded)
    print(f"   反转后ASCII: {ascii_text[:80]}")
    if 'WDT' in ascii_text or '2017' in ascii_text:
        print(f"   ✅ 发现有意义文本!")

    # 假设2: 每个字节减去一个固定值 (简单位移编码)
    print("\n假设2: 尝试字节位移编码")
    for delta in [-1, 1, -2, 2, 32, 64, 128]:
        shifted = bytes([(b + delta) % 256 for b in header_block[:48]])
        ascii_text = ''.join(chr(b) if 32 <= b < 127 else '.' for b in shifted)
        if ascii_text.count('.') < 30:  # 如果可读字符较多
            print(f"   位移 {delta:3}: {ascii_text[:60]}")

    # 假设3: 可能是直接的zlib流但缺少头部 (尝试原始DEFLATE)
    print("\n假设3: 尝试无头zlib/DEFLATE流")
    import zlib
    # 从不同偏移尝试
    for offset in [0, 2, 4, 8]:
        try:
            # wbits = -15 表示原始DEFLATE数据，无zlib头和尾
            decompressed = zlib.decompress(header_block[offset:offset + 128], wbits=-15)
            if len(decompressed) > 10:
                print(f"   偏移 {offset}: 原始DEFLATE解出 {len(decompressed)} 字节")
                print(f"      预览: {decompressed[:20].hex()}...")
        except:
            pass


# 执行分析
file_path = r"G:\D盘备份1\证券股票\分钟数据\wstock_SHSZ_201502_5Min.wdz"
if os.path.exists(file_path):
    analyze_encoding(file_path)
    brute_force_simple_decode(file_path)

    # 额外的关键检查：比较多个WDZ文件的头部
    print("\n" + "=" * 70)
    print("建议执行的关键检查:")
    print("=" * 70)
    print("1. 请检查同一目录下是否有其他 .wdz 文件")
    print("2. 如果有，比较它们的前32字节是否相同")
    print("3. 相同部分就是自定义文件头，之后就是数据区")
    print("4. 如果不同，可能是文件头中包含股票代码、日期等信息")
else:
    print("文件不存在。")