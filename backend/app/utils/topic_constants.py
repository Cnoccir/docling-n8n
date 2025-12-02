"""Topic mapping constants - shared across modules to avoid circular imports."""

# Map query categories to topic filters
CATEGORY_TO_TOPIC_MAP = {
    'architecture': ['system_database', 'multi_tier_architecture'],
    'graphics': ['graphics'],
    'provisioning': ['provisioning'],
    'troubleshooting': ['troubleshooting'],
    'configuration': ['configuration'],
    'hardware': ['hardware'],
    'hvac': ['hvac_systems'],
    'energy': ['energy_management'],
    'integration': ['integration']
}
