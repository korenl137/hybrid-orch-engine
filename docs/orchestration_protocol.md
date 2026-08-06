# Hybrid-Orch Engine Orchestration Protocol

## 1. Overview
This protocol defines how the Hybrid-Orch Engine manages complex projects by combining **Stateful Orchestration** with **Hybrid Execution (Macro-Sequential + Micro-Parallel)**.

## 2. Core Components
- **State Store**: `state/project_status.json` (The Single Source of Truth)
- **Orchestrator**: The primary agent (Hermes) that interprets the state and decomposes goals.
- **Subagents**: Workers spawned via `delegate_task` to perform independent micro-tasks.

## 3. Operational Workflow
For every Macro-step, the Orchestrator must follow this cycle:

1.  **Observe**: Read `project_status.json` to identify the current `macro_step` and `results`.
2.  **Plan**: Analyze the current goal and decompose it into a list of `micro_tasks`.
3.  **Execute (Parallel)**: 
    - For independent tasks, use `delegate_task` with a batch of tasks.
    - For sequential tasks, execute them one by one, updating the state after each.
4.  **Consolidate**: Collect all results from subagents/tasks.
5.  **Update**: Write the consolidated results to `results` and mark the `macro_step` as `completed`.
6.  **Advance**: Move to the next `macro_step`.

## 4. State Transition Rules
- `pending` -> `in_progress`: When the Orchestrator starts planning/executing a macro-step.
- `in_progress` -> `completed`: Only after **all** micro-tasks for that step are successfully finished and results are persisted.
- `failed`: If a micro-task fails and cannot be recovered, mark the macro-step as failed and seek manual intervention.

## 5. Concurrency & Locking
- The Orchestrator must ensure it only advances the `step_index` when the current step's micro-tasks are 100% complete.
- Parallel tasks must be isolated; subagents should not modify the global `project_status.json` directly. They must return results to the Orchestrator.
