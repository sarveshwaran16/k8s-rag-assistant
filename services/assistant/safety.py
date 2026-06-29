import re

DANGEROUS_VERBS = {"delete", "evict", "drain", "cordon", "taint", "scale", "rollback", "patch"}


def extract_citations(answer: str) -> list[str]:
    """Pull out [source:Title] tags from the answer."""
    return re.findall(r"\[source:([^\]]+)\]", answer)


def extract_kubectl_commands(answer: str) -> list[str]:
    """Pull out kubectl <verb> ... invocations from the answer."""
    return re.findall(r"kubectl\s+[a-z\-]+(?:\s+[a-z\-]+)?", answer.lower())


def validate_citations(answer: str, sources: list[dict]) -> dict:
    """Check that every citation tag actually matches a retrieved source title."""
    valid_titles = {s["title"] for s in sources}
    citations = extract_citations(answer)
    invalid = [c for c in citations if c.strip() not in valid_titles]
    return {
        "citation_count": len(citations),
        "invalid_citations": invalid,
        "all_citations_valid": len(invalid) == 0
    }


def validate_commands(answer: str, chunks: list[dict]) -> dict:
    """
    Check that every kubectl command mentioned in the answer actually appears,
    verbatim or near-verbatim, somewhere in the retrieved context. Catches the
    real-but-misapplied command problem (e.g. suggesting `kubectl autoscale`
    for a quota issue when the source never mentions it for that purpose).
    """
    context_text = " ".join(c["text"].lower() for c in chunks)
    commands = extract_kubectl_commands(answer)
    unverified = [cmd for cmd in commands if cmd not in context_text]
    return {
        "commands_found": commands,
        "unverified_commands": unverified,
        "all_commands_verified": len(unverified) == 0
    }


def safety_check_node(state: dict) -> dict:
    """LangGraph node — runs after generation, validates citations and commands."""
    citation_result = validate_citations(state["answer"], state["sources"])
    command_result = validate_commands(state["answer"], state["retrieved_chunks"])

    answer = state["answer"]
    notes = []

    if not citation_result["all_citations_valid"]:
        notes.append(
            f"some citations reference sources not in the retrieved set: "
            f"{citation_result['invalid_citations']}"
        )

    if command_result["unverified_commands"]:
        for cmd in command_result["unverified_commands"]:
            answer = answer.replace(
                cmd,
                f"<command omitted — '{cmd}' could not be verified against retrieved sources>"
            )
        notes.append(
            f"removed unverified command(s): {command_result['unverified_commands']}"
        )

    if notes:
        answer += f"\n\n_Safety check: {'; '.join(notes)}_"

    return {
        "answer": answer,
        "safety_check": {**citation_result, **command_result}
    }