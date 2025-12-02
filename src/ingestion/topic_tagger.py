"""Auto-tag chunks with topics during ingestion."""
from openai import OpenAI
import os
import json

TOPIC_TAGGING_PROMPT = """Classify this Niagara/BAS technical content into topic(s):

Topics:
- system_database: System Database concepts, shared data, station coordination
- multi_tier_architecture: Multi-tier design, JACE networks, enterprise supervisor, VM topology
- graphics: PX pages, navigation, displays, tag dictionaries, UI design
- provisioning: Backup, bulk deployment, job builder, restore, archive
- troubleshooting: Alarms, faults, diagnostics, error codes
- configuration: Point setup, schedules, parameters, sequences, tuning, BQL, control logic
- hardware: Wiring, IO, sensors, installation, physical components, JACE, protocols
- hvac_systems: AHU, VAV, FCU, boilers, chillers, HVAC equipment, sequences of operation
- energy_management: Energy optimization, demand response, load shedding, utilities
- integration: BACnet, Modbus, LON, OPC, protocol integration, third-party devices
- other: General information not fitting above

Section: {section_title}

Content:
{content}

Return JSON array of relevant topics (1-3 max). Example: ["system_database", "multi_tier_architecture"]

Output:"""

TOPIC_RULES = {
    'system_database': [
        'system database', 'system db', 'station database', 'shared database', 
        'db sync', 'database synchronization', 'station coordination', 'sysdb',
        'history sync', 'shared history', 'station sync', 'data replication'
    ],
    'multi_tier_architecture': [
        'multi-tier', 'multi tier', 'enterprise supervisor', 'virtual px', 
        'vm', 'supervisor network', 'jace network', 'topology', 'network architecture',
        'tiered architecture', 'hierarchical network', 'supervisor station',
        'jace-to-supervisor', 'supervisor-to-jace', 'niagara network', 'enterprise network',
        'multiple supervisors', 'multiple stations', 'network design', 'site architecture'
    ],
    'graphics': [
        'px', 'graphics', 'navigation', 'display', 'view', 'tag dictionary', 
        'wiresheet', 'roll-up', 'navigation tree', 'ui', 'user interface',
        'visual', 'dashboard', 'hmi', 'graphic design', 'tag-based', 'px page',
        'visualization', 'display design', 'navigation design', 'graphic template',
        'web profile', 'web graphics', 'tag reference', 'dynamic graphics'
    ],
    'provisioning': [
        'provision', 'backup', 'restore', 'job builder', 'bulk', 
        'distribution', 'archive', 'deploy', 'deployment', 'module distribution',
        'station backup', 'archive manager', 'bulk operations', 'station restore',
        'snapshot', 'rollback', 'configuration backup', 'system restore'
    ],
    'troubleshooting': [
        'alarm', 'fault', 'error', 'diagnostic', 'troubleshoot', 
        'issue', 'symptom', 'debug', 'problem', 'failure', 'alarm routing',
        'fault detection', 'error code', 'diagnosis', 'alarm analysis',
        'fault condition', 'system error', 'alarm notification', 'fault message'
    ],
    'configuration': [
        'configure', 'schedule', 'parameter', 'point', 'setpoint', 
        'tuning', 'sequence', 'setup', 'setting', 'config', 'control logic',
        'pid tuning', 'point configuration', 'parameter setup', 'control strategy',
        'scheduling', 'setpoint adjustment', 'point setup', 'logic configuration',
        'bql', 'control program', 'program logic', 'logic editor'
    ],
    'hardware': [
        'wiring', 'io', 'sensor', 'actuator', 'power', 
        'installation', 'termination', 'physical', 'cable', 'connector',
        'jace', 'controller', 'hardware install', 'device installation',
        'i/o module', 'analog input', 'digital output', 'universal input',
        'communication module', 'network adapter',
        'power supply', 'battery backup', 'din rail', 'enclosure',
        'field device', 'controller installation', 'device commissioning'
    ],
    'hvac_systems': [
        'ahu', 'air handler', 'air handling unit', 'vav', 'variable air volume',
        'fcu', 'fan coil', 'chiller', 'boiler', 'heat exchanger',
        'cooling tower', 'hvac', 'heating', 'ventilation', 'cooling',
        'damper', 'vfd', 'variable frequency drive', 'fan', 'pump',
        'sequence of operation', 'hvac sequence', 'equipment schedule',
        'psychrometric', 'enthalpy', 'static pressure', 'cfm', 'air flow',
        'discharge air', 'return air', 'supply air', 'exhaust',
        'economizer', 'heat recovery', 'energy recovery'
    ],
    'energy_management': [
        'energy', 'demand', 'load shedding', 'peak demand', 'utility',
        'kw demand', 'kwh', 'power consumption', 'energy optimization',
        'demand response', 'load control', 'energy savings',
        'power monitoring', 'energy meter', 'submeter', 'utility meter',
        'carbon', 'emissions', 'sustainability', 'green building',
        'leed', 'energy star', 'benchmarking'
    ],
    'integration': [
        'bacnet', 'modbus', 'lonworks', 'lon', 'opc', 'snmp',
        'protocol', 'integration', 'third-party', 'gateway',
        'driver', 'device driver', 'network discovery',
        'point mapping', 'device integration', 'protocol conversion',
        'bacnet ms/tp', 'bacnet ip', 'modbus rtu', 'modbus tcp',
        'lonmark', 'lon network', 'opc ua', 'opc da',
        'trend', 'data logging', 'historian', 'data export'
    ]
}

