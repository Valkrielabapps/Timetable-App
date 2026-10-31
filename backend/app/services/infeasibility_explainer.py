"""
Plain-language layer on top of the solver's existing infeasibility
diagnosis — takes the technical error strings _diagnose_infeasibility /
_diagnose_constraint_conflicts already produce (see app/services/solver.py)
and asks Claude to rewrite them as a short, conversational explanation for
a school admin who isn't a scheduling expert. This is deliberately NOT a
tool-use call like app/services/llm_constraint_parser.py's — the output
here is prose meant to be read, not structured data meant to be stored
and matched against, so free-text completion is the right shape.

Design choices (same never-raises contract as every other LLM-calling
service in this app):
  - Returns None on ANY failure — no API key configured, package missing,
    network error, malformed response. The raw technical messages are
    already stored in Timetable.error_message and rendered as a bulleted
    list regardless (see TimetableTab.jsx), so this is purely additive:
    a friendlier summary shown ABOVE that list when available, never a
    replacement the admin could be left without.
  - Called once, at generation-failure time (see
    app/routers/timetables.py's _run_generation_job), not on every
    GET /api/timetables/{id} poll — an admin's browser polls that
    endpoint repeatedly while a solve is running and occasionally after,
    so generating this on every read would mean repeated, unnecessary
    LLM calls for output that doesn't change between polls.
"""
import logging
import re

from app.core.config import settings

# What the model says when it has misread its job - answering the messages
# as if a person had written to it, rather than explaining them. Shown to a
# school that reads as the app talking nonsense, so it's thrown away and the
# plain messages are shown on their own.
_NOT_AN_EXPLANATION = re.compile(
    r"\b(i'?d be happy|could you (share|provide|paste|send)|can you (share|provide|paste)|"
    r"i'?m not (quite )?(sure|following)|share the (actual )?error|as an ai|i don'?t have)\b",
    re.I,
)

logger = logging.getLogger(__name__)


def explain_infeasibility(errors: list[str]) -> str | None:
    """`errors` is the same list[str] _diagnose_infeasibility /
    _diagnose_constraint_conflicts already produce. Returns a short
    (2-4 sentence) plain-English explanation, or None if the LLM path
    can't be used right now. Callers must handle None by just not
    showing a friendly explanation (the raw errors are shown regardless)."""
    if not errors:
        return None
    if not settings.anthropic_api_key:
        return None

    try:
        import anthropic
    except ImportError:
        logger.warning("anthropic package not installed; skipping infeasibility explanation")
        return None

    try:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        system_prompt = (
            "You explain to a school administrator, who is not a scheduling or "
            "software expert, why their timetable generation failed. You'll be given "
            "one or more technical diagnostic messages from a constraint solver. "
            "Rewrite them as a short, warm, plain-English explanation of what's "
            "contradictory and what they should try changing.\n\n"
            "Rules:\n"
            "- 2-4 sentences total, no matter how many messages you're given.\n"
            "- Preserve every specific number, teacher name, and subject name from "
            "the input — do not genericize them away.\n"
            "- If there are multiple unrelated causes, briefly address each rather "
            "than picking just one.\n"
            "- End with a concrete next step the admin can take.\n"
            "- No scheduling jargon (don't say 'infeasible', 'constraint', 'solver', "
            "'CP-SAT', etc. — say 'timetable', 'rule', 'the system').\n"
            "- Plain prose only, no bullet points or headers.\n"
            "- Never invent a cause that isn't in the input.\n"
            "- The messages are not written to you and nobody is waiting for a reply: "
            "never ask a question or ask for more information. Explain what the "
            "messages say, even if there is only one."
        )
        response = client.messages.create(
            model=settings.llm_model,
            max_tokens=400,
            system=system_prompt,
            messages=[{
                "role": "user",
                "content": "Diagnostic messages from the timetable generator:\n\n"
                + "\n".join(f"- {e}" for e in errors),
            }],
        )
        text_blocks = [b.text for b in response.content if b.type == "text"]
        explanation = "".join(text_blocks).strip()
        if not explanation or _NOT_AN_EXPLANATION.search(explanation) or explanation.endswith("?"):
            return None
        return explanation
    except Exception:
        logger.exception("Infeasibility explanation failed; showing raw errors only")
        return None
