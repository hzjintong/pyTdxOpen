import pandas as pd
import numpy as np
import chardet

def load_split_data(file_path):
    """
    读取并预处理权息资料
    格式：代码,日期,送股,配股,配股价,红利
    """

    # 假设文件编码为 utf-8 或 gbk
    df_split = pd.read_csv(
        file_path,
        encoding='gb18030',
        header=0,
        dtype={'代码': str, '日期': str}
        )
    # df_split.columns = ['code', 'date','song', 'pei', 'peiprice', 'fenhong']
    print("读取到的列名：", df_split.columns.tolist())

    # 将日期转换为整数，方便与 TDX 日线数据的日期匹配
    df_split['日期'] = df_split['日期'].astype(int)
    return df_split

if __name__ == '__main__':
    df = load_split_data(file_path='wsSHSZ_SPLITs.txt')
    print(df.head())
