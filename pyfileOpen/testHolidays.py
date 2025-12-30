import holidays
from datetime import datetime,date

# from chinese_holiday import is_holiday


# the below is the same, but takes a string:
cn_holidays = holidays.country_holidays('CN')  # this is a dict-like object


def test_holiday(testDate1):
    is_holiday = testDate1 in cn_holidays
    return is_holiday

def main():
    # 该包没有2004年以前的数据，需要自己编程解决
    test_date = date(2025,9,30)
    test_date2 = date(2025,10,9)
    test_result = test_holiday(test_date)
    result = cn_holidays.get_closest_holiday(test_date2)
    print(f"{test_date}当天 是节假日吗：{test_result} ，近期{result}")

if __name__ == '__main__':
    main()