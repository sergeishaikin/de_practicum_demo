from superset.app import create_app
from superset.models.slice import Slice
from superset.models.dashboard import Dashboard
from superset.models.core import Database
from superset.connectors.sqla.models import SqlaTable

app = create_app()

print("Slice columns:", Slice.__table__.columns.keys())
print("Dashboard columns:", Dashboard.__table__.columns.keys())
print("Database columns:", Database.__table__.columns.keys())
print("SqlaTable columns:", SqlaTable.__table__.columns.keys())
