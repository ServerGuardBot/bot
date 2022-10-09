#!/bin/sh
export FLASK_APP=project:app
gunicorn --chdir project project:app -w 2 --threads 2 -b 0.0.0.0:5000