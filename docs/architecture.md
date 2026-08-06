# System Architecture: Market Analysis Agent

## 1. High-Level Architecture
The system follows a **Manager-Worker** pattern managed by the Hybrid-Orch Engine.

### A. Orchestrator (The Manager)
- Responsible for reading `project_status.json`.
- Decomposes the goal into Macro-steps and Micro-tasks.
- Dispatches `delegate_task` calls for parallel subagents.
- Aggregates results and updates the global state.

### B. Subagents (The Workers)
- **Fetcher Agent**: Handles asynchronous web requests and raw content extraction.
- **Analyzer Agent**: Performs LLM-based filtering and entity extraction.
- **Summarizer Agent**: Synthesizes analyzed data into a structured Markdown report.

## 2. Data Flow
1.  **User Input**: Target Topic (e.g., "AI Semiconductor Trends")
2.  **Orchestrator**: Identifies the current step (RESEARCH -> DATA_COLLECTION).
3.  **Parallel Execution**:
    - Orchestrator spawns $N$ **Fetcher Agents** (parallel).
    - Fetches $N$ different sources.
4.  **Sequential Processing**:
    - Fetched data flows to **Analyzer Agent** (can be parallelized per source).
    - Analyzed data flows to **Summarizer Agent**.
5.  **Completion**: Summarizer produces a report -> Orchestrator updates state to `completed`.

## 3. Component Interaction Diagram (Logical)
[User] -> [Orchestrator] <-> [State Store: project_status.json]
               |
               +-- (Delegate Task) --> [Fetcher Agent] x N
               |
               +-- (Delegate Task) --> [Analyzer Agent] x N
               |
               +-- (Delegate Task) --> [Summarizer Agent]
