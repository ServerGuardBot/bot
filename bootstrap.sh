#!/bin/sh
export FLASK_APP=project
export PYTHONPATH=".:/root/serverguard"
killall gunicorn
pip install guilded.py --upgrade
gunicorn project:app -w 2 --threads 2 --pythonpath /root/serverguard -c /root/serverguard/project/gunicorn_config.py -b 0.0.0.0:5000 -error-logfile=/root/serverguard/gunicorn-error.log --access-logfile=/root/serverguard/gunicorn-access.log
