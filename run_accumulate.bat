@echo off
REM Trickle a small batch of high-elo games into the DB. Safe to run on a schedule.
REM Re-run adds only NEW games (deduped against the DB). Refresh the dev key in .env daily.
cd /d "C:\Users\Charles\Documents\Unnamed-league-project"
python tools\accumulate.py --tier MASTER --target 40 --pace 2.7 >> game\data\accumulate.log 2>&1
