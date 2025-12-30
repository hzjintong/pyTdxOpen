import zlib, lzma, bz2, sys, os


def probe_decompression_v2(file_path, start_offset=0, probe_size=102400):
    """
    从指定偏移量开始，尝试用多种算法解压数据。
    修复了异常捕获问题，并优化了输出。
    """
    print(f"\n🔍 正在探测从偏移量 {start_offset:#x} ({start_offset}) 开始的压缩数据...")

    with open(file_path, 'rb') as f:
        f.seek(start_offset)
        compressed_data = f.read(probe_size)
        # 也打印一下开始几个字节，方便观察
        print(f"   数据起始字节(hex): {compressed_data[:16].hex()}...")

    results = []

    # 1. 尝试 Zlib / DEFLATE (最常见)
    for wbits in [zlib.MAX_WBITS, -zlib.MAX_WBITS, 15 + 16, 15]:  # 常用wbits组合
        try:
            decompressed = zlib.decompress(compressed_data, wbits=wbits)
            # 计算可读性：ASCII字符比例
            if len(decompressed) > 0:
                sample = decompressed[:1000] if len(decompressed) > 1000 else decompressed
                ascii_count = sum(32 <= c < 127 for c in sample)
                ascii_ratio = ascii_count / len(sample)
                # 同时检查是否有很多连续的0x00（可能是二进制整数0）
                zero_ratio = sample.count(0) / len(sample)

                results.append(("zlib/deflate", wbits, decompressed[:64], len(decompressed), ascii_ratio, zero_ratio))
        except (zlib.error, EOFError):
            continue

    # 2. 尝试原始LZMA (7-Zip SDK常用)
    # 尝试多种可能的LZMA过滤器配置
    lzma_filters = [
        [{"id": lzma.FILTER_LZMA1}],
        [{"id": lzma.FILTER_LZMA2}],
    ]
    for filters in lzma_filters:
        try:
            decompressed = lzma.decompress(compressed_data, format=lzma.FORMAT_RAW, filters=filters)
            if len(decompressed) > 0:
                sample = decompressed[:1000] if len(decompressed) > 1000 else decompressed
                ascii_count = sum(32 <= c < 127 for c in sample)
                ascii_ratio = ascii_count / len(sample)
                zero_ratio = sample.count(0) / len(sample)
                filter_name = "LZMA1" if filters[0]["id"] == lzma.FILTER_LZMA1 else "LZMA2"
                results.append(
                    (f"raw {filter_name}", "-", decompressed[:64], len(decompressed), ascii_ratio, zero_ratio))
        except (lzma.LZMAError, ValueError):
            continue

    # 3. 尝试BZIP2 (修正了异常捕获)
    try:
        decompressed = bz2.decompress(compressed_data)
        if len(decompressed) > 0:
            sample = decompressed[:1000] if len(decompressed) > 1000 else decompressed
            ascii_count = sum(32 <= c < 127 for c in sample)
            ascii_ratio = ascii_count / len(sample)
            zero_ratio = sample.count(0) / len(sample)
            results.append(("bz2", "-", decompressed[:64], len(decompressed), ascii_ratio, zero_ratio))
    except OSError:  # bz2.decompress 在失败时引发 OSError
        pass

    # 4. 尝试简单的字节反转（处理大小端问题后再尝试解压）
    # 有时数据会以错误的大小端存储
    reversed_data = compressed_data[:128][::-1]  # 只反转前128字节尝试
    for wbits in [zlib.MAX_WBITS, 15]:
        try:
            decompressed = zlib.decompress(reversed_data, wbits=wbits)
            if len(decompressed) > 0:
                sample = decompressed[:500]
                ascii_ratio = sum(32 <= c < 127 for c in sample) / len(sample) if sample else 0
                results.append((f"zlib (数据反转后)", wbits, decompressed[:64], len(decompressed), ascii_ratio, 0))
        except (zlib.error, EOFError):
            continue

    # 分析并展示结果
    if not results:
        print("   ❌ 当前偏移量下，所有标准压缩算法尝试均失败。")
        return None
    else:
        print("   探测结果摘要 (按ASCII可读性排序):")
        # 按ASCII比率排序，高的在前
        results.sort(key=lambda x: x[4], reverse=True)
        for algo, param, sample, out_len, ascii_ratio, zero_ratio in results[:5]:  # 只显示前5个最好的结果
            status = "✅ 高可读性" if ascii_ratio > 0.3 else "⚠️  低可读性" if ascii_ratio > 0.1 else "🔍 二进制数据"
            print(
                f"     [{status}] 算法: {algo:15} 参数: {param:<5} 解压后长度: {out_len:>9,} ASCII: {ascii_ratio:.1%} 零值: {zero_ratio:.1%}")
            # 如果ASCII比例高，尝试显示一些可读字符
            if ascii_ratio > 0.3 and out_len > 10:
                try:
                    text_preview = sample.decode('ascii', errors='ignore')[:30]
                    if text_preview.strip():
                        print(f"        文本预览: '{text_preview}'...")
                except:
                    pass
        # 返回最好的结果
        return results[0] if results else None


