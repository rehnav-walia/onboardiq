class AIUnavailableError(Exception):
    """Raised whenever we did not get a usable answer from the LLM — the API
    call itself failed (network, timeout, auth, rate limit) or its response
    could not be parsed into our expected schema. Callers must treat this as
    "route to manual review", never as a reason to error out (US-12)."""
