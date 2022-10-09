#!/bin/sh
export FLASK_APP=project:app;
flask db init;
flask db migrate -m "Initial Migration.";
flask db upgrade;