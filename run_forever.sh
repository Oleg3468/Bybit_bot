#!/bin/bash
# run_forever.sh — супервизор для bot.py с защитой от дублей процессов.
#
# Проблема, которую это решает: на UserLand процессы иногда не до конца
# умирают после pkill, и если запустить run_forever.sh второй раз поверх
# первого, оба bot.py одновременно долбят Telegram getUpdates и падают
# с "Conflict: terminated by other getUpdates request".
#
# Защита в две линии:
# 1. Lock-файл — если run_forever.sh уже жив (проверяем PID), новый
#    экземпляр сразу выходит вместо того, чтобы плодить дубль.
# 2. Перед стартом цикла принудительно убиваем любые "осиротевшие"
#    bot.py, которые могли остаться от прошлого раза.

LOCKFILE="/tmp/bybit_bot_run_forever.lock"

if [ -f "$LOCKFILE" ]; then
    OLD_PID=$(cat "$LOCKFILE" 2>/dev/null)
    if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
        echo "$(date): run_forever.sh уже запущен (PID $OLD_PID), выхожу без действий"
        exit 1
    fi
    echo "$(date): найден устаревший lock-файл (PID $OLD_PID не жив), перезаписываю"
fi
echo $$ > "$LOCKFILE"

# Подчищаем любые старые bot.py перед стартом — на случай если предыдущий
# run_forever.sh был убит через kill -9 и не успел прибрать за собой.
pkill -9 -f "python3 bot.py" 2>/dev/null
sleep 1

cleanup() {
    rm -f "$LOCKFILE"
    exit 0
}
trap cleanup INT TERM

while true; do
    echo "$(date): запуск bot.py"
    python3 bot.py
    echo "$(date): bot.py упал, перезапуск через 10 сек"
    sleep 10
done