class TopicTagger:
    """Tag chunks with topics using LLM or rules."""
    
    def __init__(self, use_llm: bool = True):
        """Initialize topic tagger.
        
        Args:
            use_llm: Whether to use LLM classification (requires OPENAI_API_KEY)
        """
        self.use_llm = use_llm and os.getenv('OPENAI_API_KEY')
        if self.use_llm:
            self.client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        
        print(f"💡 TopicTagger initialized (mode: {'LLM' if self.use_llm else 'rules-based'})")
    
    def tag_chunk_llm(self, content: str, section_title: str) -> list[str]:
        """Tag using GPT-4o-mini.
        
        Args:
            content: Chunk text content
            section_title: Title of parent section
            
        Returns:
            List of topic names (e.g., ['system_database', 'multi_tier_architecture'])
        """
        # Use section title + first 500 chars for context
        context = content[:500]
        
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a topic tagger. Return only JSON arrays."},
                    {"role": "user", "content": TOPIC_TAGGING_PROMPT.format(
                        section_title=section_title,
                        content=context
                    )}
                ],
                temperature=0.0,
                max_tokens=30
            )
            
            topics = json.loads(response.choices[0].message.content.strip())
            
            # Validate output
            if not isinstance(topics, list):
                print(f"⚠️  LLM returned non-list: {topics}, falling back to rules")
                return self.tag_chunk_rules(content, section_title)
            
            # Filter to valid topics
            valid_topics = [t for t in topics if t in TOPIC_RULES or t == 'other']
            
            return valid_topics if valid_topics else self.tag_chunk_rules(content, section_title)
            
        except json.JSONDecodeError as e:
            print(f"⚠️  LLM tagging JSON decode failed: {e}, using rules")
            return self.tag_chunk_rules(content, section_title)
        except Exception as e:
            print(f"⚠️  LLM tagging failed: {e}, using rules")
            return self.tag_chunk_rules(content, section_title)
    
    def tag_chunk_rules(self, content: str, section_title: str) -> list[str]:
        """Tag using keyword rules.
        
        Args:
            content: Chunk text content
            section_title: Title of parent section
            
        Returns:
            List of topic names based on keyword matching
        """
        text = (section_title + " " + content).lower()
        topics = []
        
        for topic, keywords in TOPIC_RULES.items():
            if any(kw in text for kw in keywords):
                topics.append(topic)
        
        return topics if topics else ['other']
    
    def tag_chunk(self, content: str, section_title: str) -> list[str]:
        """Main tagging function.
        
        Args:
            content: Chunk text content
            section_title: Title of parent section
            
        Returns:
            List of topic names
        """
        if self.use_llm:
            return self.tag_chunk_llm(content, section_title)
        else:
            return self.tag_chunk_rules(content, section_title)
    
    def tag_chunks_batch(self, chunks: list[dict]) -> dict[str, list[str]]:
        """Tag multiple chunks efficiently.
        
        Args:
            chunks: List of chunk dicts with 'id', 'content', 'section_title' keys
            
        Returns:
            Dictionary mapping chunk IDs to topic lists
        """
        results = {}
        
        for i, chunk in enumerate(chunks):
            if (i + 1) % 10 == 0:
                print(f"   Tagged {i + 1}/{len(chunks)} chunks...")
            
            topics = self.tag_chunk(
                chunk.get('content', ''), 
                chunk.get('section_title', 'Unknown')
            )
            results[chunk['id']] = topics
        
        return results

# For testing
if __name__ == "__main__":
    test_chunks = [
        {
            'id': 'chunk_001',
            'section_title': 'System Database Architecture',
            'content': 'The System Database allows coordination across multiple stations in a multi-tier Niagara network. Virtual PX components can be shared between enterprise supervisors and local JACE controllers.'
        },
        {
            'id': 'chunk_002',
            'section_title': 'Backup Procedures',
            'content': 'To provision backups across multiple stations, use the Job Builder tool. Create a backup job and distribute it to all JACE controllers in the network.'
        },
        {
            'id': 'chunk_003',
            'section_title': 'Graphics Design',
            'content': 'PX pages use tag dictionaries for navigation. Create a navigation tree with roll-ups to display data from multiple devices in a single view.'
        }
    ]
    
    print("Testing Topic Tagger (rules-based mode):\n")
    tagger = TopicTagger(use_llm=False)
    
    for chunk in test_chunks:
        topics = tagger.tag_chunk(chunk['content'], chunk['section_title'])
        print(f"Section: {chunk['section_title']}")
        print(f"Topics:  {topics}")
        print()
