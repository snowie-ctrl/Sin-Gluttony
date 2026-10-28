#!/usr/bin/env bash
# Starts the Gluttony scraper and its control API in one tmux session.
#   ./run.sh                     start (does nothing if already running)
#   tmux attach -t gluttony      watch it; Ctrl-b d leaves it running
#   tmux kill-session -t gluttony
cd "$(dirname "$0")" || exit 1
SESSION=gluttony
if tmux has-session -t "$SESSION" 2>/dev/null; then
    echo "already running - tmux attach -t $SESSION"
    exit 0
fi
mkdir -p logs
# -u: the output is piped to tee, and without it logs/scraper.log stays empty for minutes.
tmux new-session -d -x 200 -y 50 -s "$SESSION" -n scraper ".venv/bin/python -u main.py 2>&1 | tee -a logs/scraper.log; echo; read -rp 'scraper exited - press Enter to close'"
tmux new-window -t "$SESSION" -n control ".venv/bin/python controlApi.py; echo; read -rp 'control API exited - press Enter to close'"
echo "started - tmux attach -t $SESSION"