def quick_scan_offsets(file_path):
    """快速扫描几个最有可能的偏移量"""
    print("=" * 70)
    print("开始快速扫描可能的自定义头长度")
    print("=" * 70)

    # 常见对齐边界和VC++中可能的结构大小
    test_offsets = [0, 4, 8, 12, 16, 20, 24, 32, 40, 48, 64, 128, 256, 512]

    best_result = None
    best_offset = -1

    for offset in test_offsets:
        result = probe_decompression_v2(file_path, start_offset=offset, probe_size=65536)  # 探测64KB数据
        if result:
            algo, param, sample, out_len, ascii_ratio, zero_ratio = result
            # 记录最好的结果
            if ascii_ratio > 0.5 and (best_result is None or ascii_ratio > best_result[4]):
                best_result = result
                best_offset = offset
                # 如果找到非常好的结果，可以提前停止
                if ascii_ratio > 0.7:
                    print(f"\n✨ 在偏移量 {offset} 发现高可读性数据，这可能就是正确的起始位置！")
                    break

    print("\n" + "=" * 70)
    if best_result and best_result[4] > 0.3:
        algo, param, sample, out_len, ascii_ratio, zero_ratio = best_result
        print(f"🎯 最佳候选: 偏移量 = {best_offset}, 算法 = {algo}, ASCII可读性 = {ascii_ratio:.1%}")
        print(f"   解压后数据长度: {out_len:,} 字节")
        # 尝试解码为文本查看结构
        try:
            text = sample.decode('ascii', errors='ignore')[:100]
            if len(text) > 20:
                print(f"   数据预览: '{text}'...")
        except:
            pass
        return best_offset, best_result
    else:
        print("❌ 未找到明显成功的解压偏移点和算法。")
        print("   可能需要：")
        print("   1. 检查文件是否使用非常见压缩算法")
        print("   2. 查找原软件相关的DLL文件")
        print("   3. 尝试更大的探测数据块")
        return None, None


# 执行探测
file_path = r"G:\D盘备份1\证券股票\分钟数据\wstock_SHSZ_201701_5Min.wdz"
if os.path.exists(file_path):
    file_size = os.path.getsize(file_path)
    print(f"文件: {os.path.basename(file_path)}")
    print(f"大小: {file_size:,} 字节 ({file_size / 1024 / 1024:.2f} MB)")

    # 先查看文件头
    with open(file_path, 'rb') as f:
        header = f.read(48)
        print(f"文件头(hex): {header.hex()}")
        print(f"文件头(ASCII): {''.join(chr(b) if 32 <= b < 127 else '.' for b in header)}")

    # 执行快速扫描
    best_offset, best_result = quick_scan_offsets(file_path)

    # 如果找到了最佳候选，进一步验证
    if best_offset is not None and best_result is not None:
        print("\n" + "=" * 70)
        print("进行深度验证...")
        # 用最佳参数尝试解压更大的数据块
        with open(file_path, 'rb') as f:
            f.seek(best_offset)
            larger_chunk = f.read(min(1024 * 1024, file_size - best_offset))  # 最多1MB

        algo, param, _, _, _, _ = best_result
        if algo.startswith("zlib"):
            try:
                decompressed = zlib.decompress(larger_chunk, wbits=param)
                print(f"✅ 成功解压 {len(decompressed):,} 字节数据")
                # 分析解压后数据的结构
                if len(decompressed) > 100:
                    print("分析解压数据的前100字节:")
                    print(f"  HEX: {decompressed[:100].hex()}")
                    # 检查是否有规律的结构（如固定长度记录）
                    for rec_len in [32, 40, 44, 52, 64, 72]:
                        if len(decompressed) > rec_len * 3:
                            # 检查前几条记录的第一个字段是否相似
                            first_words = [decompressed[i * rec_len:i * rec_len + 4] for i in
                                           range(min(5, len(decompressed) // rec_len))]
                            if len(set(first_words)) < 3:  # 如果前几个记录的第一个字段相似
                                print(f"  ⚠️  检测到可能的固定记录长度: {rec_len} 字节")
            except Exception as e:
                print(f"解压更大数据块时出错: {e}")
else:
    print("文件不存在。")