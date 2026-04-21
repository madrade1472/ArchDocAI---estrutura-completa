"""
Layer 2 - Analysis: Use the LLM to analyze the project context and produce
a structured architecture description + validation Q&A.
"""

import json
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, field_validator

from .llm_client import LLMClient
from ..ingestion.context import ProjectContext
from src.logger import get_logger

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Pydantic schema - validates LLM response before trusting it
# ---------------------------------------------------------------------------

class ComponentSchema(BaseModel):
    name: str
    description: str = ""
    tech: str = ""
    type: Literal["source", "process", "store", "api", "ui", "infra"] = "process"
    connections_to: list[str] = Field(default_factory=list)  # names of other components this feeds into

    @field_validator("connections_to", mode="before")
    @classmethod
    def cap_connections(cls, v):
        return v[:6] if isinstance(v, list) else []

class LayerSchema(BaseModel):
    id: str
    name: str
    description: str = ""
    color: str = "#4578a0"
    components: list[ComponentSchema] = Field(default_factory=list)
    connections_to: list[str] = Field(default_factory=list)

    @field_validator("color")
    @classmethod
    def validate_color(cls, v: str) -> str:
        if not v.startswith("#") or len(v) not in (4, 7):
            return "#4578a0"
        return v

    @field_validator("components", mode="before")
    @classmethod
    def cap_components(cls, v):
        return v[:6] if isinstance(v, list) else v

class QualityScoreBreakdown(BaseModel):
    """Five dimensions, each 0-20. Total = sum (0-100)."""
    arquitetura: int = 0       # cohesion, layer separation, scalability
    codigo: int = 0            # patterns, structure, maintainability
    documentacao: int = 0      # README, inline docs, ADRs
    testabilidade: int = 0     # test presence, coverage, organization
    devops: int = 0            # containers, CI/CD, IaC, observability

    @field_validator("arquitetura", "codigo", "documentacao", "testabilidade", "devops", mode="before")
    @classmethod
    def clamp_dimension(cls, v):
        try:
            n = int(v)
        except (TypeError, ValueError):
            return 0
        return max(0, min(20, n))


class QualityScoreSchema(BaseModel):
    total: int = 0
    rationale: str = ""
    breakdown: QualityScoreBreakdown = Field(default_factory=QualityScoreBreakdown)

    @field_validator("total", mode="before")
    @classmethod
    def clamp_total(cls, v):
        try:
            n = int(v)
        except (TypeError, ValueError):
            return 0
        return max(0, min(100, n))


class LLMResponseSchema(BaseModel):
    project_name: str = "Unknown Project"
    description: str = ""
    tech_stack: list[str] = Field(default_factory=list)
    layers: list[LayerSchema] = Field(default_factory=list)
    good_practices: list[str] = Field(default_factory=list)
    improvement_points: list[str] = Field(default_factory=list)
    validation_questions: list[str] = Field(default_factory=list)
    quality_score: QualityScoreSchema = Field(default_factory=QualityScoreSchema)

    @field_validator("tech_stack", mode="before")
    @classmethod
    def cap_tech_stack(cls, v):
        return v[:8] if isinstance(v, list) else v

    @field_validator("layers", mode="before")
    @classmethod
    def cap_layers(cls, v):
        return v[:7] if isinstance(v, list) else v

    @field_validator("good_practices", "improvement_points", mode="before")
    @classmethod
    def cap_lists(cls, v):
        return v[:5] if isinstance(v, list) else v

    @field_validator("validation_questions", mode="before")
    @classmethod
    def cap_questions(cls, v):
        return v[:2] if isinstance(v, list) else v

SYSTEM_PROMPT_PT = """Você é um arquiteto de dados e software sênior especialista em documentação técnica.
Sua função é analisar projetos de engenharia e produzir:
1. Uma descrição clara da arquitetura em camadas
2. Um JSON estruturado representando as camadas e componentes (para gerar o diagrama)
3. Pontos de atenção e boas práticas que o projeto está seguindo ou deveria seguir

PRINCÍPIO DE COESÃO FUNCIONAL (regra mais importante para a estrutura):
Agrupe componentes pelo PAPEL FUNCIONAL que cumprem no produto, não pela pasta ou arquivo onde estão.
Tudo que faz a mesma coisa pertence ao mesmo bloco/camada — mesmo que esteja espalhado pelo código.
Exemplos: todas as chamadas a LLM ficam juntas, todos os geradores de documento ficam juntos,
todos os clientes de APIs externas ficam juntos, toda a persistência fica junta.
Se você se pegar criando duas camadas que fazem coisas parecidas, FUNDA-AS em uma só.

Sempre responda em JSON válido quando solicitado. Seja preciso, técnico e objetivo."""

