import json
import re
from typing import Dict, Any, Optional
from dataclasses import dataclass
from llm_server import get_llm_server, LLMServer


@dataclass
class JudgeOutput:
    final_emotion: str
    secondary_emotion: Optional[str]
    final_intensity: int
    final_confidence: float
    is_sarcasm: bool
    is_mixed: bool
    reason: str


class JudgeAgent:

    CONFIDENCE_THRESHOLD = 0.6

    SYSTEM_PROMPT = """你是一个情绪融合专家。请严格按照JSON格式输出分析结果，不要输出markdown代码块，不要包含额外解释。

输出字段说明：
- final_emotion: 最终情绪，从「开心、悲伤、愤怒、焦虑、厌烦、中性」中选择
- secondary_emotion: 次情绪，可为null
- final_intensity: 最终强度，0-100的整数
- final_confidence: 最终置信度，0-1之间的小数
- is_sarcasm: 布尔值，是否反讽
- is_mixed: 布尔值，是否混合情绪
- reason: 一段话说明最终判断依据，不超过100字"""

    def __init__(self, llm: Optional[LLMServer] = None):
        self.llm = llm or get_llm_server()

    def _merge(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        """规则融合：根据 sample_type 和置信度决定最终值"""
        result = {
            "is_sarcasm": False,
            "is_mixed": False,
            "secondary_emotion": None,
        }

        sample_type = ctx["sample_type"]

        if sample_type == "direct":
            result.update({
                "final_emotion": ctx["emotion"],
                "final_intensity": ctx["emotion_intensity"],
                "final_confidence": ctx["emotion_confidence"],
            })

        elif sample_type == "sarcasm_suspected":
            is_sarcasm = ctx.get("is_sarcasm", False)
            sarcasm_conf = ctx.get("sarcasm_confidence", 0)

            if is_sarcasm and sarcasm_conf >= self.CONFIDENCE_THRESHOLD:
                result.update({
                    "is_sarcasm": True,
                    "final_emotion": ctx.get("true_emotion", ctx["emotion"]),
                    "final_intensity": ctx.get("revised_intensity", ctx["emotion_intensity"]),
                    "final_confidence": max(sarcasm_conf, ctx["emotion_confidence"]),
                })
            else:
                result.update({
                    "is_sarcasm": is_sarcasm,
                    "final_emotion": ctx["emotion"],
                    "final_intensity": ctx["emotion_intensity"],
                    "final_confidence": round(ctx["emotion_confidence"] * 0.8, 2),
                })

        elif sample_type == "mix":
            is_mixed = ctx.get("is_mixed", False)
            mix_conf = ctx.get("mix_confidence", 0)

            if is_mixed and mix_conf >= self.CONFIDENCE_THRESHOLD:
                result.update({
                    "is_mixed": True,
                    "final_emotion": ctx.get("primary_emotion", ctx["emotion"]),
                    "secondary_emotion": ctx.get("secondary_emotion"),
                    "final_intensity": ctx.get("revised_intensity", ctx["emotion_intensity"]),
                    "final_confidence": max(mix_conf, ctx["emotion_confidence"]),
                })
            else:
                result.update({
                    "is_mixed": is_mixed,
                    "final_emotion": ctx["emotion"],
                    "final_intensity": ctx["emotion_intensity"],
                    "final_confidence": round(ctx["emotion_confidence"] * 0.8, 2),
                })

        return result

    def _call_llm(self, ctx: Dict[str, Any], rule_result: Dict[str, Any]) -> Dict[str, Any]:
        """LLM 验证融合结果并生成 reason"""
        sarcasm_section = ""
        if ctx.get("is_sarcasm") is not None:
            sarcasm_section = (
                f"反讽分析：is_sarcasm={ctx['is_sarcasm']}，"
                f"表层={ctx.get('surface_emotion', '?')}，"
                f"真实={ctx.get('true_emotion', '?')} "
                f"（置信度：{ctx.get('sarcasm_confidence', '?')}）"
            )

        mix_section = ""
        if ctx.get("is_mixed") is not None:
            mix_section = (
                f"混合分析：is_mixed={ctx['is_mixed']}，"
                f"主情绪={ctx.get('primary_emotion', '?')}，"
                f"次情绪={ctx.get('secondary_emotion', '?')} "
                f"（置信度：{ctx.get('mix_confidence', '?')}）"
            )

        prompt = (
            f'句子："{ctx["text"]}"\n'
            f'路由类型：{ctx["sample_type"]}（{ctx.get("router_reason", "")}）\n'
            f'Emotion分析：{ctx["emotion"]}（强度：{ctx["emotion_intensity"]}，置信度：{ctx["emotion_confidence"]}）\n'
            f'{sarcasm_section}\n'
            f'{mix_section}\n'
            f'规则融合结果：{json.dumps(rule_result, ensure_ascii=False)}\n\n'
            f'请验证规则融合结果是否合理，并输出JSON格式的最终判断结果。'
        )

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

    def process(
        self,
        input_data: Dict[str, Any],
        router_result: Dict[str, Any],
        emotion_result: Dict[str, Any],
        sarcasm_result: Optional[Dict[str, Any]] = None,
        mix_result: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """融合所有上游 Agent 结果，输出最终判断"""
        ctx = {
            "text": input_data.get("text", ""),
            "sample_type": router_result.get("sample_type", "direct"),
            "router_reason": router_result.get("routing_reason", ""),
            "emotion": emotion_result.get("emotion", "中性"),
            "emotion_intensity": emotion_result.get("intensity", 50),
            "emotion_confidence": emotion_result.get("confidence", 0.5),
        }

        if sarcasm_result:
            ctx.update({
                "is_sarcasm": sarcasm_result.get("is_sarcasm", False),
                "surface_emotion": sarcasm_result.get("surface_emotion"),
                "true_emotion": sarcasm_result.get("true_emotion"),
                "revised_intensity": sarcasm_result.get("revised_intensity"),
                "sarcasm_confidence": sarcasm_result.get("confidence", 0),
            })

        if mix_result:
            ctx.update({
                "is_mixed": mix_result.get("is_mixed", False),
                "primary_emotion": mix_result.get("primary_emotion"),
                "secondary_emotion": mix_result.get("secondary_emotion"),
                "mix_ratio": mix_result.get("mix_ratio"),
                "mix_confidence": mix_result.get("confidence", 0),
            })

        rule_result = self._merge(ctx)
        llm_result = self._call_llm(ctx, rule_result)

        return {
            "final_emotion": llm_result.get("final_emotion", rule_result["final_emotion"]),
            "secondary_emotion": llm_result.get("secondary_emotion", rule_result.get("secondary_emotion")),
            "final_intensity": llm_result.get("final_intensity", rule_result["final_intensity"]),
            "final_confidence": llm_result.get("final_confidence", rule_result["final_confidence"]),
            "is_sarcasm": llm_result.get("is_sarcasm", rule_result["is_sarcasm"]),
            "is_mixed": llm_result.get("is_mixed", rule_result["is_mixed"]),
            "reason": llm_result.get("reason", ""),
        }
