from pathlib import Path
import polars as pl


def inspect_parquet_file(file_path: str, n: int = 400):
    path = Path(file_path)
    if not path.exists():
        print(f"错误：文件路径不存在 -> {file_path}")
        return

    # 设置 Polars 终端显示参数，确保不省略列与行
    pl.Config.set_tbl_cols(-1)  # 显示所有字段列
    pl.Config.set_tbl_rows(n)  # 设置最大可打印行数为 n

    # 读取 Parquet 文件
    df = pl.read_parquet(file_path)

    print("=" * 90)
    print(f"文件路径 : {file_path}")
    print(f"数据总量 : {len(df):,} 行")
    print(f"数据结构 : {df.schema}")
    print("=" * 90)

    # 查看前 N 条记录
    print(f"\n【前 {n} 条记录 (HEAD)】")
    print(df.head(n))

    print("\n" + "-" * 90 + "\n")

    # 查看后 N 条记录
    print(f"【后 {n} 条记录 (TAIL)】")
    print(df.tail(n))


if __name__ == "__main__":
    # 替换为需要查验的具体 Parquet 文件路径
    TARGET_PARQUET = r"E:\quant_parquet\1min\sh\sh000001.parquet"

    inspect_parquet_file(TARGET_PARQUET, n=400)