# Project Requirements: Intelligent Market Analysis Agent

## 1. Goal
Build a system that automatically collects, analyzes, and summarizes market trends from multiple sources (news, blogs, SNS) using a hybrid orchestration engine.

## 2. Functional Requirements
### 2.1 Data Acquisition
- **Asynchronous Fetching**: Support multiple concurrent requests to various web sources.
- **Content Extraction**: Extract main text from URLs, handling different web layouts.
- **Large-scale Processing**: Efficiently handle large volumes of raw text using `Polars`.

### 2.2 Intelligence & Analysis
- **Topic Filtering**: Use LLMs to identify and filter content relevant to the user's target topic.
- **Entity Extraction**: Extract key information (Companies, Technologies, Figures, Dates).
- **De-duplication**: Identify and merge overlapping information from different sources.

### 2.3 Orchestration & State
- **State Tracking**: Real-time tracking of project progress via `project_status.json`.
- **Parallel Execution**: Orchestrate independent data collection tasks in parallel.
- **Result Consolidation**: Aggregate results from multiple subagents into a single coherent summary.

### 2.4 Reporting
- **Structured Output**: Generate Markdown reports with clear sections (Summary, Key Insights, Entities).
- **Distribution**: (Future) Support for automated Telegram notifications.
