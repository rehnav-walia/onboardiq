from pathlib import Path
from string import Template

# backend/app/llm/prompts.py -> backend/prompts/
_PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"


def render_prompt(name: str, **substitutions: str) -> str:
    """Loads prompts/<name>.txt and fills in $placeholders.

    Uses Template.safe_substitute so a missing substitution leaves the
    placeholder text in place instead of raising — a prompt template should
    never be able to crash the extraction pipeline.
    """
    template_text = (_PROMPTS_DIR / f"{name}.txt").read_text(encoding="utf-8")
    return Template(template_text).safe_substitute(**substitutions)
