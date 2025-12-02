"""Query classification for BAS/HVAC technical queries."""
from openai import OpenAI
import os
import json

CLASSIFICATION_PROMPT = """You are a BAS/HVAC technical documentation query classifier.

Classify the user's query into one or more of these categories:
- architecture: System design, multi-tier, network topology, VM layout, System Database
- graphics: UI, PX pages, navigation, displays, tag dictionaries, roll-ups
- provisioning: Bulk deployment, backup, restore, module distribution
- troubleshooting: Faults, alarms, diagnostics, error messages
- configuration: Point setup, device parameters, sequences, schedules, BQL, control logic
- hardware: Wiring, IO, installation, physical setup, sensors, JACE controllers
- hvac: HVAC equipment, AHU, VAV, chillers, boilers, sequences of operation
- energy: Energy management, demand response, load shedding, utilities, optimization
- integration: BACnet, Modbus, LON, OPC, protocol integration, third-party devices

Return ONLY a JSON array of category names (1-3 max).

Examples:
Query: "design multi-tier system with supervisors and VM graphics"
Output: ["architecture", "graphics"]

Query: "how to provision backups to multiple JACEs"
Output: ["provisioning"]

Query: "alarm shows low water error"
Output: ["troubleshooting"]

Now classify:
{query}

Output (JSON array):"""

CATEGORY_KEYWORDS = {
    'architecture': [
        'multi-tier', 'system database', 'virtual px', 'enterprise', 
        'supervisor network', 'topology', 'vm', 'host', 'station', 
        'jace network', 'multi tier', 'enterprise supervisor',
        'multiple supervisors', 'virtual machine', 'spans multiple',
        'rolls up to', 'system design', 'system architecture'
    ],
    'graphics': [
        'graphics', 'px', 'navigation', 'display', 'ui', 'view', 
        'tag dictionary', 'roll-up', 'navigation tree', 'wiresheet', 
        'design view', 'grahics', 'desgin'  # Common typos
    ],
    'provisioning': [
        'provision', 'backup', 'restore', 'job builder', 'bulk deploy', 
        'distribution', 'archive', 'bulk provision'
    ],
    'troubleshooting': [
        'alarm', 'error', 'fault', 'diagnostic', 'troubleshoot', 
        'symptom', 'fix', 'failed', 'issue', 'problem'
    ],
    'configuration': [
        'configure', 'setup', 'point', 'schedule', 'parameter', 
        'tuning', 'sequence', 'setpoint', 'config'
    ],
    'hardware': [
        'wiring', 'io', 'power', 'installation', 'sensor', 
        'actuator', 'physical', 'cable', 'termination', 'jace',
        'controller', 'device install'
    ],
    'hvac': [
        'hvac', 'ahu', 'air handler', 'vav', 'variable air volume',
        'fcu', 'fan coil', 'chiller', 'boiler', 'cooling tower',
        'vfd', 'fan', 'pump', 'damper', 'sequence of operation',
        'heating', 'cooling', 'ventilation', 'air flow', 'cfm'
    ],
    'energy': [
        'energy', 'demand', 'load shedding', 'utility', 'kwh', 'kw',
        'power consumption', 'energy optimization', 'demand response',
        'energy savings', 'meter', 'carbon', 'sustainability'
    ],
    'integration': [
        'bacnet', 'modbus', 'lonworks', 'lon', 'opc', 'protocol',
        'integration', 'third-party', 'gateway', 'driver',
        'point mapping', 'device driver', 'trend', 'historian'
    ]
}

def classify_query_llm(query: str) -> list[str]:
    """Classify query using GPT-4o-mini.
    
    Args:
        query: User's query text
        
    Returns:
        List of category names (e.g., ['architecture', 'graphics'])
    """
    client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a query classifier. Return only JSON arrays."},
                {"role": "user", "content": CLASSIFICATION_PROMPT.format(query=query)}
            ],
            temperature=0.0,
            max_tokens=50
        )
        
        categories = json.loads(response.choices[0].message.content.strip())
        
        # Validate output
        if not isinstance(categories, list):
            print(f"⚠️  LLM returned non-list: {categories}, falling back")
            return classify_query_keywords(query)
        
        # Filter to valid categories
        valid_categories = [
            cat for cat in categories 
            if cat in CATEGORY_KEYWORDS
        ]
        
        return valid_categories if valid_categories else ['configuration']
        
    except json.JSONDecodeError as e:
        print(f"⚠️  Classification JSON decode failed: {e}, falling back to keyword classifier")
        return classify_query_keywords(query)
    except Exception as e:
        print(f"⚠️  Classification failed: {e}, falling back to keyword classifier")
        return classify_query_keywords(query)

def classify_query_keywords(query: str) -> list[str]:
    """Classify using keyword matching (fallback).
    
    Args:
        query: User's query text
        
    Returns:
        List of category names based on keyword matching
    """
    query_lower = query.lower()
    categories = []
    
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(kw in query_lower for kw in keywords):
            categories.append(category)
    
    # Default to configuration if no matches
    return categories if categories else ['configuration']

def classify_query(query: str, use_llm: bool = True) -> list[str]:
    """Main classification function with fallback.
    
    Args:
        query: User's query text
        use_llm: Whether to use LLM classification (default: True)
        
    Returns:
        List of category names (1-3 max)
        
    Examples:
        >>> classify_query("design system with multiple supervisors")
        ['architecture']
        
        >>> classify_query("how to wire temperature sensor")
        ['hardware', 'configuration']
    """
    if use_llm and os.getenv('OPENAI_API_KEY'):
        return classify_query_llm(query)
    else:
        return classify_query_keywords(query)

# For backward compatibility and testing
if __name__ == "__main__":
    # Test queries
    test_queries = [
        "I need to design a system that spans multiple supervisors and rolls up to one virtual machine",
        "How to provision backup jobs across 50 JACE controllers",
        "Alarm shows boiler low water fault",
        "Configure VFD parameters for variable speed control",
        "Wiring diagram for temperature sensor"
    ]
    
    print("Testing Query Classifier:\n")
    for query in test_queries:
        categories = classify_query(query, use_llm=False)  # Use keywords for testing
        print(f"Query: {query[:60]}...")
        print(f"Categories: {categories}\n")
