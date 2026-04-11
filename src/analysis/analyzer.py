"""
Layer 2 — Analysis: Use the LLM to analyze the project context and produce
a structured architecture description + validation Q&A.
"""

import json
from dataclasses import dataclass, field
from .llm_client import LLMClient
from ..ingestion.context import ProjectContext

SYSTEM_PROMPT_PT = """Você é um arquiteto de dados e software sênior especialista em documentação técnica.
Sua função é analisar projetos de engenharia e produzir:
1. Uma descrição clara da arquitetura em camadas
2. Um JSON estruturado representando as camadas e componentes (para gerar o diagrama)
3. Pontos de atenção e boas práticas que o projeto está seguindo ou deveria seguir

Sempre responda em JSON válido quando solicitado. Seja preciso, técnico e objetivo."""

SYSTEM_PROMPT_EN = """You are a senior data and software architect specializing in technical documentation.
Your role is to analyze engineering projects and produce:
1. A clear layered architecture description
2. A structured JSON representing layers and components (for diagram generation)
3. Attention points and best practices the project follows or should follow

Always respond with valid JSON when requested. Be precise, technical, and objective."""

ANALYSIS_SCHEMA = """
Return a JSON object with this exact structure:
{
  "project_name": "string",
  "description": "2-3 sentence project summary",
  "tech_stack": ["list of main technologies"],
  "layers": [
    {
      "id": "layer_1",
      "name": "Layer display name",
      "description": "What this layer does",
      "color": "#hex_color",
      "components": [
        {
          "name": "Component name",
          "description": "What it does",
          "tech": "Technology used",
          "type": "source|process|store|api|ui|infra"
        }
      ],
      "connections_to": ["layer_2"]
    }
  ],
  "good_practices": ["list of good practices observed"],
  "improvement_points": ["list of things that could be improved"],
  "validation_questions": [
    "Question to confirm understanding of a specific part",
    "Question about an ambiguous architectural decision"
  ]
}
"""


@dataclass
class AnalysisResult:
    raw_json: dict
    project_name: str
    description: str
    tech_stack: list[str]
    layers: list[dict]
    good_practices: list[str]
    improvement_points: list[str]
    validation_questions: list[str]
    user_corrections: list[str] = field(default_factory=list)


@dataclass
class ArchitectureAnalyzer:
    client: LLMClient
    language: str = "pt"

    def analyze(self, context: ProjectContext) -> AnalysisResult:
        system = SYSTEM_PROMPT_PT if self.language == "pt" else SYSTEM_PROMPT_EN
        lang_note = "Responda em português brasileiro." if self.language == "pt" else "Respond in English."

        user_prompt = (
            f"{context.to_llm_prompt(self.language)}\n\n"
            f"---\n{lang_note}\n"
            f"Analyze the project above and return ONLY a valid JSON object following this schema:\n"
            f"{ANALYSIS_SCHEMA}"
        )

        raw_response = self.client.chat(system=system, user=user_prompt)
        data = self._parse_json(raw_response)
        return self._build_result(data)

    def validate_with_user(
        self, result: AnalysisResult, user_answers: dict[str, str]
    ) -> AnalysisResult:
        """Re-analyze incorporating user corrections/answers."""
        system = SYSTEM_PROMPT_PT if self.language == "pt" else SYSTEM_PROMPT_EN
        lang_note = "Responda em português brasileiro." if self.language == "pt" else "Respond in English."

        corrections_text = "\n".join(
            f"- Q: {q}\n  A: {a}" for q, a in user_answers.items()
        )

        user_prompt = (
            f"Previous architecture analysis:\n```json\n{json.dumps(result.raw_json, ensure_ascii=False, indent=2)}\n```\n\n"
            f"The user provided these corrections and clarifications:\n{corrections_text}\n\n"
            f"{lang_note}\n"
            f"Update the architecture analysis incorporating these corrections. "
            f"Return ONLY the updated JSON following the same schema."
        )

        raw_response = self.client.chat(system=system, user=user_prompt)
        data = self._parse_json(raw_response)
        updated = self._build_result(data)
        updated.user_corrections = list(user_answers.values())
        return updated

    def _parse_json(self, response: str) -> dict:
        text = response.strip()

        # Strip markdown code fences if present
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove first line (```json or ```) and last line (```)
            inner = lines[1:]
            if inner and inner[-1].strip() == "```":
                inner = inner[:-1]
            text = "\n".join(inner).strip()

        # Try direct parse first
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Extract outermost {...} block in case the LLM added prose before/after
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidate = text[start:end + 1]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass

        # Last resort: try to repair truncated JSON by closing open structures
        try:
            return self._repair_json(text)
        except Exception:
            pass

        raise ValueError(
            f"LLM did not return valid JSON.\n\nFirst 800 chars of response:\n{text[:800]}"
        )

    def _repair_json(self, text: str) -> dict:
        """Best-effort repair of truncated JSON by balancing brackets."""
        start = text.find("{")
        if start == -1:
            raise ValueError("No JSON object found")

        chunk = text[start:]
        depth_brace = 0
        depth_bracket = 0
        in_string = False
        escape = False

        for i, ch in enumerate(chunk):
            if escape:
                escape = False
                continue
            if ch == "\\" and in_string:
                escape = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == "{":
                depth_brace += 1
            elif ch == "}":
                depth_brace -= 1
                if depth_brace == 0:
                    # Found complete object
                    return json.loads(chunk[: i + 1])
            elif ch == "[":
                depth_bracket += 1
            elif ch == "]":
                depth_bracket -= 1

        # Truncated — close open structures
        suffix = ""
        if in_string:
            suffix += '"'
        suffix += "]" * max(depth_bracket, 0)
        suffix += "}" * max(depth_brace, 0)
        return json.loads(chunk + suffix)

    def _build_result(self, data: dict) -> AnalysisResult:
        return AnalysisResult(
            raw_json=data,
            project_name=data.get("project_name", "Unknown Project"),
            description=data.get("description", ""),
            tech_stack=data.get("tech_stack", []),
            layers=data.get("layers", []),
            good_practices=data.get("good_practices", []),
            improvement_points=data.get("improvement_points", []),
            validation_questions=data.get("validation_questions", []),
        )
