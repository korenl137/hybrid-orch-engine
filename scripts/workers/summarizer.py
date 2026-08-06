import json
import sys
import os
from typing import List, Dict, Any

def generate_report(analysis_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    # Filter out non-relevant items
    relevant_results = [r for r in analysis_results if r.get("relevance_score", 0) > 0.5]
    
    if not relevant_results:
        return {
            "report_title": "No Relevant Information Found",
            "overall_summary": "No information meeting the relevance threshold was found in the collected sources.",
            "detailed_insights": [],
            "entities_list": [],
            "report_markdown": ""
        }

    # Extract and deduplicate entities
    entities = set()
    for r in relevant_results:
        entities.update(r.get("key_entities", []))
    
    # Simple aggregation of summaries
    summary_parts = [r.get("summary", "") for r in relevant_results]
    combined_summary = " ".join(summary_parts)
    
    # Generate Markdown
    report_md = f"# Market Analysis Report\n\n## Executive Summary\n{combined_summary}\n\n"
    report_md += "## Key Insights\n"
    for i, r in enumerate(relevant_results):
        report_md += f"### Insight {i+1}\n{r.get('summary')}\n\n"
    
    report_md += "## Key Entities\n"
    for entity in sorted(list(entities)):
        report_md += f"- {entity}\n"

    return {
        "report_title": "Market Trend Analysis",
        "overall_summary": combined_summary,
        "detailed_insights": [r.get("summary") for r in relevant_results],
        "entities_list": list(entities),
        "report_markdown": report_md
    }

if __name__ == "__main__":
    # Expecting a JSON list of Analysis_Results from stdin or argv
    input_data_str = sys.argv[1] if len(sys.argv) > 1 else "[]"
    try:
        analysis_results = json.loads(input_data_str)
        report = generate_report(analysis_results)
        print(json.dumps(report, indent=2))
    except Exception as e:
        print(json.dumps({"error": str(e)}, indent=2))
