import struct
import datetime
from typing import Dict, Optional, Tuple # , List （List库目前没用到，后续也许会用到）
import pandas as pd
from pathlib import Path
import logging
from dataclasses import dataclass

# 设置日志，便于调试
# 这是读取和解析飞狐导出文件QM1的程序

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@dataclass
class FoxMinuteDataHeader:
    """飞狐分钟数据文件头信息"""
    magic_number: int  # 标识
    date_range: int  # 日期范围
    stock_count: int  # 股票数量


@dataclass
class FoxStockInfo:
    """股票基本信息"""
    code: str  # 股票代码
    name: str  # 股票名称
    record_count: int  # 总记录数
    day_count: int  # 天数（记录数/240）


@dataclass
class MinuteRecord:
    """单条分钟记录"""
    timestamp: datetime.datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float


class FoxMinuteDataParser:
    """飞狐股票分钟数据解析器"""

    # 常量定义
    HEADER_SIZE = 12  # 文件头大小（字节）
    STOCK_INFO_SIZE = 28  # 股票信息块大小（字节）
    RECORD_SIZE = 32  # 单条分钟记录大小（字节）
    RECORDS_PER_DAY = 240  # 每天记录数（4小时*60分钟）

    def __init__(self, file_path: str, debug_mode: bool = True):
        """
        初始化解析器

        Args:
            file_path: 飞狐分钟数据文件路径
            debug_mode: 是否启用调试模式（打印中间结果）
        """
        self.file_path = Path(file_path)
        self.debug_mode = debug_mode
        self.file_data = None
        self.file_header = None
        self.stocks_info = []

    def load_file(self) -> bytes:
        """加载文件数据"""
        if not self.file_path.exists():
            raise FileNotFoundError(f"文件不存在: {self.file_path}")

        logger.info(f"开始加载文件: {self.file_path}")
        with open(self.file_path, 'rb') as f:
            self.file_data = f.read()

        logger.info(f"文件加载完成，总大小: {len(self.file_data)} 字节")
        return self.file_data

    def parse_file_header(self) -> FoxMinuteDataHeader:
        """解析文件头"""
        if self.file_data is None:
            raise ValueError("请先调用 load_file() 加载文件数据")

        logger.info("开始解析文件头...")

        # 解析前12个字节的头部信息
        header_bytes = self.file_data[0:self.HEADER_SIZE]
        magic, date_range, stock_count = struct.unpack('3I', header_bytes)

        self.file_header = FoxMinuteDataHeader(
            magic_number=magic,
            date_range=date_range,
            stock_count=stock_count
        )

        if self.debug_mode:
            logger.info(f"文件头解析结果:")
            logger.info(f"  Magic Number: {magic:#x}")
            logger.info(f"  日期范围: {date_range}")
            logger.info(f"  股票数量: {stock_count}")

        return self.file_header

    def parse_stock_info_block(self, start_pos: int) -> Tuple[FoxStockInfo, int]:
        """
        解析单个股票信息块

        Returns:
            (股票信息, 下一个块开始位置)
        """
        # 股票代码（8个字节）
        stock_code_bytes = self.file_data[start_pos:start_pos + 8]
        stock_code = stock_code_bytes.decode('gbk', errors='ignore').strip('\x00')

        # 股票名称（从偏移12开始，8个字节）
        stock_name_bytes = self.file_data[start_pos + 12:start_pos + 20]
        stock_name = stock_name_bytes.decode('gbk', errors='ignore').strip('\x00')

        # 记录总数（从偏移24开始，4个字节）
        record_count_bytes = self.file_data[start_pos + 24:start_pos + 28]
        record_count = struct.unpack('I', record_count_bytes)[0]

        # 计算天数（每天240条记录）
        day_count = record_count // self.RECORDS_PER_DAY

        stock_info = FoxStockInfo(
            code=stock_code,
            name=stock_name,
            record_count=record_count,
            day_count=day_count
        )

        next_start_pos = start_pos + self.STOCK_INFO_SIZE

        if self.debug_mode:
            logger.info(f"股票信息解析:")
            logger.info(f"  代码: {stock_code}")
            logger.info(f"  名称: {stock_name}")
            logger.info(f"  记录数: {record_count}")
            logger.info(f"  天数: {day_count}")

        return stock_info, next_start_pos

    def parse_minute_record(self, start_pos: int) -> MinuteRecord:
        """解析单条分钟记录"""
        # 时间戳（4个字节）
        timestamp_bytes = self.file_data[start_pos:start_pos + 4]
        timestamp_int = struct.unpack('I', timestamp_bytes)[0]

        # 注意：飞狐数据的时间戳可能是从特定起点开始的，这里使用UTC时间
        # 实际使用时可能需要根据数据格式调整
        timestamp = datetime.datetime.fromtimestamp(timestamp_int, datetime.UTC)  # 这里按开发环境提示修改为新的函数调用

        # 价格和成交数据（6个float，24字节）
        data_bytes = self.file_data[start_pos + 4:start_pos + 28]
        open_price, high, low, close, volume, amount = struct.unpack('6f', data_bytes)

        # 保留两位小数
        open_price = round(open_price, 2)
        high = round(high, 2)
        low = round(low, 2)
        close = round(close, 2)

        return MinuteRecord(
            timestamp=timestamp,
            open=open_price,
            high=high,
            low=low,
            close=close,
            volume=volume,
            amount=amount
        )

    def parse_day_data(self, start_pos: int, day_index: int) -> pd.DataFrame:
        """解析一天的数据（240条分钟记录）"""
        records = []

        for minute in range(self.RECORDS_PER_DAY):
            record_pos = start_pos + minute * self.RECORD_SIZE
            record = self.parse_minute_record(record_pos)
            records.append(record)

            if self.debug_mode and minute < 3:  # 只打印前3条记录作为示例
                logger.debug(f"  第{day_index + 1}天 第{minute + 1}分钟: "
                             f"时间={record.timestamp}, "
                             f"OHLC=({record.open},{record.high},{record.low},{record.close})")

        # 转换为DataFrame
        df = pd.DataFrame([{
            'time': r.timestamp,
            'open': r.open,
            'high': r.high,
            'low': r.low,
            'close': r.close,
            'volume': r.volume,
            'amount': r.amount
        } for r in records])

        return df

    def parse_all_stocks(self) -> Dict[str, Dict[str, pd.DataFrame]]:
        """解析所有股票数据"""
        if self.file_header is None:
            self.parse_file_header()

        logger.info(f"开始解析 {self.file_header.stock_count} 只股票的数据...")

        all_data = {}
        current_pos = self.HEADER_SIZE

        for stock_idx in range(self.file_header.stock_count):
            logger.info(f"\n解析第 {stock_idx + 1}/{self.file_header.stock_count} 只股票...")

            # 解析股票信息
            stock_info, data_start_pos = self.parse_stock_info_block(current_pos)
            self.stocks_info.append(stock_info)

            logger.info(f"开始解析 {stock_info.code} 的 {stock_info.day_count} 天数据...")

            stock_data = {}
            daily_data_start_pos = data_start_pos

            for day_idx in range(stock_info.day_count):
                if self.debug_mode:
                    logger.info(f"  解析第 {day_idx + 1}/{stock_info.day_count} 天...")

                day_df = self.parse_day_data(daily_data_start_pos, day_idx)
                date_str = day_df['time'].iloc[0].strftime('%Y%m%d')
                stock_data[date_str] = day_df

                # 移动到下一天数据
                daily_data_start_pos += self.RECORDS_PER_DAY * self.RECORD_SIZE

            # 保存这只股票的所有数据
            all_data[stock_info.code] = {
                'info': stock_info,
                'data': stock_data
            }

            # 移动到下一只股票
            current_pos = daily_data_start_pos

        logger.info(f"所有股票数据解析完成！")
        return all_data

    def parse_single_stock(self, target_code: str) -> Optional[Dict[str, pd.DataFrame]]:
        """解析指定股票代码的数据"""
        if self.file_header is None:
            self.parse_file_header()

        logger.info(f"开始查找并解析股票 {target_code}...")

        current_pos = self.HEADER_SIZE
        found_stock = None

        for stock_idx in range(self.file_header.stock_count):
            stock_info, data_start_pos = self.parse_stock_info_block(current_pos)

            if stock_info.code == target_code:
                found_stock = stock_info
                logger.info(f"找到股票 {target_code}，开始解析数据...")

                stock_data = {}
                daily_data_start_pos = data_start_pos

                for day_idx in range(stock_info.day_count):
                    day_df = self.parse_day_data(daily_data_start_pos, day_idx)
                    date_str = day_df['time'].iloc[0].strftime('%Y%m%d')
                    stock_data[date_str] = day_df

                    # 移动到下一天数据
                    daily_data_start_pos += self.RECORDS_PER_DAY * self.RECORD_SIZE

                return {
                    'info': stock_info,
                    'data': stock_data
                }

            # 移动到下一只股票
            # 先跳过当前股票的分钟数据
            total_minutes_data_size = stock_info.day_count * self.RECORDS_PER_DAY * self.RECORD_SIZE
            current_pos = data_start_pos + total_minutes_data_size

        logger.warning(f"未找到股票 {target_code}")
        return None

    def get_summary(self) -> pd.DataFrame:
        """获取文件数据摘要"""
        if not self.stocks_info:
            self.parse_all_stocks()

        summary_data = []
        for stock in self.stocks_info:
            summary_data.append({
                '股票代码': stock.code,
                '股票名称': stock.name,
                '总记录数': stock.record_count,
                '天数': stock.day_count,
                '日均记录数': stock.record_count / stock.day_count if stock.day_count > 0 else 0
            })

        return pd.DataFrame(summary_data)


