import os
import re
import struct
import pandas as pd
from typing import Dict, List, Tuple
from tqdm import tqdm

class TDXDuplicateScanner:
    """
    诊断通达信财务文件中的重复股票记录和字段问题
    并输出xlsx报告
    """
    def __init__(self, cw_dir: str, field_file: str):
        self.cw_dir = cw_dir
        self.field_names = self._load_field_names(field_file)
        self.report_data = []

    def _load_field_names(self, field_file: str) -> Dict[int, str]:
        mapping = {}
        if not os.path.exists(field_file):
            return mapping
        try:
            with open(field_file, 'r', encoding='utf-8') as f:
                for line in f:
                    match = re.match(r'(\d+)\.?--(.+)', line.strip())
                    if match:
                        mapping[int(match.group(1))] = match.group(2)
        except Exception as e:
            print(f"加载字段说明失败: {e}")
        return mapping

    def _get_all_offsets(self, file_path: str) -> Dict[str, List[int]]:
        stock_offsets = {}
        try:
            with open(file_path, 'rb') as f:
                header = f.read(struct.calcsize("<26s1L"))
                if len(header) < 30: return {}
                _, max_count = struct.unpack("<26s1L", header)

                for i in range(max_count):
                    data = f.read(11)  # <6s1c1L 是 11 字节
                    if len(data) < 11: break

                    try:
                        # 核心修正：使用 gbk 且 ignore 错误，防止非文本字节导致崩溃
                        code_bytes, flag, foa = struct.unpack("<6s1c1L", data)
                        code = code_bytes.decode('gbk', errors='ignore').strip('\x00').strip()

                        # 过滤掉不符合股票代码规则的垃圾数据 (通常是 6 位数字)
                        if not re.match(r'^\d{6}$', code):
                            continue

                        if code not in stock_offsets:
                            stock_offsets[code] = []
                        stock_offsets[code].append(foa)
                    except:
                        continue  # 如果单条记录解包失败，跳过，继续下一条
        except Exception as e:
            print(f"无法打开文件 {file_path}: {e}")
        return stock_offsets

    def _read_values(self, file_path: str, foa: int) -> Tuple[float, ...]:
        try:
            with open(file_path, 'rb') as f:
                f.seek(foa)
                # 尝试读取新版 584 字段
                raw = f.read(584 * 4)
                if len(raw) == 584 * 4:
                    return struct.unpack('<584f', raw)
                # 尝试读取旧版 264 字段
                f.seek(foa)
                raw = f.read(264 * 4)
                if len(raw) == 264 * 4:
                    return struct.unpack('<264f', raw)
        except:
            pass
        return tuple()

    def scan(self, output_excel: str = "通达信重复记录诊断报告.xlsx"):
        if not os.path.exists(self.cw_dir):
            print(f"错误：目录不存在 {self.cw_dir}")
            return

        files = [f for f in os.listdir(self.cw_dir) if re.match(r'gpcw\d{8}\.dat', f)]
        files.sort(reverse=True)  # 从新日期开始扫
        print(f"开始扫描 {len(files)} 个文件...")

        for fname in tqdm(files, desc="扫描进度"):
            fpath = os.path.join(self.cw_dir, fname)
            stock_map = self._get_all_offsets(fpath)

            # 找出同一个文件里 code 出现多次的情况
            duplicates = {code: offsets for code, offsets in stock_map.items() if len(offsets) > 1}

            if not duplicates:
                continue

            for code, offsets in duplicates.items():
                # 对比该股票在该文件内的所有重复索引指向的数据
                base_val = self._read_values(fpath, offsets[0])
                if not base_val: continue

                # 遍历后续的重复记录进行比对
                for dup_idx, other_foa in enumerate(offsets[1:], 1):
                    other_val = self._read_values(fpath, other_foa)
                    if not other_val: continue

                    found_diff = False
                    # 对比字段
                    max_fields = min(len(base_val), len(other_val))
                    for i in range(max_fields):
                        v1, v2 = base_val[i], other_val[i]
                        if abs(v1 - v2) > 1e-6:
                            found_diff = True
                            field_name = self.field_names.get(i, f"未知字段_{i}")
                            self.report_data.append({
                                "文件名": fname,
                                "股票代码": code,
                                "重复记录序号": f"1 vs {dup_idx + 1}",
                                "字段ID": i,
                                "字段名称": field_name,
                                "前一处数据": v1,
                                "后一处数据": v2,
                                "差异": v2 - v1
                            })

                    if not found_diff:
                        self.report_data.append({
                            "文件名": fname, "股票代码": code, "重复记录序号": f"1 vs {dup_idx + 1}",
                            "字段ID": "-", "字段名称": "无差异(仅索引重复)",
                            "前一处数据": "-", "后一处数据": "-", "差异": 0
                        })

        if self.report_data:
            df = pd.DataFrame(self.report_data)
            df.to_excel(output_excel, index=False)
            print(f"\n扫描完成！报告已生成: {output_excel}")
            print(f"共发现 {len(df)} 条差异明细。")
        else:
            print("\n扫描完成，未发现任何重复且有差异的记录。")


if __name__ == "__main__":
    # 请务必核对以下路径是否正确
    CW_DIR = r"d:/new_hxzq_hc/vipdoc/cw/"
    FIELD_TXT = "专业财务数据字段说明.txt"

    scanner = TDXDuplicateScanner(CW_DIR, FIELD_TXT)
    scanner.scan("E:/分析日志/通达信CW重复记录诊断报告.xlsx")