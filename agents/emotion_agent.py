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
class EmotionOutput:
    tokens: List[str]
    emotion_words: List[str]
    degree_words: List[str]
    negation_words: List[str]
    contrast_words: List[str]
    emotion: str
    intensity: int
    confidence: float
    reason: str


class EmotionAgent:

    # 各情绪类别词表
    EMOTION_WORDS = {
        "开心": {"开心", "高兴", "幸福", "兴奋", "激动", "快乐", "爽", "棒",
                 "不错", "满意", "喜欢", "爱", "感动", "庆幸", "幸运", "nice",
                 "完美", "精彩", "优秀", "厉害", "期待", "满足", "欣慰", "喜悦", "嗨"},
        "悲伤": {"难过", "伤心", "痛苦", "悲伤", "失落", "沮丧", "忧郁",
                 "心酸", "绝望", "消沉", "伤感", "悲哀", "想哭", "低沉", "心碎"},
        "愤怒": {"愤怒", "生气", "火大", "恼火", "气愤", "怒", "暴躁",
                 "忍不了", "受不了", "气死", "抓狂", "炸了", "气人", "真气"},
        "焦虑": {"焦虑", "紧张", "担心", "不安", "慌", "着急", "焦急",
                 "惶恐", "失眠", "压力大", "喘不过气", "心神不宁", "坐立不安", "怕", "恐惧"},
        "厌烦": {"厌烦", "烦", "无聊", "厌倦", "腻", "枯燥", "乏味",
                 "没意思", "没劲", "讨厌", "烦人", "累", "疲惫", "麻了", "摆烂", "算了", "随便吧"},
    }

    # 程度词
    DEGREE_WORDS = {"很", "非常", "特别", "太", "极其", "十分", "超级",
                    "有点", "比较", "稍微", "略微", "有些", "挺", "最", "极",
                    "格外", "多么", "好", "可", "过于"}

    # 否定词
    NEGATION_WORDS = {"不", "没", "别", "不要", "没有", "不会", "不是", "不太", "不怎么"}

    # 转折词
    CONTRAST_WORDS = {"但是", "可是", "不过", "然而", "虽然", "只是", "但", "却", "却也", "但还是"}

    SYSTEM_PROMPT = """你是一个情绪分析专家。请严格按照JSON格式输出分析结果，不要输出markdown代码块，不要包含额外解释。

输出字段说明：
- tokens: 对句子做短语级切分得到的列表
- emotion_words: 从tokens中筛选出的情绪词
- degree_words: 程度副词列表（如：很、非常、有点）
- negation_words: 否定词列表（如：不、没）
- contrast_words: 转折词列表（如：但是、不过）
- emotion: 主情绪类别，只能从「开心、悲伤、愤怒、焦虑、厌烦、中性」中选择
- intensity: 情绪强度，0-100的整数
- confidence: 置信度，0-1之间的小数
- reason: 一句话说明判断依据，不超过50字"""

    def __init__(self, llm: Optional[LLMServer] = None):
        self.llm = llm or get_llm_server()

    def _tokenize(self, text: str) -> List[str]:
        # 按标点和空格做短语级切分
        parts = re.split(r'[，,。.！!？?；;、：:\s]+', text)
        return [p for p in parts if p]

    def _rule_analysis(self, text: str) -> Dict[str, Any]:
        tokens = self._tokenize(text)
        emotion_words = []
        degree_words = []
        negation_words = []
        contrast_words = []

        # 收集所有情绪词
        all_emotion_words = set()
        for words in self.EMOTION_WORDS.values():
            all_emotion_words.update(words)

        for t in tokens:
            if t in all_emotion_words:
                emotion_words.append(t)
            if t in self.DEGREE_WORDS:
                degree_words.append(t)
            if t in self.NEGATION_WORDS:
                negation_words.append(t)
            if t in self.CONTRAST_WORDS:
                contrast_words.append(t)

        # 统计各情绪类别命中数
        scores = {}
        for emotion, words in self.EMOTION_WORDS.items():
            scores[emotion] = sum(1 for w in emotion_words if w in words)

        max_emotion = max(scores, key=scores.get)  # type: ignore
        has_any = any(scores.values())

        return {
            "tokens": tokens,
            "emotion_words": emotion_words,
            "degree_words": degree_words,
            "negation_words": negation_words,
            "contrast_words": contrast_words,
            "scores": scores,
            "predicted_emotion": max_emotion if has_any else "中性",
        }

    def _call_llm(self, text: str, rule_info: Dict) -> Dict[str, Any]:
        prompt = f"""句子："{text}"

规则初步分析：{json.dumps(rule_info, ensure_ascii=False)}

请输出JSON格式的情绪分析结果。"""
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
        rule_info = self._rule_analysis(msg.text)
        llm_result = self._call_llm(msg.text, rule_info)

        return {
            "tokens": llm_result.get("tokens", rule_info["tokens"]),
            "emotion_words": llm_result.get("emotion_words", rule_info["emotion_words"]),
            "degree_words": llm_result.get("degree_words", rule_info["degree_words"]),
            "negation_words": llm_result.get("negation_words", rule_info["negation_words"]),
            "contrast_words": llm_result.get("contrast_words", rule_info["contrast_words"]),
            "emotion": llm_result.get("emotion", rule_info["predicted_emotion"]),
            "intensity": llm_result.get("intensity", 50),
            "confidence": llm_result.get("confidence", 0.5),
            "reason": llm_result.get("reason", ""),
        }
