"""Database-backed, in-process Analysis Job dispatcher."""

from __future__ import annotations

import json
import inspect
from datetime import datetime

from bap_common.analysis_contracts import ContractError
from bap_backend.app.repositories import AnalysisSessionRepository
from bap_backend.app.services.analysis_registry import AnalysisInputDescriptor, AnalysisRegistry


class AnalysisDispatcher:
    def __init__(self, session_factory, registry: AnalysisRegistry, *, clock=datetime.utcnow) -> None:
        self.session_factory = session_factory
        self.registry = registry
        self.clock = clock

    def recover(self) -> int:
        try:
            with self.session_factory() as session:
                count = AnalysisSessionRepository(session).recover_processing()
                session.commit()
                return count
        except Exception:
            # Startup recovery is best-effort. The /health endpoint remains the
            # authoritative readiness signal when the Database is unavailable.
            return 0

    def dispatch_pending(self) -> int:
        completed = 0
        with self.session_factory() as session:
            repository = AnalysisSessionRepository(session)
            for job in repository.pending_jobs():
                if not repository.claim(job, self.clock()):
                    continue
                try:
                    specification = self.registry.specification(job.analysis_type, job.spec_version)
                    executor = self.registry.executor(job.analysis_type, job.spec_version)
                    if executor is None:
                        raise ContractError("executor_unavailable", "此分析功能尚未提供")
                    inputs = {
                        binding.input_role: binding.csv_file.csv_blob
                        for binding in job.input_bindings
                    }
                    arguments = {
                        "inputs": inputs,
                        "parameters": json.loads(job.parameters_json),
                    }
                    # Older executors and injected test doubles keep the original
                    # two-argument interface.  Descriptor-aware analyses opt in
                    # explicitly so existing analyses remain compatible.
                    if "input_descriptors" in inspect.signature(executor.execute).parameters:
                        arguments["input_descriptors"] = {
                            binding.input_role: AnalysisInputDescriptor(
                                csv_id=binding.csv_file.id,
                                source_id=binding.csv_file.source_id,
                                port=binding.csv_file.port,
                                connection_type=binding.csv_file.connection_type,
                                baud_rate=binding.csv_file.baud_rate,
                                group_id=binding.csv_file.group_id,
                                node_id=binding.csv_file.node_id,
                            )
                            for binding in job.input_bindings
                        }
                    result = executor.execute(**arguments)
                    specification.validate_result(result)
                    repository.save_result(job, result, self.clock())
                    completed += 1
                except ContractError as error:
                    job.status = "failed"
                    job.error_code = error.code
                    job.safe_error_message = error.message
                    job.completed_at = self.clock()
                except Exception:
                    job.status = "failed"
                    job.error_code = "analysis_failed"
                    job.safe_error_message = "分析過程發生錯誤，請稍後重試"
                    job.completed_at = self.clock()
                session.commit()
        return completed
