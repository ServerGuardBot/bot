FROM python:3.9-slim

# Installing packages
RUN pip install --no-cache-dir pipenv

# Defining working directory and adding source code
RUN mkdir -p /usr/src/app
WORKDIR /usr/src/app
COPY Pipfile Pipfile.lock bootstrap.sh migrate_database.sh create_tables.py ./
COPY project ./project

# Install API dependencies
RUN pipenv install --deploy --ignore-pipfile

# Start app
EXPOSE 5000
ENTRYPOINT ["/usr/src/app/bootstrap.sh"]