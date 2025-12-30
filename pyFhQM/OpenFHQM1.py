import struct
import datetime
import pandas as pd

# 飞狐文件解析：
# 报文头12个字节
# 然后有28个字节用来说明股票代码及股票名字


def get_1m_price_from_file():
    file_name = 'F:\\D盘备份1\\证券股票\\分钟数据\\sh200505-200512.QM1'
    file = open(file_name, 'rb')  # 打开文件
    bytes_all = file.read()  # 读取文件所有的字节数据

    head_length = 12  # 报文头长度
    start_posi = 0
    b = struct.unpack('3I', bytes_all[start_posi: start_posi + 12])
    stock_count = b[2]
    recore_length = 0
    start_posi = head_length
    for posi in range(stock_count):
        b = struct.unpack('8s', bytes_all[start_posi: start_posi + 8])
        stock_code = b[0].decode(encoding='gbk')
        print(stock_code)
        # 股票名称
        b = struct.unpack('8s', bytes_all[start_posi + 12: start_posi + 20])
        print(b[0].decode(encoding='gbk'))
        b = struct.unpack('I', bytes_all[start_posi + 24: start_posi + 28])
        recore_length = int(b[0] / 240)  # 记录的长度，即天数

        start_posi += 28
        for day in range(recore_length):
            dataSet = []
            for i in range(240):
                b = struct.unpack('I', bytes_all[start_posi + i * 32:start_posi + i * 32 + 4])
                time = datetime.datetime.utcfromtimestamp(b[0])
                b = struct.unpack('6f', bytes_all[start_posi + i * 32 + 4:start_posi + i * 32 + 28])

                l = list(b)
                l2 = [round(j, 2) for j in l]
                l2.insert(0, time)
                dataSet.append(l2)
                # print(l2)
            data = pd.DataFrame(data=dataSet, columns=['time', 'open', 'high', 'low', 'close', 'volume', 'amount'])
            print(data)
            start_posi += 7680

if __name__ == '__main__':
    get_1m_price_from_file()


