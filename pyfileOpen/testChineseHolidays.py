from datetime import date,datetime
#from chinese_holiday import is_holiday
import calendar
from chinese_calendar import ( is_holiday,is_workday,is_in_lieu, get_holidays,get_holiday_detail,get_solar_terms)

# 检查特定日期是否为节假日
def test_is_holiday(testDate):
    #testDate = datetime(2024, 10, 4)
    print(f"{testDate}是否是节假日： {is_holiday(testDate)}")

# 检查特定日期是否为工作日
def test_is_workday(testDate):
    #testDate = datetime(2024, 10, 4)
    print(f"{testDate} 是否是工作日: {is_workday(testDate)}")

# 检查特定日期是否为补休日，即调休的日
def test_is_in_lieu(testDate):
    #testDate = datetime(2024, 10, 4)
    print(f"{testDate} 是否是调休日: {is_in_lieu(testDate)}")

# 检查特定时间段内是否有节假日
def test_get_holidays(testDate,testDate2):
    print(f"get_holidays {testDate}到{testDate2}之间有 {get_holidays(testDate,testDate2)}")

# 检查节假日的详细信息
def test_get_holiday_detail(testDate,testDate2):
    print(f"get_holiday_detail {testDate} - {testDate2} 之间的{get_holiday_detail(testDate2)}")

# 测试calendar的日历生成
def test_get_solar_terms(testDate,testDate2):
    print(f"{testDate} - {testDate2} 之间有solar  {get_solar_terms(date(2025,2,2),date(2025,12,21)) }")

def test_get_calendar():
    print(f"1800-11 的月历：{calendar.month(2025,12)}")


if __name__ == '__main__':
    # 该包没有2004年以前的数据，需要自己编程解决
    testDate = datetime(2025, 9, 20)
    testDate2 = datetime(2025, 10, 5)
    test_is_holiday(testDate)
    test_is_workday(testDate)
    test_is_in_lieu(testDate)
    test_get_holidays(testDate,testDate2)
    test_get_holiday_detail(testDate,testDate2)
    test_get_solar_terms(testDate,testDate2)
    test_get_calendar()

