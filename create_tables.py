from project.server.models import *
from project import app, db

def create_tables():
	with app.app_context():
		db.create_all()

if __name__ == '__main__':
	create_tables()