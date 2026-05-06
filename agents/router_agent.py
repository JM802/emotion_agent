import json
import re
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from enum import Enum
from llm_server import get_llm_server, LLMServer

#定义枚举的类型
class SampleType(Enum):
    DIRECT = "direct"
    SARCASM_SUSPECTED = "sarcasm_suspected"
    MIX = "mix"


@dataclass
class InputMessage:
    id: str
    user_id: str
    text: str
    source: str
    created_at: str


@dataclass
class RouterOutput:
    sample_type: str
    need_sarcasm_check: bool
    need_mix_check: bool
    routing_reason: str


class RouterAgent:

    # 正向情绪词
    POSITIVE_WORDS = {
        "太好了", "真棒", "开心", "高兴", "幸福", "兴奋", "激动",
        "满意", "期待", "喜欢", "爱", "感动", "庆幸", "幸运",
        "不错", "完美", "精彩", "优秀", "厉害", "爽", "nice", "棒"
    }

    # 负向情绪词
    NEGATIVE_WORDS = {
        "难过", "伤心", "痛苦", "焦虑", "烦躁", "愤怒", "生气",
        "失望", "无奈", "崩溃", "累", "疲惫", "郁闷", "压抑",
        "讨厌", "恨", "烦", "惨", "糟糕", "烂", "难受"
    }

    # 典型反讽触发词
    SARCASM_TRIGGERS = {
        "又", "还真是", "真棒", "太好了", "好极了", "真不错",
        "可真行", "服了", "呵呵", "有意思", "真是太", "还能这样",
        "不愧是你", "谢谢你啊", "多谢了", "感激不尽", "感恩",
        "可真是", "可以可以", "牛"
    }

    # 转折词
    TRANSITION_WORDS = {
        "但是", "可是", "不过", "然而", "虽然", "只是",
        "但", "却", "却也", "也挺"
    }

    # 负向场景词
    NEGATIVE_SCENARIOS = {
        "加班", "开会", "改需求", "延期", "熬夜", "通宵",
        "bug", "故障", "投诉", "扣钱", "裁员", "加班到",
        "周末", "凌晨", "年底", "汇报", "考核"
    }

    # 低能量/压抑模式
    LOW_ENERGY_PATTERNS = [
        r"提不[起上]劲",#正则匹配
        r"不知道怎么",
        r"说不出",
        r"堵得慌",
        r"空落落",
        r"不算.{1,3}但",#examle特别好
        r"说不上来",
        r"有点.{1,2}但又",#example不行
        r"就是.{1,3}得慌",#example累
    ]

    #system_prompt
    SYSTEM_PROMPT = """你是一个文本分析专家，负责为句子分流系统生成简洁的路由理由。要求：
        - 用一句话（不超过50字）解释为什么这句话被判定为某个类型
        - 简洁明了，直击要点
        - 不要在理由中包含"经分析"、"根据规则"等冗余表述
        - 直接描述句子的语言特征"""

    def __init__(self, llm: Optional[LLMServer] = None):
        self.llm = llm or get_llm_server()

    def _check_sarcasm(self, text: str) -> Optional[RouterOutput]:
        #检测疑似反讽
        triggers = [t for t in self.SARCASM_TRIGGERS if t in text]
        has_positive = any(w in text for w in self.POSITIVE_WORDS)
        has_negative = any(s in text for s in self.NEGATIVE_SCENARIOS)

        if triggers and (has_positive and has_negative):
            return True, {
                "triggers": triggers,
                "positive_negative_conflict": True,
            }

        if triggers:
            return True, {"triggers": triggers}

        return False, {}
    

    def _check_mix(self, text: str) -> tuple:
        #检测混合情绪
        transitions = [t for t in self.TRANSITION_WORDS if t in text]
        pos = [w for w in self.POSITIVE_WORDS if w in text]
        neg = [w for w in self.NEGATIVE_WORDS if w in text]
        low_energy = [p for p in self.LOW_ENERGY_PATTERNS if re.search(p, text)]

        if transitions or (pos and neg) or low_energy:
            return True, {
                "transitions": transitions,
                "positive_words": pos,
                "negative_words": neg,
                "low_energy_patterns": low_energy,
            }

        return False, {}

    def _generate_reason(self, sample_type: str, text: str, info: Dict) -> str:
        #调用 LLM 生成理由
        prompts = {
            "sarcasm_suspected": f"""这句话被判定为"疑似反讽"。
            句子："{text}"
            触发信息：{json.dumps(info, ensure_ascii=False)}
            请生成路由理由。要求：
            - 指明具体哪些词构成反讽（如正向词+负向场景的矛盾）
            - 格式参考："句子中'太好了'与'周末继续改需求'形成矛盾，表面正向实则负向，疑似反讽" """,

            "mix": f"""这句话被判定为"混合情绪"。
            句子："{text}"
            触发信息：{json.dumps(info, ensure_ascii=False)}
            请生成路由理由。要求：
            -如有转折词，指出具体转折词和两侧情绪
            -如有低能量表达，指出具体是哪个词
            -如有正负情绪词并存，指出分别是什么
            - 格式参考："句子通过'但'连接'开心'和'累'，表达喜悦与疲惫并存的复合情绪"
            - 格式参考："句子中'提不起劲'体现低能量状态，情绪模糊压抑" """,

            "direct": f"""这句话被判定为"直接表达"。
            句子："{text}"
            请生成路由理由。要求：
            - 指明句子表达的具体情绪（如高兴、焦虑、愤怒、疲惫等）
            - 说明判断依据（如情绪词、语气）
            - 格式参考："句子直接使用'开心'一词，情绪明确为喜悦"
            - 格式参考："句子直接表达焦虑情绪，用词'特别焦虑'情绪强度高" """
            }

        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": prompts[sample_type]},
        ]

        return self.llm.chat(messages, temperature=0.1)

    def _route(self, msg: InputMessage) -> RouterOutput:
        text = msg.text

        # 优先级：sarcasm > mix > direct
        # 先并行检查
        is_sarcasm, sarcasm_info = self._check_sarcasm(text)
        is_mix, mix_info = self._check_mix(text)

        # sarcasm 优先
        if is_sarcasm:
            reason = self._generate_reason("sarcasm_suspected", text, sarcasm_info)
            return {
                "sample_type": "sarcasm_suspected",
                "need_sarcasm_check": True,
                "need_mix_check": False,
                "routing_reason": reason,
            }

        if is_mix:
            reason = self._generate_reason("mix", text, mix_info)
            return {
                "sample_type": "mix",
                "need_sarcasm_check": False,
                "need_mix_check": True,
                "routing_reason": reason,
            }

        # fallback: direct
        reason = self._generate_reason("direct", text, {})
        return {
            "sample_type": "direct",
            "need_sarcasm_check": False,
            "need_mix_check": False,
            "routing_reason": reason,
        }
    
    
    
    def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        #处理输入，返回路由决策
        msg = InputMessage(**input_data)
        result = self._route(msg)
        return result

