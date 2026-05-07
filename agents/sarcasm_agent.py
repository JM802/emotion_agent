import json
import re
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from llm_server import get_llm_server, LLMServer

@dataclass
class InputMessage:
    id: str
    user_id: str
    text: str
    source: str
    created_at: str

@dataclass
class SarcasmOutput:
    is_sarcasm: bool
    surface_emotion: str
    true_emotion: str
    revised_intensity: int
    sarcasm_confidence: float
    reason: str

class SarcasmAgent:

    # 正向情绪词
    POSITIVE_WORDS = {
        "太好了", "真棒", "开心", "高兴", "幸福", "兴奋", "激动",
        "满意", "期待", "喜欢", "爱", "感动", "庆幸", "幸运",
        "不错", "完美", "精彩", "优秀", "厉害", "爽", "nice", "棒",
        "真不错", "好极了", "可以", "感恩", "谢谢你", "多谢",
    }

    # 典型反讽触发词
    SARCASM_TRIGGERS = {
        "又", "还真是", "真棒", "太好了", "好极了", "真不错",
        "可真行", "服了", "呵呵", "有意思", "真是太", "还能这样",
        "不愧是你", "谢谢你啊", "多谢了", "感激不尽", "感恩",
        "可真是", "可以可以", "牛",
    }

    # 负向场景词
    NEGATIVE_SCENARIOS = {
        "加班", "开会", "改需求", "延期", "熬夜", "通宵",
        "bug", "故障", "投诉", "扣钱", "裁员", "加班到",
        "周末", "凌晨", "年底", "汇报", "考核", "出问题",
        "崩溃", "挂了", "宕机", "背锅", "填坑",
    }

    SYSTEM_PROMPT = """你是一个反讽识别专家。请严格按照JSON格式输出分析结果，不要输出markdown代码块，不要包含额外解释。

    输出字段说明：
    - is_sarcasm: 布尔值，是否反讽
    - surface_emotion: 表层情绪（句子字面表达的情绪），从「开心、悲伤、愤怒、焦虑、厌烦、中性」中选择
    - true_emotion: 真实情绪（实际传达的情绪），从「开心、悲伤、愤怒、焦虑、厌烦、中性」中选择
    - revised_intensity: 修正后的情绪强度，0-100的整数
    - sarcasm_confidence: 反讽识别的置信度，0-1之间的小数
    - reason: 一句话说明判断依据，不超过50字"""

    def __init__(self, llm: Optional[LLMServer] = None):
        self.llm = llm or get_llm_server()

    def _has_rule_hints(self, text: str) -> Dict[str, Any]:
        triggers = [t for t in self.SARCASM_TRIGGERS if t in text]
        positive_words = [w for w in self.POSITIVE_WORDS if w in text]
        negative_scenarios = [s for s in self.NEGATIVE_SCENARIOS if s in text]

        return {
            "has_triggers": len(triggers) > 0,
            "triggers": triggers,
            "positive_words": positive_words,
            "negative_scenarios": negative_scenarios,
            "rule_hint_score": len(triggers) * 2 + len(negative_scenarios),
        }

    def _call_llm(self, text: str, rule_hints: Dict) -> Dict[str, Any]:
        prompt = f"""句子："{text}"

        规则线索：{json.dumps(rule_hints, ensure_ascii=False)}

        请判断该句子是否使用了反讽修辞，并输出JSON格式的分析结果。"""
        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
        content = self.llm.chat(messages, temperature=0.1)
        match = re.search(r'\{.*\}', content, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        return {}

    def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        msg = InputMessage(**input_data)
        rule_hints = self._has_rule_hints(msg.text)
        llm_result = self._call_llm(msg.text, rule_hints)

        return {
            "is_sarcasm": llm_result.get("is_sarcasm", False),
            "surface_emotion": llm_result.get("surface_emotion", "中性"),
            "true_emotion": llm_result.get("true_emotion", "中性"),
            "revised_intensity": llm_result.get("revised_intensity", 50),
            "sarcasm_confidence": llm_result.get("sarcasm_confidence", 0.5),
            "reason": llm_result.get("reason", ""),
        }
