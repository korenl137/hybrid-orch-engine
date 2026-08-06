# Hybrid-Orch Engine Tech Stack

## Core Environment
- **Language**: Python 3.11+
- **Package Manager**: uv (Fast, reproducible environments)
- **OS Environment**: WSL (Windows Subsystem for Linux)

## Core Libraries
- **Concurrency**: `asyncio` (I/O bound), `concurrent.futures` (CPU bound)
- **Data Processing**: `Polars` (High-performance data manipulation)
- **Data Validation**: `Pydantic` (Strict schema enforcement for JSON states)
- **LLM Orchestration**: Model-agnostic wrappers for local (Ollama/vLLM) and remote APIs.

## Reliability & Scalability Features
- **Atomic File Operations**: File locking for `project_status.json` updates.
- **Task Isolation**: Strict separation between Orchestrator and Subagents using `delegate_task`.
- **Retry Mechanism**: Standardized exponential backoff for all external calls.
- **Logging**: Structured JSON logs for auditing and debugging.
