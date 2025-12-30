import struct, os, math
from collections import Counter


def forensic_examination(file_path, candidate_length, candidate_key):
    """
    法医式检查：对最佳候选参数进行最彻底的验证。
    """
    print(f"🔬 对候选参数进行法医式检查 [长度={candidate_length}, 密钥=0x{candidate_key:02x}]")
    print("=" * 70)

    with open(file_path, 'rb') as f:
        # 读取足够解密多条记录的数据
        f.seek(0)
        encrypted_data = f.read(candidate_length * 20)  # 读取20条记录的量

    # 1. 解密数据
    decrypted_data = bytes([b ^ candidate_key for b in encrypted_data])
    total_records = len(decrypted_data) // candidate_length

    print(f"解密数据大小: {len(decrypted_data)} 字节，共 {total_records} 条记录\n")

    # 2. 检查解密后数据的整体字节分布 (这很关键！)
    print("1. 解密数据的字节值分布:")
    byte_counts = Counter(decrypted_data)
    most_common = byte_counts.most_common(10)
    for byte_val, count in most_common:
        percentage = (count / len(decrypted_data)) * 100
        char_repr = chr(byte_val) if 32 <= byte_val < 127 else '.'
        print(f"   字节 0x{byte_val:02x} ({char_repr}): {count:6} 次 ({percentage:5.1f}%)")

    # 特别关注0x00和0xFF的比例，这可能是原始数据中的“零值”
    zero_ratio = (byte_counts.get(0, 0) / len(decrypted_data)) * 100
    ff_ratio = (byte_counts.get(255, 0) / len(decrypted_data)) * 100
    print(f"   0x00 比例: {zero_ratio:.1f}%")
    print(f"   0xFF 比例: {ff_ratio:.1f}%")
    if zero_ratio > 20 or ff_ratio > 20:
        print(f"   ⚠️  警告：解密数据中0x00或0xFF比例异常高，这可能意味着解密密钥不正确。\n")

    # 3. 将每条记录按候选长度切割，并检查每条记录的内部模式
    print(f"2. 分析前5条记录的内部结构 (每条{candidate_length}字节):")
    records = [decrypted_data[i * candidate_length:(i + 1) * candidate_length] for i in range(min(5, total_records))]

    for i, rec in enumerate(records):
        print(f"\n   记录 {i + 1} (前64字节):")
        hex_line = ' '.join(f'{b:02x}' for b in rec[:64])
        print(f"     HEX: {hex_line}")

        # 尝试寻找子结构：将记录视为一系列2字节和4字节的数字查看
        print(f"     解读为2字节短整型序列（小端）:", end=" ")
        shorts = []
        for j in range(0, min(16, len(rec)), 2):
            if j + 2 <= len(rec):
                val = struct.unpack('<H', rec[j:j + 2])[0]
                shorts.append(val)
        print(f"{shorts[:8]}...")  # 只打印前8个

        print(f"     解读为4字节整型序列（小端）:", end=" ")
        ints = []
        for j in range(0, min(32, len(rec)), 4):
            if j + 4 <= len(rec):
                val = struct.unpack('<I', rec[j:j + 4])[0]
                ints.append(val)
        print(f"{ints[:4]}...")  # 只打印前4个

        # 关键：对每个4字节整数应用通达信日期公式，看是否有合理日期
        print(f"     尝试从中寻找通达信日期码:")
        date_found = False
        for idx, val in enumerate(ints[:8]):  # 检查前8个4字节整数
            year = (val // 2048) + 2004
            month_day = val % 2048
            month = month_day // 100
            day = month_day % 100
            # 放宽条件：允许月份或日为0（可能是时间字段），但年份必须合理
            if 2010 <= year <= 2020:
                print(f"       位置{idx * 4:02d}: 值 {val:10d} -> {year:04d}-{month:02d}-{day:02d}")
                date_found = True
        if not date_found:
            print(f"       未发现合理日期。")

    # 4. 如果候选长度较大，检查其内部是否有固定的“子记录”模式
    if candidate_length > 32:
        print(f"\n3. 检查长记录({candidate_length}字节)内部是否存在固定子结构:")
        # 选取第一条记录，计算其内部的自相关性（滑动窗口）
        sample_record = records[0] if records else decrypted_data[:candidate_length]
        sub_len = find_internal_substructure(sample_record)
        if sub_len:
            print(f"   ✅ 发现可能的内部子结构长度: {sub_len} 字节")
            # 按此子长度重新分割并显示
            num_sub = candidate_length // sub_len
            print(f"   每条记录可能包含 {num_sub} 个 {sub_len} 字节的子块。")
        else:
            print(f"   ❌ 未检测到明显的内部固定子结构。")


def find_internal_substructure(data, max_sub_len=64):
    """
    在一条较长的记录内部，寻找可能重复出现的子结构（固定长度的字段块）。
    使用自相关方法。
    """
    for sub_len in range(4, min(max_sub_len, len(data) // 2), 2):  # 子结构通常是偶数长度
        # 检查数据是否能被此长度整除
        if len(data) % sub_len != 0:
            continue
        # 将数据按子长度分块，检查前几块开头几个字节是否相似
        num_blocks = len(data) // sub_len
        if num_blocks < 2:
            continue
        # 比较每个子块的第一个字节
        first_bytes = [data[i * sub_len] for i in range(num_blocks)]
        # 如果这些字节的值都很接近（比如差值很小），可能是相似结构
        if max(first_bytes) - min(first_bytes) < 10:
            return sub_len
    return None


def try_additive_cipher(file_path, candidate_length):
    """
    尝试加性密码（密文 = (明文 + 密钥) % 256）而非异或。
    如果原始数据中有大量0（如成交量字段为0），那么密文中对应的字节就会直接等于密钥。
    """
    print(f"\n" + "=" * 70)
    print(f"尝试加性密码（而非XOR）解密分析")
    print("=" * 70)

    with open(file_path, 'rb') as f:
        f.seek(0)
        sample = f.read(candidate_length * 5)  # 读5条记录

    # 我们将每条记录的相同位置拿出来看，寻找出现频率最高的字节，它可能就是密钥
    print(f"分析每条记录的相同位置，推测加性密钥:")
    for pos in range(0, min(16, candidate_length)):  # 只检查前16个字节位置
        bytes_at_pos = [sample[i * candidate_length + pos] for i in range(5)
                        if i * candidate_length + pos < len(sample)]
        if bytes_at_pos:
            # 统计该位置出现频率最高的字节值
            counter = Counter(bytes_at_pos)
            most_common_byte, count = counter.most_common(1)[0]
            # 如果5条记录里有3条以上在这个位置字节相同，它就很可能是密钥
            if count >= 3:
                print(f"  位置{pos:2d}: 最常见字节 0x{most_common_byte:02x} (出现{count}次)，可能是密钥。")
                # 尝试用这个字节作为加性密钥解密该位置（即：明文 = (密文 - 密钥) % 256）
                potential_plain = (bytes_at_pos[0] - most_common_byte) % 256
                print(
                    f"       -> 假设密钥={most_common_byte:3d}，则第一条记录此位置明文为: {potential_plain:3d} (0x{potential_plain:02x})")


def brute_force_simple_transformations(file_path):
    """
    如果XOR和加法都不行，尝试其他最简单的可逆变换。
    这是一个‘最后一搏’式的尝试。
    """
    print(f"\n" + "=" * 70)
    print(f"尝试其他简单变换")
    print("=" * 70)

    with open(file_path, 'rb') as f:
        f.seek(0)
        header = f.read(48)  # 读取文件头

    print(f"文件头原始HEX: {header[:32].hex()}...")
    print(f"文件头ASCII: {''.join(chr(b) if 32 <= b < 127 else '.' for b in header[:32])}")

    # 常见变换：按位取反、循环移位、与固定值AND/OR
    transformations = [
        ("按位取反 (~b)", lambda data: bytes([~b & 0xFF for b in data])),
        ("循环左移1位", lambda data: bytes([((b << 1) | (b >> 7)) & 0xFF for b in data])),
        ("循环右移1位", lambda data: bytes([((b >> 1) | (b << 7)) & 0xFF for b in data])),
        ("与0xAA异或", lambda data: bytes([b ^ 0xAA for b in data])),
        ("与0x55异或", lambda data: bytes([b ^ 0x55 for b in data])),
        ("字节顺序反转（每4字节）",
         lambda data: bytes([data[i + j] for i in range(0, len(data), 4) for j in [3, 2, 1, 0] if i + j < len(data)])),
    ]

    print(f"\n尝试对文件头应用简单变换，寻找可读文本:")
    for name, transform_func in transformations:
        transformed = transform_func(header)
        ascii_part = ''.join(chr(b) if 32 <= b < 127 else '.' for b in transformed[:32])
        # 如果出现较多可读字符，显示出来
        readable_count = sum(1 for c in ascii_part if c != '.')
        if readable_count > 10:
            print(f"  {name:20} -> {ascii_part}")
            # 特别检查是否有'WDT','WDF'等标识
            if 'WDT' in ascii_part or 'WDF' in ascii_part:
                print(f"     ✅ 发现可能的数据文件标识!")


def main():
    file_path = r"G:\D盘备份1\证券股票\分钟数据\wstock_SHSZ_201701_5Min.wdz"

    if not os.path.exists(file_path):
        print("文件不存在!")
        return

    print("=" * 70)
    print("WDZ文件格式破解 - 深度验证与反向分析")
    print("=" * 70)

    # 当前最佳候选参数（来自上一轮结果）
    best_length = 164
    best_xor_key = 0xFC

    # 1. 对最佳候选进行法医式检查
    forensic_examination(file_path, best_length, best_xor_key)

    # 2. 尝试加性密码假设（反向攻击）
    try_additive_cipher(file_path, best_length)

    # 3. 尝试其他简单变换（最后一搏）
    brute_force_simple_transformations(file_path)

    print("\n" + "=" * 70)
    print("分析总结与后续建议:")
    print("=" * 70)
    print("根据以上输出，请重点关注：")
    print("1. 【法医检查-第1部分】解密后字节分布：")
    print("   - 如果0x00或0xFF占比极高(>30%)，几乎可断定当前密钥错误。")
    print("   - 观察分布是否相对均匀（这才是未压缩数据的特征）。")
    print("2. 【法医检查-第2部分】寻找‘合理日期’：")
    print("   - 是否有任何4字节整数能通过通达信公式解码出2015-2018年的日期？")
    print("3. 【加性密码分析】是否有某些位置字节高度一致？")
    print("   这可能是破解的关键突破口。")
    print("\n请将上述观察结果反馈给我。")


if __name__ == "__main__":
    main()