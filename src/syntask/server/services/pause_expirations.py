"""
The FailExpiredPauses service. Responsible for putting Paused flow runs in a Failed state if they are not resumed on time.
"""

import asyncio
from typing import Optional

import pendulum
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

import syntask.server.models as models
from syntask.server.database.dependencies import inject_db
from syntask.server.database.interface import SyntaskDBInterface
from syntask.server.schemas import states
from syntask.server.services.loop_service import LoopService
from syntask.settings import SYNTASK_API_SERVICES_PAUSE_EXPIRATIONS_LOOP_SECONDS


class FailExpiredPauses(LoopService):
    """
    A simple loop service responsible for identifying Paused flow runs that no longer can be resumed.
    """

    def __init__(self, loop_seconds: Optional[float] = None, **kwargs):
        super().__init__(
            loop_seconds=loop_seconds
            or SYNTASK_API_SERVICES_PAUSE_EXPIRATIONS_LOOP_SECONDS.value(),
            **kwargs,
        )

        # query for this many runs to mark failed at once
        self.batch_size = 200

    @inject_db
    async def run_once(self, db: SyntaskDBInterface):
        """
        Mark flow runs as failed by:

        - Querying for flow runs in a Paused state that have timed out
        - For any runs past the "expiration" threshold, setting the flow run state to a new `Failed` state
        """
        while True:
            async with db.session_context(begin_transaction=True) as session:
                query = (
                    sa.select(db.FlowRun)
                    .where(
                        db.FlowRun.state_type == states.StateType.PAUSED,
                    )
                    .limit(self.batch_size)
                )

                result = await session.execute(query)
                runs = result.scalars().all()

                # mark each run as failed
                for run in runs:
                    await self._mark_flow_run_as_failed(session=session, flow_run=run)

                # if no runs were found, exit the loop
                if len(runs) < self.batch_size:
                    break

        self.logger.info("Finished monitoring for late runs.")

    async def _mark_flow_run_as_failed(
        self, session: AsyncSession, flow_run: SyntaskDBInterface.FlowRun
    ) -> None:
        """
        Mark a flow run as failed.

        Pass-through method for overrides.
        """
        if flow_run.state.state_details.pause_timeout < pendulum.now("UTC"):
            await models.flow_runs.set_flow_run_state(
                session=session,
                flow_run_id=flow_run.id,
                state=states.Failed(message="The flow was paused and never resumed."),
                force=True,
            )


if __name__ == "__main__":
    asyncio.run(FailExpiredPauses(handle_signals=True).start())
