import os
import json
import logging
import subprocess
from typing import List, Dict, Any
from scripts.orchestrator_utils import load_state, save_state, update_step_status

# Logging Setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("Hybrid-Orch-Engine")

class HybridOrchEngine:
    def __init__(self, project_root: str):
        self.project_root = project_root
        self.state = load_state()
        self.logger = logger

    def get_current_step_info(self) -> Dict[str, Any]:
        for step in self.state["macro_steps"]:
            if step["status"] == "in_progress":
                return step
        return self.state["macro_steps"][0]

    def run_orchestration(self):
        self.logger.info(f"Starting orchestration for: {self.state['project_name']}")
        
        while self.state["status"] != "completed":
            current_step = self.get_current_step_info()
            step_name = current_step["name"]
            
            self.logger.info(f"--- Executing Macro-step: {step_name} ---")
            
            if step_name == "INITIALIZATION":
                self._handle_initialization()
            elif step_name == "RESEARCH":
                self._handle_research()
            elif step_name == "DESIGN":
                self._handle_design()
            elif step_name == "IMPLEMENT":
                self._handle_implementation()
            else:
                self.logger.error(f"Unknown step: {step_name}")
                break
            
            if current_step["status"] == "completed":
                self.logger.info(f"Completed macro-step: {step_name}")
                self._advance_step()

    def _handle_initialization(self):
        update_step_status("INITIALIZATION", "completed", {"verification": "success"})

    def _handle_research(self):
        target_topic = "AI Semiconductors Market Trends"
        urls = [
            "https://example.com/news1",
            "https://example.com/market-report-alpha",
            "https://example.com/tech-blog-beta"
        ]
        
        # 1. Parallel Data Collection
        self.logger.info(f"Phase 1: Collecting data from {len(urls)} sources...")
        raw_data_list = []
        for url in urls:
            result = self.run_worker("scripts/workers/fetcher.py", json.dumps([url]))
            raw_data_list.append(result)
        
        # 2. Analysis
        self.logger.info("Phase 2: Analyzing collected content...")
        analysis_results = []
        for data in raw_data_list:
            if "Error" not in data.get("raw_content", ""):
                res = self.run_worker("scripts/workers/analyzer.py", json.dumps(data))
                analysis_results.append(res)
        
        # 3. Summarization
        self.logger.info("Phase 3: Generating final summary report...")
        final_report = self.run_worker("scripts/workers/summarizer.py", json.dumps(analysis_results))
        
        update_step_status("RESEARCH", "completed", {
            "target_topic": target_topic,
            "final_report": final_report,
            "sources_processed": len(raw_data_list)
        })

    def _handle_design(self):
        update_step_status("DESIGN", "completed", {"status": "Architecture & Schema Defined"})

    def _handle_implementation(self):
        self.logger.info("Implementation phase active.")
        pass

    def run_worker(self, script_path: str, input_data: str) -> Dict[str, Any]:
        full_path = os.path.join(self.project_root, script_path)
        try:
            result = subprocess.run(
                ["python3", full_path, input_data],
                capture_output=True,
                text=True,
                check=True
            )
            return json.loads(result.stdout)
        except Exception as e:
            self.logger.error(f"Worker {script_path} failed: {str(e)}")
            return {"error": str(e)}

    def _advance_step(self):
        for step in self.state["macro_steps"]:
            if step["status"] == "pending":
                step["status"] = "in_progress"
                break
        save_state(self.state)

if __name__ == "__main__":
    engine = HybridOrchEngine("/home/hermes/hybrid-orch-engine")
    engine.run_orchestration()
