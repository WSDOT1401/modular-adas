#!/usr/bin/env bash
# On the Pi: the ADAS display on the round screen, the vision service (sign_v3
# on the AI HAT) and the stats server. The stats window itself runs on another
# machine (a Mac beside the car):
#   python3 adas/vision/tools/stats_window.py --pi <this Pi's address> --windowed
# GPS and the rotary encoder are user services of their own (adas-gps, adas-encoder).
#
#   bash ~/modular-adas/adas/tools/pi_start.sh          # the camera
#   bash ~/modular-adas/adas/tools/pi_start.sh CLIP     # a clip on loop instead
#
# Logs: /tmp/display.log, /tmp/stats.log, /tmp/cam.log
# The [.] and [r] keep each pattern from matching the shell running this script.
pkill -f "main[.]py" ; pkill -f "stats_windo[w]" ; pkill -f "stats_serve[r]" ; pkill -x adas_display ; sleep 1
export XDG_RUNTIME_DIR=/run/user/1000 WAYLAND_DISPLAY=wayland-0
cd ~/modular-adas/adas/display
QT_QPA_PLATFORM=wayland setsid nohup ./build/adas_display --screen auto > /tmp/display.log 2>&1 < /dev/null &
sleep 3
cd ~/modular-adas/adas/vision
setsid nohup ~/adas-venv/bin/python -u tools/stats_server.py > /tmp/stats.log 2>&1 < /dev/null &
if [ -n "$1" ]; then SRC="--source file --clip $1 --loop"; else SRC="--source camera"; fi
setsid nohup ~/adas-venv/bin/python -u main.py $SRC --signs v3 > /tmp/cam.log 2>&1 < /dev/null &
sleep 1
pgrep -af "adas_display|stats_serve[r]|main[.]py"
