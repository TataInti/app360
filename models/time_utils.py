from datetime import datetime, timedelta, timezone

LOCAL_TZ = timezone(timedelta(hours=-3))


def now_local():
    return datetime.now(LOCAL_TZ)


def today_local_date():
    return now_local().date()
