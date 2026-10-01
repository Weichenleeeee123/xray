from datetime import date


def money(n: float) -> str:
    """¥5,000 万 / ¥40,000 / ¥0"""
    if n >= 10000 and n % 10000 == 0:
        return f"¥{n / 10000:,.0f} 万"
    return f"¥{n:,.0f}"


def wan(n: float) -> str:
    """5000 万 / 4 万 / 800 元"""
    if n >= 10000:
        return f"{n / 10000:g} 万"
    return f"{n:,.0f} 元"


def months_between(start: str, end: date) -> int:
    s = date.fromisoformat(start)
    return (end.year - s.year) * 12 + (end.month - s.month) - (1 if end.day < s.day else 0)
