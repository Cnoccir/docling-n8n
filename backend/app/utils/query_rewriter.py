"""Query rewriting for domain-aware BAS/HVAC search."""
from openai import OpenAI
import os

REWRITE_PROMPT = """You are a BAS/HVAC technical documentation query rewriter.

Transform the user's query into a precise, keyword-rich search query. Follow these rules:
1. Fix typos and grammar
2. Expand abbreviations: VM → Virtual Machine, PX → Niagara PX graphics, JACE → JACE controller
3. Add technical context: "Niagara 4", "BAS/HVAC", "building automation"
4. Include domain keywords based on category:
   - architecture: "multi-tier", "System Database", "enterprise supervisor", "network topology", "virtual components"
   - graphics: "PX pages", "tag-based displays", "navigation tree", "tag dictionaries", "roll-ups"
   - provisioning: "bulk deployment", "job builder", "backup procedures", "restore operations"
   - troubleshooting: "diagnostics", "fault codes", "alarm conditions", "error resolution"
   - configuration: "point configuration", "schedules", "parameters", "sequences"
5. Remove conversational fluff: "I need", "help me", "please", "can you"
6. Keep under 100 words

Original: "{query}"
Categories: {categories}

Rewritten query:"""

def rewrite_query(query: str, categories: list[str]) -> str:
    """Rewrite query to be more domain-aware.
    
    Args:
        query: Original user query
        categories: List of detected categories (from classifier)
        
    Returns:
        Rewritten, keyword-rich query
        
    Examples:
        >>> rewrite_query("supervisrs and VM graphics", ['architecture', 'graphics'])
        "Niagara 4 multi-tier architecture with JACE supervisors..."
    """
    client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a technical query rewriter. Return only the rewritten query."},
                {"role": "user", "content": REWRITE_PROMPT.format(query=query, categories=categories)}
            ],
            temperature=0.2,
            max_tokens=150
        )
        
        rewritten = response.choices[0].message.content.strip()
        
        # Remove quotes if LLM wrapped it
        if rewritten.startswith('"') and rewritten.endswith('"'):
            rewritten = rewritten[1:-1]
        if rewritten.startswith("'") and rewritten.endswith("'"):
            rewritten = rewritten[1:-1]
        
        # Basic validation: ensure rewrite is not empty or too short
        if len(rewritten) < 10:
            print(f"⚠️  Rewrite too short: '{rewritten}', using original")
            return query
        
        return rewritten
        
    except Exception as e:
        print(f"⚠️  Query rewrite failed: {e}, using original")
        return query

def rewrite_query_simple(query: str, categories: list[str]) -> str:
    """Simple rule-based query expansion (fallback/non-LLM option).
    
    Args:
        query: Original user query
        categories: List of detected categories
        
    Returns:
        Expanded query with domain terms
    """
    # Fix common typos
    typo_map = {
        'supervisrs': 'supervisors',
        'grahics': 'graphics',
        'desgin': 'design',
        'confgure': 'configure'
    }
    
    expanded = query
    for typo, correct in typo_map.items():
        expanded = expanded.replace(typo, correct)
    
    # Add domain context based on categories
    domain_terms = []
    
    if 'architecture' in categories:
        domain_terms.extend(['multi-tier', 'System Database', 'enterprise supervisor'])
    if 'graphics' in categories:
        domain_terms.extend(['PX pages', 'navigation tree', 'tag-based displays'])
    if 'provisioning' in categories:
        domain_terms.extend(['bulk deployment', 'job builder', 'backup procedures'])
    if 'troubleshooting' in categories:
        domain_terms.extend(['diagnostics', 'fault codes', 'alarm conditions'])
    if 'configuration' in categories:
        domain_terms.extend(['point configuration', 'schedules', 'parameters'])
    if 'hardware' in categories:
        domain_terms.extend(['wiring', 'installation', 'IO configuration'])
    
    # Combine
    if domain_terms:
        expanded = f"{expanded} Niagara BAS/HVAC {' '.join(domain_terms[:3])}"
    
    return expanded

# For testing
if __name__ == "__main__":
    test_cases = [
        ("I need to design a system that spans multiple supervisrs and rolls up to one virtual machine", ['architecture']),
        ("how to desgin grahics", ['graphics']),
        ("bulk deploy to many controllers", ['provisioning'])
    ]
    
    print("Testing Query Rewriter (simple mode):\n")
    for query, categories in test_cases:
        rewritten = rewrite_query_simple(query, categories)
        print(f"Original:  {query}")
        print(f"Categories: {categories}")
        print(f"Rewritten: {rewritten}\n")