def main():
    """主函数示例"""
    # 文件路径（请修改为实际路径）
    file_path = r'E:\D盘备份1\证券股票\分钟数据\sh200505-200512.QM1'

    try:
        # 创建解析器实例（启用调试模式）
        parser = FoxMinuteDataParser(file_path, debug_mode=True)

        # 1. 加载文件
        parser.load_file()

        # 2. 解析文件头
        header = parser.parse_file_header()

        # 3. 方式1：解析所有股票（大数据量时可能较慢）
        # all_data = parser.parse_all_stocks()

        # 3. 方式2：只解析特定股票（推荐）
        target_stock = 'SH600000'  # 修改为目标股票代码
        single_stock_data = parser.parse_single_stock(target_stock)

        if single_stock_data:
            # 获取第一天的数据示例
            first_date = next(iter(single_stock_data['data']))
            first_day_df = single_stock_data['data'][first_date]

            print("\n" + "=" * 50)
            print(f"股票 {target_stock} 的数据示例（{first_date}）:")
            print("=" * 50)
            print(f"数据形状: {first_day_df.shape}")
            print(f"时间范围: {first_day_df['time'].min()} 到 {first_day_df['time'].max()}")
            print("\n前5条记录:")
            print(first_day_df.head())
            print("\n数据统计:")
            print(first_day_df[['open', 'high', 'low', 'close', 'volume']].describe())

        # 4. 获取数据摘要
        print("\n" + "=" * 50)
        print("文件数据摘要:")
        print("=" * 50)
        summary_df = parser.get_summary()
        print(summary_df.to_string())

        # 5. 保存数据到CSV（示例）
        if single_stock_data:
            for date_str, day_df in single_stock_data['data'].items():
                output_file = f"{target_stock}_{date_str}_分钟数据.csv"
                day_df.to_csv(output_file, index=False, encoding='utf-8-sig')
                print(f"已保存 {date_str} 数据到: {output_file}")

    except Exception as e:
        logger.error(f"解析过程出错: {e}", exc_info=True)


if __name__ == "__main__":
    # 详细调试信息
    logging.getLogger(__name__).setLevel(logging.DEBUG)
    main()