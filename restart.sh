#!/bin/bash
# restart.sh — единственная команда для безопасного рестарта бота.
# Убивает ВСЁ (run_forever.sh, bot.py, lock-файл), ждёт, запускает заново.
# Используй вместо ручного набора pkill/sleep/nohup — так не забудешь шаг.

cd ~/bybit_bot || exit 1

echo "Останавливаю старые процессы..."
pkill -9 -f "run_forever.sh" 2>/dev/null
pkill -9 -f "python3 bot.py" 2>/dev/null
rm -f /tmp/bybit_bot_run_forever.lock
sleep 2

echo "Проверка, что всё чисто:"
ps aux | grep -E "bot\.py|run_forever" | grep -v grep

echo "Запускаю заново..."
nohup ./run_forever.sh > run_forever.log 2>&1 & disown
sleep 3

echo "Последние строки лога:"
tail -10 run_forever.log