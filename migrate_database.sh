#!/bin/sh
export FLASK_APP=project:app;
flask db migrate;
flask db upgrade;