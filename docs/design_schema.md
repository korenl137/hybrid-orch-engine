# System Design: Data Schema & Subagent Roles

## 1. Data Schema Definitions

### 1.1 Data Collection Schema
```json
{
  "source_url": "string",
  "raw_content": "string",
  "title": "string",
  "timestamp": "ISO8601_datetime"
}
```

### 1.2 Analysis Schema
```json
{
  "source_url": "string",
  "key_entities": ["entity1", "entity2"],
  "summary": "string",
  "relevance_score": 0.0,
  "extracted_data": {}
}
```

### 1.3 Final Report Schema
```json
{
  "report_title": "string",
  "overall_summary": "string",
  "detailed_insights": ["insight1", "insight2"],
  "entities_list": ["entity1", "entity2"],
  "report_markdown": "string"
}
```

## 2. Subagent Roles

### 2.1 Fetcher Agent
- **Role**: Data Acquisition Worker.
- **Responsibility**: Fetch HTML content from URLs and clean/extract body text.
- **Success Criteria**: Returns a valid `Data_Collection_Results` object for every provided URL.

### 2.2 Analyzer Agent
- **Role**: Intelligence & Filtering Worker.
- **Responsibility**: Analyze content for relevance to the target topic and extract key entities.
- **Success Criteria**: Returns a valid `Analysis_Results` object with a relevance score > 0.5.

### 2.3 Summarizer Agent
- **Role**: Synthesis & Reporting Worker.
- **Responsibility**: Aggregate all `Analysis_Results`, remove duplicates, and generate a structured Markdown report.
- **Success Criteria**: Produces a coherent, structured Markdown report in `report_markdown` field.
