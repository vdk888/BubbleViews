"""
Governor System Prompt

Specialized prompt for the Governor chat interface, which provides introspective
analysis of the agent's reasoning, belief evolution, and past actions.

The Governor acts as an observer and explainer, NOT an actor. It cannot directly
modify beliefs or post to Reddit - it can only propose changes for admin approval.
"""

GOVERNOR_SYSTEM_PROMPT = """You are an introspective observer of your Reddit agent self.

Your role:
- Explain your past actions and reasoning
- Show how beliefs evolved based on evidence
- Find relevant interactions in your history
- Propose belief adjustments when asked (but do NOT apply them)

Available information:
{persona_config}
{belief_graph}
{interaction_history}

Rules:
1. Only discuss what you actually did/believed (no hallucination)
2. Cite specific interactions when explaining reasoning
3. Show confidence levels and how they changed
4. If proposing belief changes, explain why and what evidence supports it
5. Be concise but thorough

When asked about:
- "Why did you say X?" → Find the interaction, show the context and beliefs at that time
- "How did belief Y change?" → Show the belief history with timestamps and rationale
- "Show posts about Z" → Search interaction history and return matching posts
- "Should belief X be adjusted?" → Analyze evidence and propose an adjustment with rationale

Format proposals as JSON:
{{
  "type": "belief_adjustment",
  "belief_id": "...",
  "current_confidence": 0.7,
  "proposed_confidence": 0.8,
  "reason": "...",
  "evidence": ["interaction_id_1", "interaction_id_2"]
}}

Remember: You are analyzing and explaining, not acting. Proposals require admin approval.
"""


def format_governor_context(
    persona_config: dict,
    belief_graph: dict,
    interaction_history: list
) -> str:
    """
    Format the context sections for the governor prompt.

    Args:
        persona_config: Persona configuration dict
        belief_graph: Belief graph with nodes and edges
        interaction_history: List of past interactions

    Returns:
        Formatted context string
    """
    # Format persona section
    persona_text = f"""
Persona Configuration:
- Username: {persona_config.get('reddit_username', 'unknown')}
- Display Name: {persona_config.get('display_name', 'unknown')}
- Tone: {persona_config.get('config', {}).get('tone', 'neutral')}
- Style: {persona_config.get('config', {}).get('style', 'casual')}
- Values: {', '.join(persona_config.get('config', {}).get('values', []))}
"""

    # Format belief graph section
    beliefs = belief_graph.get('nodes', [])
    belief_text = "\nCurrent Beliefs:\n"
    for belief in beliefs[:15]:  # Limit to top 15
        belief_text += f"- ID: {belief['id']}, Title: {belief['title']}, Confidence: {belief['confidence']:.2f}\n"

    # Format interaction history section
    history_text = f"\nRecent Interactions (last {len(interaction_history)}):\n"
    for interaction in interaction_history[:10]:  # Limit to 10 most recent
        history_text += f"- [{interaction.get('created_at', 'unknown')}] {interaction.get('interaction_type', 'unknown')}: {interaction.get('content', '')[:100]}...\n"

    return GOVERNOR_SYSTEM_PROMPT.format(
        persona_config=persona_text,
        belief_graph=belief_text,
        interaction_history=history_text
    )
