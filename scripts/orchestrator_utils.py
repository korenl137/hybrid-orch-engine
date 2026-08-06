import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

PROJECT_ROOT = "/home/hermes/hybrid-orch-engine"
STATE_FILE = os.path.join(PROJECT_ROOT, "state", "project_status.json")

def load_state() -> Dict[str, Any]:
    """상태 파일을 읽어와 파이썬 딕셔너리로 반환합니다."""
    if not os.path.exists(STATE_FILE):
        # 초기 상태 파일이 없는 경우 기본값 생성
        initial_state = {
            "project_id": "hybrid-orch-001",
            "project_name": "Hybrid-Orch Engine Build",
            "current_step": "INITIALIZATION",
            "step_index": 0,
            "status": "in_progress",
            "macro_steps": [
                {"id": 0, "name": "INITIALIZATION", "description": "Environment setup and status schema definition", "status": "in_progress"},
                {"id": 1, "name": "RESEARCH", "description": "Data collection and target analysis", "status": "pending"},
                {"id": 2, "name": "DESIGN", "description": "Architecture and logic design", "status": "pending"},
                {"id": 3, "name": "IMPLEMENT", "description": "Core engine and subagent deployment", "status": "pending"}
            ],
            "micro_tasks": [],
            "results": {},
            "logs": []
        }
        save_state(initial_state)
        return initial_state
    
    with open(STATE_FILE, "r") as f:
        return json.load(f)

def save_state(state: Dict[str, Any]) -> None:
    """상태를 JSON 파일에 저장합니다."""
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

def update_step_status(step_name: str, status: str, result_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """특정 매크로 단계의 상태를 업데이트하고 결과를 저장합니다."""
    state = load_state()
    
    # 매크로 단계 상태 업데이트
    found = False
    for step in state["macro_steps"]:
        if step["name"] == step_name:
            step["status"] = status
            found = True
            break
    
    if not found:
        raise ValueError(f"Step '{step_name}' not found in macro_steps.")

    # 현재 진행 단계 업데이트 (만약 현재 단계가 완료되었다면 다음으로 넘기는 로직은 오케스트레이터가 담당)
    state["status"] = status
    
    if result_data:
        state["results"][step_name] = result_data
        
    # 로그 기록
    state["logs"].append({
        "timestamp": datetime.now().isoformat(),
        "step": step_name,
        "status": status,
        "result_summary": str(result_data)[:200] if result_data else ""
    })
    
    save_state(state)
    return state

def get_current_macro_step() -> Dict[str, Any]:
    """현재 진행 중인 매크로 단계의 정보를 가져옵니다."""
    state = load_state()
    for step in state["macro_steps"]:
        if step["status"] == "in_progress":
            return step
    return state["macro_steps"][0]
