def sci_line():
    return "━━━━━━━━━━━━━━━━━━━━"


def format_status(status):
    return {
        "pending": "⏳ ОЖИДАЕТ ВЕРИФИКАЦИИ",
        "approved": "🟢 ВЕРИФИЦИРОВАН",
        "rejected": "🔴 ОТКЛОНЁН"
    }.get(status, status)


def format_salary_cooldown(seconds_left):
    days = seconds_left // 86400
    hours = (seconds_left % 86400) // 3600
    minutes = (seconds_left % 3600) // 60

    if days > 0:
        return f"{days} дн. {hours} ч."
    if hours > 0:
        return f"{hours} ч. {minutes} мин."
    return f"{minutes} мин."
