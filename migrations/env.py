from alembic import context
from proofops.config import get_settings
from proofops.storage.database import Base, make_engine

config = context.config
target_metadata = Base.metadata

if context.is_offline_mode():
    context.configure(
        url=get_settings().database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()
else:

    def run_migrations(connection):
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()

    connection = config.attributes.get("connection")
    if connection is not None:
        run_migrations(connection)
    else:
        with make_engine().connect() as connection:
            run_migrations(connection)
