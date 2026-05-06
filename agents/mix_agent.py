import json
import re
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from llm_server import get_llm_server, LLMServer


@dataclass
class InputMessage:
    id: str
    user_id: str
    text: str
    source: str
    created_at: str


@dataclass
class MixOutput:
    is_mixed: bool
    primary_emotion: str
    secondary_emotion: Optional[str]
    mix_ratio: Dict[str, float]
    revised_intensity: int
    confidence: float
    reason: str


class MixAgent:

    # 正向词
    POSITIVE_WORDS = {
        "太好了", "真棒", "开心", "高兴", "幸福", "兴奋", "激动",
        "满意", "期待", "喜欢", "爱", "感动", "庆幸", "幸运",
        "不错", "完美", "精彩", "优秀", "厉害", "爽", "棒", "轻松",
    }

    # 负向词
    NEGATIVE_WORDS = {
        "难过", "伤心", "痛苦", "焦虑", "烦躁", "愤怒", "生气",
        "失望", "无奈", "崩溃", "累", "疲惫", "郁闷", "压抑",
        "讨厌", "恨", "烦", "惨", "糟糕", "烂", "难受", "失落",
        "空虚", "空", "堵", "慌",
    }

    # 转折词
    TRANSITION_WORDS = {
        "但是", "可是", "不过", "然而", "虽然", "只是",
        "但", "却", "却也", "也挺", "但还是", "就是",
    }

    # 低能量/压抑表达模式
    LOW_ENERGY_PATTERNS = [
        r"提不[起上]劲",
        r"不知道怎么",
        r"说不出",
        r"堵得慌",
        r"空落落",
        r"不算.{1,3}但",
        r"说不上来",
        r"有点.{1,2}但又",
        r"就是.{1,3}得慌",
        r"也好",
        r"也行",
        r"随便吧",
        r"算了",
        r"麻了",
        r"无所谓",
        r"没所谓",
    ]

    SYSTEM_PROMPT = """你是一个混合情绪识别专家。请严格按照JSON格式输出分析结果，不要输出markdown代码块，不要包含额外解释。

输出字段说明：
- is_mixed: 布尔值，是否存在混合/复杂/模糊情绪
- primary_emotion: 主情绪，从「开心、悲伤、愤怒、焦虑、厌烦、中性」中选择
- secondary_emotion: 次情绪，可为null
- mix_ratio: 主次情绪的比例字典，如{"疲惫": 0.6, "开心": 0.4}
- revised_intensity: 情绪强度，0-100的整数
- confidence: 置信度，0-1之间的小数
- reason: 一句话说明判断依据，不超过50字"""

    def __init__(self, llm: Optional[LLMServer] = None):
        self.llm = llm or get_llm_server()

    def _has_rule_hints(self, text: str) -> Dict[str, Any]:
        transitions = [t for t in self.TRANSITION_WORDS if t in text]
        positive_words = [w for w in self.POSITIVE_WORDS if w in text]
        negative_words = [w for w in self.NEGATIVE_WORDS if w in text]
        low_energy_matches = []
        for p in self.LOW_ENERGY_PATTERNS:
            m = re.search(p, text)
            if m:
                low_energy_matches.append(m.group())

        return {
            "has_transitions": len(transitions) > 0,
            "transitions": transitions,
            "positive_words": positive_words,
            "negative_words": negative_words,
            "has_polarity_conflict": len(positive_words) > 0 and len(negative_words) > 0,
            "low_energy_matches": low_energy_matches,
        }

    def _call_llm(self, text: str, rule_hints: Dict) -> Dict[str, Any]:
        prompt = f"""句子："{text}"

规则线索：{json.dumps(rule_hints, ensure_ascii=False)}

请判断该句子是否包含混合或复杂情绪，并输出JSON格式的分析结果。"""
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
            "is_mixed": llm_result.get("is_mixed", False),
            "primary_emotion": llm_result.get("primary_emotion", "中性"),
            "secondary_emotion": llm_result.get("secondary_emotion"),
            "mix_ratio": llm_result.get("mix_ratio", {}),
            "revised_intensity": llm_result.get("revised_intensity", 50),
            "confidence": llm_result.get("confidence", 0.5),
            "reason": llm_result.get("reason", ""),
        }
