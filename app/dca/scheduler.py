"""
scheduler.py - APScheduler integration for DCA recurring payments.
Manages job scheduling, persistence, and execution.
"""

import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.asyncio import AsyncIOExecutor
from apscheduler.triggers.cron import CronTrigger
from apscheduler.util import undefined

from app.db.database import sync_engine, async_session_factory
from app.dca.models import RecurringPayment, DCAStatus
from app.dca.executor import DCAExecutor

logger = logging.getLogger(__name__)


class DCAScheduler:
    """
    Manages DCA job scheduling using APScheduler.
    
    Features:
    - Persistent job storage in PostgreSQL
    - Automatic recovery from app restart
    - Timezone-aware execution
    - Async-safe operations
    """
    
    _instance: Optional["DCAScheduler"] = None
    _scheduler: Optional[AsyncIOScheduler] = None
    
    def __init__(self):
        self.executor = DCAExecutor()
        self._initialized = False
    
    @classmethod
    async def initialize(cls) -> "DCAScheduler":
        """Initialize the global scheduler instance."""
        if cls._instance is None:
            cls._instance = cls()
            await cls._instance._setup()
        return cls._instance
    
    @classmethod
    def get_instance(cls) -> "DCAScheduler":
        """Get the global scheduler instance."""
        if cls._instance is None:
            raise RuntimeError("DCAScheduler not initialized. Call initialize() first.")
        return cls._instance
    
    async def _setup(self):
        """Set up APScheduler with PostgreSQL job store."""
        try:
            # Create job store using synchronous engine
            job_store = SQLAlchemyJobStore(
                engine=sync_engine,
            )
            
            # Create scheduler
            self._scheduler = AsyncIOScheduler(
                jobstores={"default": job_store},
                executors={"default": AsyncIOExecutor()},
                job_defaults={"coalesce": True, "max_instances": 1},
                timezone="UTC",
            )
            
            # Start scheduler
            self._scheduler.start()
            logger.info("DCA Scheduler initialized and started")
            
            # Load existing jobs from database
            await self._load_existing_jobs()
            
            self._initialized = True
        
        except Exception as e:
            logger.error(f"Failed to initialize DCA Scheduler: {e}", exc_info=True)
            raise
    
    async def _load_existing_jobs(self):
        """Load all active recurring payments and reschedule them."""
        from sqlalchemy import select
        
        try:
            async with async_session_factory() as session:
                # Get all active recurring payments
                result = await session.execute(
                    select(RecurringPayment).where(
                        RecurringPayment.status == DCAStatus.ACTIVE.value
                    )
                )
                payments = result.scalars().all()
            
            logger.info(f"Loading {len(payments)} active recurring payments")
            
            for payment in payments:
                await self.schedule_job(payment)
        
        except Exception as e:
            logger.error(f"Failed to load existing jobs: {e}", exc_info=True)
    
    async def schedule_job(self, payment: RecurringPayment):
        """
        Schedule a recurring payment job.
        
        Args:
            payment: RecurringPayment model instance
        """
        if not self._scheduler:
            raise RuntimeError("Scheduler not initialized")
        
        try:
            job_id = f"dca_{payment.id}"
            
            # Remove existing job if present
            try:
                self._scheduler.remove_job(job_id)
            except:
                pass
            
            # Create cron trigger
            trigger = CronTrigger.from_crontab(
                payment.cron_expression,
                timezone="UTC"
            )
            
            # Add job
            self._scheduler.add_job(
                self.executor.execute_payment,
                trigger=trigger,
                id=job_id,
                name=f"DCA Payment {payment.id}",
                args=[payment.id],
                replace_existing=True,
                misfire_grace_time=3600,  # Allow 1 hour late execution
            )
            
            logger.info(
                f"Scheduled DCA job {job_id}: "
                f"${payment.amount} {payment.token_symbol} → {payment.recipient_address[:10]}... "
                f"(cron: {payment.cron_expression})"
            )
        
        except Exception as e:
            logger.error(f"Failed to schedule job for payment {payment.id}: {e}", exc_info=True)
            raise
    
    async def unschedule_job(self, payment_id: int):
        """
        Remove a recurring payment job from scheduler.
        
        Args:
            payment_id: ID of the recurring payment
        """
        if not self._scheduler:
            raise RuntimeError("Scheduler not initialized")
        
        try:
            job_id = f"dca_{payment_id}"
            self._scheduler.remove_job(job_id)
            logger.info(f"Unscheduled DCA job {job_id}")
        
        except Exception as e:
            logger.warning(f"Failed to unschedule job {payment_id}: {e}")
    
    async def pause_job(self, payment_id: int):
        """Pause a recurring payment job."""
        if not self._scheduler:
            raise RuntimeError("Scheduler not initialized")
        
        try:
            job_id = f"dca_{payment_id}"
            job = self._scheduler.get_job(job_id)
            if job:
                job.pause()
                logger.info(f"Paused DCA job {job_id}")
        
        except Exception as e:
            logger.warning(f"Failed to pause job {payment_id}: {e}")
    
    async def resume_job(self, payment_id: int):
        """Resume a paused recurring payment job."""
        if not self._scheduler:
            raise RuntimeError("Scheduler not initialized")
        
        try:
            job_id = f"dca_{payment_id}"
            job = self._scheduler.get_job(job_id)
            if job:
                job.resume()
                logger.info(f"Resumed DCA job {job_id}")
        
        except Exception as e:
            logger.warning(f"Failed to resume job {payment_id}: {e}")
    
    def get_job_status(self, payment_id: int) -> Optional[Dict[str, Any]]:
        """Get status of a scheduled job."""
        if not self._scheduler:
            return None
        
        try:
            job_id = f"dca_{payment_id}"
            job = self._scheduler.get_job(job_id)
            
            if not job:
                return None
            
            return {
                "id": job.id,
                "name": job.name,
                "next_run_time": job.next_run_time,
                "trigger": str(job.trigger),
                "state": "paused" if job._jobstore_alias == "paused" else "active",
            }
        
        except Exception as e:
            logger.warning(f"Failed to get job status for {payment_id}: {e}")
            return None
    
    async def shutdown(self):
        """Shutdown the scheduler gracefully."""
        if self._scheduler:
            self._scheduler.shutdown()
            logger.info("DCA Scheduler shut down")


# Global scheduler instance functions
async def get_dca_scheduler() -> DCAScheduler:
    """Get or initialize the DCA scheduler."""
    try:
        return DCAScheduler.get_instance()
    except RuntimeError:
        # Not initialized yet
        return await DCAScheduler.initialize()
