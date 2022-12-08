#!/bin/sh
export FLASK_APP=project:app;
export MIGRATING_DB="1";
flask db migrate;
flask db upgrade;