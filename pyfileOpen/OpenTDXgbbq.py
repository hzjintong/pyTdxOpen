import struct
import pandas as pd
import numpy as np


# --- 注意：以下是基于公开算法的核心逻辑，实际密钥需要您自行获得 ---
# 搜索结果中的解密算法是一个复杂的异或和查表过程，需要特定的密钥结构体。
# 此处提供一个解密函数框架，你需要将真实的解密算法（如3DES或自定义流加密）填充进去。
# 如果暂时无法获得真实密钥，作为替代，你可以尝试在网上搜索其他研究者已经编译好的
# 解密工具或动态链接库（DLL），然后在Python中调用。
# ---

def decrypt_record(encrypted_data):
    """
    TODO: 填充真实的解密算法
    解密单条记录的前24字节。
    Args:
        encrypted_data (bytes): 长度为24的加密字节串
    Returns:
        bytes: 解密后的24字节数据
    """
    # 这里假设你的密钥和解密逻辑已经准备好。
    # 例如，如果解密算法是某种异或流，你需要按位还原。
    # 下面的代码仅作为占位符，返回原始数据，实际使用时必须替换。

    # --- 真实解密步骤 (伪代码) ---
    # 1. 加载或初始化密钥 (key)
    # 2. 对 encrypted_data 的每4字节进行循环异或和查表操作 (参考搜索结果中的C代码)
    # 3. 返回解密后的字节串
    # ---

    # 警告：直接返回加密数据意味着解析结果将是错误的。
    print("警告：使用未解密的占位函数，数据将不正确。")
    return encrypted_data  # 请替换为真实解密逻辑


def parse_gbbq(filepath):
    """
    解析通达信 gbbq 文件并返回DataFrame。

    Args:
        filepath (str): gbbq文件的完整路径

    Returns:
        pandas.DataFrame: 包含解析后数据的表格，失败则返回None。
    """
    try:
        with open(filepath, 'rb') as f:
            # 1. 读取文件头 (前4字节，小端序整数)
            header_data = f.read(4)
            if len(header_data) < 4:
                print("文件过小，无法读取头部")
                return None
            record_count = struct.unpack('<I', header_data)[0]
            print(f"文件记录总数: {record_count}")

            records = []
            for i in range(record_count):
                # 2. 读取一条完整记录 (29字节)
                record_raw = f.read(29)
                if len(record_raw) != 29:
                    print(f"警告：读取记录 {i} 时文件意外结束")
                    break

                # 3. 分离加密部分(前24字节)和未加密部分(后5字节)
                encrypted_part = record_raw[:24]
                # plain_part = record_raw[24:29]  # 后5字节实际是四个float中的最后一个？需要按结构体解析。
                # 更准确地说，29字节的整体结构就是市场,代码,日期,t,数据1,数据2,数据3,数据4。
                # 其中数据4本身是最后4字节，加上一个可能是填充或验证的字节？根据文档，29字节恰好是8个字段。
                # 重新梳理：按之前表格，29字节 = 1+7+4+1+4+4+4+4 = 29，没有多余字节。
                # 所以整个29字节除了日期等，都是需要解密或直接使用的。但解密算法只针对前24字节。
                # 这意味着我们先解密前24字节，然后拼接上后5字节，再统一按结构体解析。

                # 4. 解密前24字节
                decrypted_part = decrypt_record(encrypted_part)

                # 5. 拼接解密后的24字节和原始的5字节
                # 注意：最后5字节包含数据3的部分和数据4？还是整个29字节结构就是那样？
                # 根据C代码逻辑，解密是按8字节一组进行，总共3组（24字节），然后跳过5字节。
                # 这5字节其实就是记录中的最后5字节（数据3的后半？和数据4？）。为了简化，我们按整个29字节结构解析，
                # 但需要理解解密只影响前24字节。实际上，解密算法就是为了还原这24字节。
                # 正确做法：解密后得到24字节，这24字节就是记录的前24字节明文。
                # 然后我们需要将这段明文与最后5字节组合成完整的29字节记录。
                # 但最后5字节本身就是明文，所以组合后的29字节就是完整明文记录。

                # 由于我们暂时无法正确解密，以下解析将基于'假设解密成功'的完整29字节数据进行。
                # 如果你解密成功，将 decrypted_part 与 record_raw[24:] 拼接。
                # combined_record = decrypted_part + record_raw[24:]
                # 由于解密函数是占位符，我们暂时直接用原始数据（会导致解析结果错误）
                combined_record = record_raw  # 正式使用时请替换为上面这行

                # 6. 按照表格格式解析组合后的29字节数据
                # 格式: <B 7s I B f f f f (小端序)
                # B: 市场 (1字节)
                # 7s: 代码 (7字节字符串)
                # I: 日期 (4字节无符号整型)
                # B: 类别 (1字节)
                # f: 数据1 (4字节float)
                # f: 数据2 (4字节float)
                # f: 数据3 (4字节float)
                # f: 数据4 (4字节float)
                record_fields = struct.unpack('<B7sIBffff', combined_record)

                market = record_fields[0]
                # 处理股票代码：去除末尾的空字节，并解码为字符串
                code = record_fields[1].split(b'\x00')[0].decode('utf-8')
                date_int = record_fields[2]  # 例如 20230101
                t_type = record_fields[3]
                data1 = record_fields[4]
                data2 = record_fields[5]
                data3 = record_fields[6]
                data4 = record_fields[7]

                # 将日期整数转换为字符串或pandas的datetime格式
                date_str = str(date_int)
                # 简单的格式检查，例如20230101转为2023-01-01
                if len(date_str) == 8:
                    date_formatted = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
                else:
                    date_formatted = date_str

                records.append({
                    '市场': market,
                    '股票代码': code,
                    '日期': date_formatted,
                    '类别': t_type,
                    '数据1': data1,
                    '数据2': data2,
                    '数据3': data3,
                    '数据4': data4
                })

            # 7. 构建DataFrame
            df = pd.DataFrame(records)
            return df

    except FileNotFoundError:
        print(f"错误：文件未找到 - {filepath}")
        return None
    except Exception as e:
        print(f"解析过程中发生错误: {e}")
        return None


# --- 使用示例 ---
if __name__ == "__main__":
    # 请将下面的路径替换为你自己电脑上的gbbq文件路径
    file_path = r"D:\new_hxzq_hc\T0002\hq_cache\gbbq"

    df_result = parse_gbbq(file_path)

    if df_result is not None and not df_result.empty:
        print("解析成功，前10行数据预览：")
        print(df_result.head(10))

        # 如果你想要保存为CSV文件
        # df_result.to_csv('gbbq_parsed.csv', index=False, encoding='utf-8-sig')
    else:
        print("解析失败或文件为空。")