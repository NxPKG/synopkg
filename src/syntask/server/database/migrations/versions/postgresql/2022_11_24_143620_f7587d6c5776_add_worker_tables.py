"""Add worker tables

Revision ID: f7587d6c5776
Revises: 5d526270ddb4
Create Date: 2022-11-24 14:36:20.350834

"""

import sqlalchemy as sa
from alembic import op

import syntask

# revision identifiers, used by Alembic.
revision = "f7587d6c5776"
down_revision = "5e4f924ff96c"
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "worker_pool",
        sa.Column(
            "id",
            syntask.server.utilities.database.UUID(),
            server_default=sa.text("(GEN_RANDOM_UUID())"),
            nullable=False,
        ),
        sa.Column(
            "created",
            syntask.server.utilities.database.Timestamp(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated",
            syntask.server.utilities.database.Timestamp(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("type", sa.String(), nullable=True),
        sa.Column(
            "base_job_template",
            syntask.server.utilities.database.JSON(),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("is_paused", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("concurrency_limit", sa.Integer(), nullable=True),
        sa.Column(
            "default_queue_id", syntask.server.utilities.database.UUID(), nullable=True
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_worker_pool")),
        sa.UniqueConstraint("name", name=op.f("uq_worker_pool__name")),
    )
    op.create_index(
        op.f("ix_worker_pool__updated"), "worker_pool", ["updated"], unique=False
    )
    op.create_index(op.f("ix_worker_pool__type"), "worker_pool", ["type"], unique=False)

    op.create_table(
        "worker",
        sa.Column(
            "id",
            syntask.server.utilities.database.UUID(),
            server_default=sa.text("(GEN_RANDOM_UUID())"),
            nullable=False,
        ),
        sa.Column(
            "created",
            syntask.server.utilities.database.Timestamp(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated",
            syntask.server.utilities.database.Timestamp(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column(
            "last_heartbeat_time",
            syntask.server.utilities.database.Timestamp(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "worker_pool_id", syntask.server.utilities.database.UUID(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["worker_pool_id"],
            ["worker_pool.id"],
            name=op.f("fk_worker__worker_pool_id__worker_pool"),
            ondelete="cascade",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_worker")),
        sa.UniqueConstraint(
            "worker_pool_id",
            "name",
            name=op.f("uq_worker__worker_pool_id_name"),
        ),
    )
    op.create_index(op.f("ix_worker__updated"), "worker", ["updated"], unique=False)
    op.create_index(
        op.f("ix_worker__worker_pool_id"),
        "worker",
        ["worker_pool_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_worker__worker_pool_id_last_heartbeat_time"),
        "worker",
        ["worker_pool_id", "last_heartbeat_time"],
        unique=False,
    )

    op.create_table(
        "worker_pool_queue",
        sa.Column(
            "id",
            syntask.server.utilities.database.UUID(),
            server_default=sa.text("(GEN_RANDOM_UUID())"),
            nullable=False,
        ),
        sa.Column(
            "created",
            syntask.server.utilities.database.Timestamp(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated",
            syntask.server.utilities.database.Timestamp(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("is_paused", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("concurrency_limit", sa.Integer(), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column(
            "worker_pool_id", syntask.server.utilities.database.UUID(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["worker_pool_id"],
            ["worker_pool.id"],
            name=op.f("fk_worker_pool_queue__worker_pool_id__worker_pool"),
            ondelete="cascade",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_worker_pool_queue")),
        sa.UniqueConstraint(
            "worker_pool_id",
            "name",
            name=op.f("uq_worker_pool_queue__worker_pool_id_name"),
        ),
    )
    op.create_index(
        op.f("ix_worker_pool_queue__updated"),
        "worker_pool_queue",
        ["updated"],
        unique=False,
    )
    op.create_index(
        op.f("ix_worker_pool_queue__worker_pool_id_priority"),
        "worker_pool_queue",
        ["worker_pool_id", "priority"],
        unique=False,
    )
    op.create_index(
        op.f("ix_worker_pool_queue__worker_pool_id"),
        "worker_pool_queue",
        ["worker_pool_id"],
        unique=False,
    )

    with op.batch_alter_table("worker_pool", schema=None) as batch_op:
        batch_op.create_foreign_key(
            batch_op.f("fk_worker_pool__default_queue_id__worker_pool_queue"),
            "worker_pool_queue",
            ["default_queue_id"],
            ["id"],
            ondelete="RESTRICT",
        )

    with op.batch_alter_table("deployment", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "worker_pool_queue_id",
                syntask.server.utilities.database.UUID(),
                nullable=True,
            )
        )
        batch_op.create_index(
            batch_op.f("ix_deployment__worker_pool_queue_id"),
            ["worker_pool_queue_id"],
            unique=False,
        )
        batch_op.create_foreign_key(
            batch_op.f("fk_deployment__worker_pool_queue_id__worker_pool_queue"),
            "worker_pool_queue",
            ["worker_pool_queue_id"],
            ["id"],
            ondelete="SET NULL",
        )
    with op.batch_alter_table("flow_run", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "worker_pool_queue_id",
                syntask.server.utilities.database.UUID(),
                nullable=True,
            )
        )
        batch_op.create_index(
            batch_op.f("ix_flow_run__worker_pool_queue_id"),
            ["worker_pool_queue_id"],
            unique=False,
        )
        batch_op.create_foreign_key(
            batch_op.f("fk_flow_run__worker_pool_queue_id__worker_pool_queue"),
            "worker_pool_queue",
            ["worker_pool_queue_id"],
            ["id"],
            ondelete="SET NULL",
        )

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table("deployment", schema=None) as batch_op:
        batch_op.drop_column("worker_pool_queue_id")
    with op.batch_alter_table("flow_run", schema=None) as batch_op:
        batch_op.drop_column("worker_pool_queue_id")
    with op.batch_alter_table("worker_pool", schema=None) as batch_op:
        batch_op.drop_constraint("fk_worker_pool__default_queue_id__worker_pool_queue")
    op.drop_table("worker_pool_queue")
    op.drop_table("worker")
    op.drop_table("worker_pool")
    # ### end Alembic commands ###
