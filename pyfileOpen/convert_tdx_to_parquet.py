import os
import glob
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
import numpy as np
import polars as pl

# ------------------------------------------------------------------------------
# 1. 通达信 32 字节二进制结构定义 (NumPy dtype)
# ------------------------------------------------------------------------------
TDX_MINUTE_DTYPE = np.dtype([
    ('raw_date', '<u2'),  # 2字节日期
    ('raw_time', '<u2'),  # 2字节时间 (从 00:00 算起的分钟数)
    ('open',     '<f4'),
    ('high',     '<f4'),
    ('low',      '<f4'),
    ('close',    '<f4'),
    ('amount',   '<f4'),  # 成交额
    ('volume',   '<i4'),  # 成交量
    ('reserved', '<i4')  # 保留字段
])


def parse_tdx_file(file_path: str, market: str) -> pl.DataFrame | None:
    """使用 NumPy C 级矢量化解析单个二进制分钟线文件"""
    try:
        # 1. 内存映射高效读入
        data = np.fromfile(file_path, dtype=TDX_MINUTE_DTYPE)
        if len(data) == 0:
            return None

        # 2. 计算年份与 32 年周期修正 (解决 1990-2003 年与 2022-2035 年物理编码冲突)
        raw_date = data['raw_date'].astype(np.uint32)
        year = (raw_date // 2048) + 2004
        year = np.where(year > 2030, year - 32, year)

        # 3. 解析十进制 MMDD (低11位 % 2048)
        mmdd = raw_date % 2048
        month = mmdd // 100
        day = mmdd % 100

        # 4. 解析时间 (从 00:00 算起的分钟数)
        raw_time = data['raw_time'].astype(np.uint32)
        hour = raw_time // 60
        minute = raw_time % 60

        # 5. 标准化代码格式 (如 sh600000)
        file_stem = Path(file_path).stem.lower()
        if file_stem.startswith(market.lower()):
            symbol = file_stem
        else:
            symbol = f"{market.lower()}{file_stem}"

        # 6. 使用 Polars 组装 DataFrame
        df = pl.DataFrame({
            'symbol': symbol,
            'market': market.upper(),
            'year': year,
            'month': month,
            'day': day,
            'hour': hour,
            'minute': minute,
            'open': data['open'],
            'high': data['high'],
            'low': data['low'],
            'close': data['close'],
            'amount': data['amount'],
            'volume': data['volume'],
        })

        # 7. 过滤非法行并合成标准 datetime 时间戳
        df = df.filter(
            (pl.col('year') >= 1990) & (pl.col('year') <= 2030) &
            (pl.col('month') >= 1) & (pl.col('month') <= 12) &
            (pl.col('day') >= 1) & (pl.col('day') <= 31) &
            (pl.col('hour') >= 0) & (pl.col('hour') <= 23) &
            (pl.col('minute') >= 0) & (pl.col('minute') <= 59)
        ).with_columns(
            pl.datetime(
                pl.col('year'), pl.col('month'), pl.col('day'),
                pl.col('hour'), pl.col('minute')
            ).alias('datetime')
        ).drop(['year', 'month', 'day', 'hour', 'minute'])

        return df

    except Exception as e:
        print(f"解析文件出错 [{file_path}]: {e}")
        return None


def convert_single_task(args):
    """多进程独立执行单元 (支持多源数据自动融合、去重与排序)"""
    file_path, market, timeframe, output_base_dir = args
    df = parse_tdx_file(file_path, market)

    if df is not None and len(df) > 0:
        symbol = df['symbol'][0]
        # 目标路径示例: E:/quant_parquet/1min/sh/sh600000.parquet
        target_dir = os.path.join(output_base_dir, timeframe, market.lower())
        os.makedirs(target_dir, exist_ok=True)

        target_path = os.path.join(target_dir, f"{symbol}.parquet")

        # ----------------------------------------------------------------------
        # 核心升级：如果 Parquet 已存在，进行增量融合与自动去重
        # ----------------------------------------------------------------------
        if os.path.exists(target_path):
            try:
                # 1. 读取先前已存在的 Parquet 数据
                existing_df = pl.read_parquet(target_path)

                # 2. 纵向拼接 (旧数据 + 新数据)
                combined_df = pl.concat([existing_df, df])

                # 3. 按 datetime 列去重 (keep='last' 表示若时间戳重叠，以新读入的数据为准)
                combined_df = combined_df.unique(subset=['datetime'], keep='last')

                # 4. 重新按时间戳升序排列，保证 K 线序列严格有序
                df = combined_df.sort('datetime')
            except Exception as e:
                print(f"警告: 读取现有 Parquet [{target_path}] 失败，将进行覆盖。错误: {e}")

        # 5. 写入/刷新 Parquet 文件 (开启 ZSTD 高效压缩)
        df.write_parquet(target_path, compression='zstd', compression_level=3)
        return len(df)

    return 0

def batch_convert_tdx_structure(
        vipdoc_dir: str,
        output_parquet_dir: str,
        structures: dict,
        max_workers: int = 14
):
    """依据通达信目录结构进行多进程批量转换"""
    # 子目录与扩展名、时间粒度的映射表
    type_mapping = {
        'minline': {'exts': ['*.lc1', '*.LC1'], 'tf': '1min'},
        'fzline': {'exts': ['*.lc5', '*.LC5'], 'tf': '5min'}
    }

    task_list = []

    print("开始扫描通达信目录结构...")
    # 遍历市场与子目录组装任务列表
    for market, subfolders in structures.items():
        for subfolder in subfolders:
            # 仅处理 1分钟(minline) 和 5分钟(fzline)
            if subfolder not in type_mapping:
                continue

            config = type_mapping[subfolder]
            folder_path = os.path.join(vipdoc_dir, market, subfolder)

            if not os.path.exists(folder_path):
                print(f"提示: 路径不存在，自动跳过 -> {folder_path}")
                continue

            # 匹配对应扩展名文件
            for ext in config['exts']:
                files = glob.glob(os.path.join(folder_path, ext))
                for file_path in files:
                    task_list.append((file_path, market, config['tf'], output_parquet_dir))

    total_files = len(task_list)
    print(f"扫描完毕，共找到 {total_files} 个待转换文件，启动 {max_workers} 个并行进程...")

    if total_files == 0:
        print("未发现匹配的二进制文件，请检查目录路径。")
        return

    total_rows = 0
    completed = 0

    # 启动进程池并行转换
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(convert_single_task, task) for task in task_list]

        for future in as_completed(futures):
            completed += 1
            rows = future.result()
            total_rows += rows
            if completed % 200 == 0 or completed == total_files:
                print(
                    f"转换进度: {completed}/{total_files} ({completed / total_files * 100:.1f}%) | 累计生成 Bar 行数: {total_rows:,}")

    print(f"\n转换全部完成！Parquet 存储根目录: {output_parquet_dir}")


if __name__ == '__main__':
    # 1. 实际输入的通达信 vipdoc 根路径
    TDX_VIPDOC_DIR = r"F:\D盘备份1\new_hxzq_hc\vipdoc"

    # 2. 转换后 Parquet 文件的输出目标路径 (建议存放在空间充裕的 E 盘)
    OUTPUT_PARQUET_DIR = r"E:/quant_parquet"

    # 3. 目录结构配置
    path_structures = {
        'bj': ['minline', 'fzline', 'lday'],  # 北京
        'ds': ['minline', 'fzline', 'lday'],  # 扩展市场
        'sh': ['minline', 'fzline', 'lday'],  # 上海
        'sz': ['minline', 'fzline', 'lday']  # 深圳
    }

    # 4. 执行转换 (利用 i7-13700KF 的 14 个物理核心并发)
    batch_convert_tdx_structure(
        vipdoc_dir=TDX_VIPDOC_DIR,
        output_parquet_dir=OUTPUT_PARQUET_DIR,
        structures=path_structures,
        max_workers=14
    )
