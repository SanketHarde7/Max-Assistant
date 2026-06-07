# workflow_engine.py — Replay saved multi-step workflows for AI Orchestrator
import os
import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("MAX.ORCHESTRATOR.WORKFLOW")

class WorkflowEngine:
    def __init__(self, orchestrator):
        self.orchestrator = orchestrator
        self.config = orchestrator.config
        self.workflow_file = Path(self.config.DATA_DIR) / "ai_workflows.json"
        self._ensure_file_exists()

    def _ensure_file_exists(self):
        if not self.workflow_file.exists():
            try:
                self.workflow_file.parent.mkdir(parents=True, exist_ok=True)
                self.workflow_file.write_text(json.dumps({
                    "morning_research": [
                        { "platform": "perplexity", "action": "ask", "query": "today's top technology news developments" },
                        { "platform": "claude", "action": "summarize_previous", "instructions": "summarize into 5 bullet points with key insights" },
                        { "action": "save_file", "filename": "morning_brief_{date}.txt" }
                    ]
                }, indent=2))
            except Exception as e:
                logger.error(f"Failed to create default workflow file: {e}")

    def load_workflows(self) -> dict:
        try:
            if self.workflow_file.exists():
                return json.loads(self.workflow_file.read_text())
        except Exception as e:
            logger.error(f"Failed to load workflows: {e}")
        return {}

    def save_workflows(self, workflows: dict):
        try:
            self.workflow_file.write_text(json.dumps(workflows, indent=2))
            return True
        except Exception as e:
            logger.error(f"Failed to save workflows: {e}")
            return False

    def save_workflow(self, name: str, steps: list) -> bool:
        workflows = self.load_workflows()
        workflows[name.strip().lower()] = steps
        return self.save_workflows(workflows)

    def delete_workflow(self, name: str) -> bool:
        workflows = self.load_workflows()
        key = name.strip().lower()
        if key in workflows:
            del workflows[key]
            self.save_workflows(workflows)
            return True
        return False

    async def run_workflow(self, name: str) -> str:
        workflows = self.load_workflows()
        key = name.strip().lower()
        if key not in workflows:
            return f"Workflow '{name}' not found."

        steps = workflows[key]
        logger.info(f"Running workflow: '{name}' ({len(steps)} steps)")

        previous_response = ""
        logs = []

        for idx, step in enumerate(steps, 1):
            action = step.get("action", "ask").lower()
            logger.info(f"Executing step {idx}/{len(steps)}: {action}")

            if action == "ask":
                platform = step.get("platform")
                query = step.get("query")
                if not platform or not query:
                    return f"Step {idx} error: platform and query are required for 'ask' action."
                
                resp = await self.orchestrator.ask_ai(platform, query)
                previous_response = resp
                logs.append(f"Step {idx}: Queried {platform} -> Received {len(resp)} chars")

            elif action == "summarize_previous":
                platform = step.get("platform")
                instructions = step.get("instructions", "")
                if not platform:
                    return f"Step {idx} error: platform is required for 'summarize_previous' action."
                
                prompt = f"Please summarize the following text:\n\n{previous_response}\n\nInstructions: {instructions}"
                resp = await self.orchestrator.ask_ai(platform, prompt)
                previous_response = resp
                logs.append(f"Step {idx}: Summarized via {platform} -> Received {len(resp)} chars")

            elif action == "save_file":
                filename_template = step.get("filename", "workflow_output_{date}.txt")
                date_str = datetime.now().strftime("%Y-%m-%d")
                filename = filename_template.replace("{date}", date_str)
                
                save_path = Path(self.config.WORKSPACE_DIR) / filename
                try:
                    save_path.parent.mkdir(parents=True, exist_ok=True)
                    save_path.write_text(previous_response, encoding="utf-8")
                    logs.append(f"Step {idx}: Saved result to file {save_path.name}")
                except Exception as e:
                    return f"Step {idx} error: Failed to save file {filename}: {e}"

            else:
                return f"Step {idx} error: Unknown action '{action}'"

        return f"Workflow '{name}' completed successfully!\n" + "\n".join(logs)
