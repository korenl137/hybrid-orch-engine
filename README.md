# Hybrid-Orch Engine

A stateful, hybrid orchestration engine designed for autonomous agent infrastructure. This project implements a Manager+StateStore+Cron+Subagents workflow to handle complex, long-running tasks with high reliability.

## Features
- **Stateful Orchestration:** Maintains project status via a shared state file.
- **Hybrid Execution:** Sequential macro-steps with parallel micro-tasks.
- **Autonomous Agents:** Delegation of tasks to independent subagents.
- **Cron Integration:** Periodic monitoring and reporting for long-running tasks.

## Project Structure
- `docs/`: Architecture and design documentation.
- `scripts/`: Core engine logic and worker scripts.
- `state/`: Project status and scenario definitions.

## Installation
1. Clone the repository:
   ```bash
   git clone https://github.com/korenl137/hybrid-orch-engine.git
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
