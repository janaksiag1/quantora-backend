"""Role assignments use the five responding model IDs checked on 2026-10-31.
Roles can share a model; every response records actual model and fallback.
"""
AGENT_MODELS = {
    'vector': 'gemini-3.1-flash-lite',
    'atlas': 'gemma-4-26b-a4b-it',
    'pulse': 'gemini-3-flash-preview',
    'aegis': 'gemini-3.5-flash-lite',
    'nova': 'gemini-3.6-flash',
    'orbit': 'gemini-3.1-flash-lite',
    'rook': 'gemini-3-flash-preview',
    'echo': 'gemini-3.5-flash-lite',
    'nexus': 'gemini-3.6-flash',
    'prism': 'gemini-3.5-flash-lite',
}