#测试用例
if __name__ == "__main__":
    agent = RouterAgent()

    test_cases = [
        {
            "id": "msg_001",
            "user_id": "u_1001",
            "text": "太好了，周末又能继续改需求了。",
            "source": "chat",
            "created_at": "2026-03-24T14:00:00",
        },
        {
            "id": "msg_002",
            "user_id": "u_1002",
            "text": "我今天很开心",
            "source": "chat",
            "created_at": "2026-03-24T14:01:00",
        },
        {
            "id": "msg_003",
            "user_id": "u_1003",
            "text": "开心是开心，但也挺累",
            "source": "chat",
            "created_at": "2026-03-24T14:02:00",
        },
        {
            "id": "msg_004",
            "user_id": "u_1004",
            "text": "真棒，需求又改了",
            "source": "chat",
            "created_at": "2026-03-24T14:03:00",
        },
        {
            "id": "msg_005",
            "user_id": "u_1005",
            "text": "不算难过，就是提不起劲",
            "source": "chat",
            "created_at": "2026-03-24T14:04:00",
        },
        {
            "id": "msg_006",
            "user_id": "u_1006",
            "text": "我现在特别焦虑",
            "source": "chat",
            "created_at": "2026-03-24T14:05:00",
        },
    ]

    for case in test_cases:
        result = agent.process(case)
        print(f"Input:  {case['text']}")
        print(f"Output: {json.dumps(result, ensure_ascii=False)}")
        print("-" * 60)