SYSTEM_PROMPT_EN = """You are a senior data and software architect specializing in technical documentation.
Your role is to analyze engineering projects and produce:
1. A clear layered architecture description
2. A structured JSON representing layers and components (for diagram generation)
3. Attention points and best practices the project follows or should follow

FUNCTIONAL COHESION PRINCIPLE (most important rule for structure):
Group components by the FUNCTIONAL ROLE they play in the product, not by the folder or file they live in.
Everything that does the same thing belongs in the same block/layer — even if it is scattered across the code.
Examples: all LLM calls go together, all document generators go together,
all external API clients go together, all persistence goes together.
If you find yourself creating two layers that do similar things, MERGE them into one.

Always respond with valid JSON when requested. Be precise, technical, and objective."""

ANALYSIS_SCHEMA = """
Return a JSON object with this exact structure. Respect ALL limits below — do NOT exceed them.

GROUPING RULES (apply BEFORE counting layers/components):
- Group by FUNCTIONAL ROLE, not by file path. Files in different folders that do the same job belong in the SAME component or layer.
- A "layer" represents one functional responsibility of the product (e.g. "LLM Analysis", "Document Generation", "Data Ingestion", "Web Interface"). Never create a layer that just mirrors a folder name.
- A "component" inside a layer represents one cohesive capability. If two pieces of code call the same external service or produce the same kind of artifact, they should be ONE component, not two.
- All LLM calls (prompt building, API client, response parsing, retries) → one component or one layer, never split.
- All output/document generators (PDF, DOCX, Markdown, PNG, JSON for UI) → grouped under one "Output" layer.
- All external API integrations → grouped together (one per provider, not per call site).
- Cross-cutting concerns (logging, config, auth) are NOT layers — mention them in description or omit.
- Before finalizing: re-read your layers. If two layers describe similar responsibilities, MERGE them.

STRICT LIMITS:
- description: exactly 2-3 sentences, no more
- tech_stack: 5 to 8 items max
- layers: 3 to 7 layers (merge minor layers if needed)
- components per layer: 3 to 6 items max (pick the most architecturally relevant)
- good_practices: exactly 3 to 5 items
- improvement_points: exactly 3 to 5 items
- validation_questions: exactly 2 items
- All text values: one sentence max, no bullet points inside strings
- connections_to in components: use EXACT component names from OTHER layers that this component feeds data into or calls directly (max 3 per component). Leave empty [] if it truly has no downstream dependency.

{
  "project_name": "string",
  "description": "2-3 sentence project summary",
  "tech_stack": ["up to 8 main technologies"],
  "layers": [
    {
      "id": "layer_1",
      "name": "Layer display name",
      "description": "One sentence: what this layer does",
      "color": "#hex_color",
      "components": [
        {
          "name": "Component name",
          "description": "One sentence: what it does",
          "tech": "Technology used",
          "type": "source|process|store|api|ui|infra",
          "connections_to": ["ExactNameOfComponentInAnotherLayer"]
        }
      ],
      "connections_to": ["layer_2"]
    }
  ],
  "good_practices": ["3 to 5 items"],
  "improvement_points": ["3 to 5 items"],
  "validation_questions": ["exactly 2 questions"],
  "quality_score": {
    "total": 0,
    "rationale": "1-2 sentences explaining the overall score",
    "breakdown": {
      "arquitetura": 0,
      "codigo": 0,
      "documentacao": 0,
      "testabilidade": 0,
      "devops": 0
    }
  }
}

QUALITY SCORE RULES (the project gets a 0-100 score):
- Score 5 dimensions, each 0 to 20. The "total" field MUST equal the sum of the breakdown.
- arquitetura (0-20): coesao, separacao de responsabilidades, modularidade, escalabilidade.
- codigo (0-20): padroes consistentes, nomes claros, organizacao de pastas, baixo acoplamento.
- documentacao (0-20): README presente e util, comentarios significativos, docs estruturadas.
- testabilidade (0-20): testes existem e estao organizados, cobrem fluxos criticos.
- devops (0-20): containerizacao, CI/CD, IaC, observabilidade, gerenciamento de configuracao.
- Be honest and calibrated: 90-100 = projeto exemplar, 70-89 = solido com pontos de melhoria, 50-69 = funcional mas com lacunas relevantes, 30-49 = problemas estruturais, 0-29 = critico.
- The "rationale" field must be 1-2 sentences justifying the total in plain language matching the OUTPUT_LANGUAGE.
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
    quality_score: dict = field(default_factory=lambda: {
        "total": 0,
        "rationale": "",
        "breakdown": {"arquitetura": 0, "codigo": 0, "documentacao": 0,
                      "testabilidade": 0, "devops": 0},
    })


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

        log.info("Sending project context to LLM (provider=%s, model=%s)", self.client.config.provider, self.client.config.model)
        raw_response = self.client.chat(system=system, user=user_prompt)
        log.info("LLM response received (%d chars)", len(raw_response))
        data = self._parse_json(raw_response)
        result = self._build_result(data)
        log.info("Analysis complete: %d layers, %d components total", len(result.layers), sum(len(l.get("components", [])) for l in result.layers))
        return result

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
            result = self._repair_json(text)
            log.warning("JSON was truncated and repaired - some fields may be incomplete")
            return result
        except Exception:
            pass

        raise ValueError(
            f"LLM did not return valid JSON.\n\nFirst 800 chars of response:\n{text[:800]}"
        )

    def _repair_json(self, text: str) -> dict:
        """Best-effort repair of truncated JSON using a stack to close in correct order."""
        start = text.find("{")
        if start == -1:
            raise ValueError("No JSON object found")

        chunk = text[start:]
        stack: list[str] = []
        in_string = False
        escape = False
        after_colon = False   # True when last structural token was ':'

        for i, ch in enumerate(chunk):
            if escape:
                escape = False
                continue
            if ch == "\\" and in_string:
                escape = True
                continue
            if ch == '"':
                if in_string:
                    in_string = False
                    after_colon = False  # string value/key is done
                else:
                    in_string = True
                continue
            if in_string:
                continue

            if ch in "{[":
                stack.append(ch)
                after_colon = False
            elif ch == "}":
                if stack and stack[-1] == "{":
                    stack.pop()
                after_colon = False
                if not stack:
                    return json.loads(chunk[: i + 1])
            elif ch == "]":
                if stack and stack[-1] == "[":
                    stack.pop()
                after_colon = False
            elif ch == ":":
                after_colon = True
            elif ch == ",":
                after_colon = False

        # Strip only trailing commas (never colons — they belong to the key before null)
        tail = chunk.rstrip()
        while tail and tail[-1] == ",":
            tail = tail[:-1].rstrip()

        suffix = ""
        if in_string:
            suffix += '"'           # close the open string
            if not after_colon:
                # The open string was a KEY (we never saw ':' after it) -> add a null value
                suffix += ": null"
        elif after_colon:
            # Truncated right after ':', no value was written -> insert null
            suffix += "null"

        for opener in reversed(stack):
            suffix += "}" if opener == "{" else "]"

        try:
            return json.loads(tail + suffix)
        except json.JSONDecodeError:
            # Last resort: strip back to last clean value and close containers
            closer = "".join("}" if o == "{" else "]" for o in reversed(stack))
            return json.loads(tail + closer)

    def _build_result(self, data: dict) -> AnalysisResult:
        try:
            validated = LLMResponseSchema.model_validate(data)
            log.info("Pydantic validation passed for LLM response")
            layers = [l.model_dump() for l in validated.layers]
            score = validated.quality_score.model_dump()
            score = self._reconcile_score(score)
            return AnalysisResult(
                raw_json=data,
                project_name=validated.project_name,
                description=validated.description,
                tech_stack=validated.tech_stack,
                layers=layers,
                good_practices=validated.good_practices,
                improvement_points=validated.improvement_points,
                validation_questions=validated.validation_questions,
                quality_score=score,
            )
        except ValidationError as exc:
            log.warning("Pydantic validation found issues - falling back to safe defaults: %s", exc)
            score = self._reconcile_score(data.get("quality_score") or {})
            return AnalysisResult(
                raw_json=data,
                project_name=data.get("project_name", "Unknown Project"),
                description=data.get("description", ""),
                tech_stack=data.get("tech_stack", []),
                layers=data.get("layers", []),
                good_practices=data.get("good_practices", []),
                improvement_points=data.get("improvement_points", []),
                validation_questions=data.get("validation_questions", []),
                quality_score=score,
            )

    def _reconcile_score(self, score: dict) -> dict:
        """Ensure total matches breakdown sum and all dimensions are clamped to 0-20.

        LLMs sometimes return inconsistent totals or omit breakdown fields entirely.
        Recompute the total from the breakdown so the displayed score is always trustworthy.
        """
        defaults = {"arquitetura": 0, "codigo": 0, "documentacao": 0,
                    "testabilidade": 0, "devops": 0}
        breakdown = {**defaults, **(score.get("breakdown") or {})}
        for k in defaults:
            try:
                breakdown[k] = max(0, min(20, int(breakdown.get(k, 0))))
            except (TypeError, ValueError):
                breakdown[k] = 0
        total = sum(breakdown[k] for k in defaults)
        return {
            "total": total,
            "rationale": (score.get("rationale") or "").strip(),
            "breakdown": breakdown,
        }
