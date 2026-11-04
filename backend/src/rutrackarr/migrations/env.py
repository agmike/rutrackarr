from alembic import context

from rutrackarr.db.models import Base

connection = context.config.attributes.get("connection")
if connection is None:  # pragma: no cover - only used via db.engine.migrate()
    raise RuntimeError("run migrations through rutrackarr.db.engine.migrate()")

context.configure(connection=connection, target_metadata=Base.metadata, render_as_batch=True)
with context.begin_transaction():
    context.run_migrations()
