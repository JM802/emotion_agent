from typing import Dict, Any, Optional

from agents.router_agent import RouterAgent
from agents.emotion_agent import EmotionAgent
from agents.sarcasm_agent import SarcasmAgent
from agents.mix_agent import MixAgent
from agents.judge_agent import JudgeAgent
from database.db import Database

class AgentPipeline:

    def __init__(self, db: Optional[Database] = None):
        self.router = RouterAgent()
        self.emotion = EmotionAgent()
        self.sarcasm = SarcasmAgent()
        self.mix = MixAgent()
        self.judge = JudgeAgent()
        self.db = db

    def _insert_raw(self, input_data: Dict[str, Any]) -> None:
        if not self.db:
            return
        try:
            self.db.insert_raw_text(input_data)
        except Exception as e:
            print(f"[pipeline] raw_text insert failed (non-fatal): {e}")

    def _insert_result(self, output: Dict[str, Any]) -> None:
        if not self.db:
            return
        try:
            self.db.insert_emotion_result(output)
        except Exception as e:
            print(f"[pipeline] emotion_result insert failed (non-fatal): {e}")

    @staticmethod
    def _build_output(input_data: Dict[str, Any],
                      router_result: Dict[str, Any],
                      emotion_result: Dict[str, Any],
                      judge_result: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": input_data["id"],
            "text": input_data["text"],
            "sample_type": router_result["sample_type"],
            "emotion": judge_result["final_emotion"],
            "secondary_emotion": judge_result.get("secondary_emotion"),
            "intensity": judge_result["final_intensity"],
            "final_confidence": judge_result["final_confidence"],
            "is_sarcasm": judge_result["is_sarcasm"],
            "is_mixed": judge_result["is_mixed"],
            "reason": judge_result["reason"],
            "tokens": emotion_result.get("tokens", []),
            "emotion_words": emotion_result.get("emotion_words", []),
            "source": input_data["source"],
            "created_at": input_data["created_at"],
        }

    def run(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        self._insert_raw(input_data)

        router_result = self.router.process(input_data)

        emotion_result = self.emotion.process(input_data)

        sarcasm_result = None
        mix_result = None

        if router_result.get("need_sarcasm_check"):
            sarcasm_result = self.sarcasm.process(input_data)

        if router_result.get("need_mix_check"):
            mix_result = self.mix.process(input_data)

        judge_result = self.judge.process(
            input_data, router_result, emotion_result,
            sarcasm_result, mix_result,
        )

        output = self._build_output(input_data, router_result, emotion_result, judge_result)

        self._insert_result(output)

        return output

   
