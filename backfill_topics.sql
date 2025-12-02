-- Backfill topics for existing chunks based on content analysis
-- This simulates what TopicTagger would have done during ingestion

-- Update chunks with system_database topic
UPDATE chunks
SET 
    topic = 'system_database',
    topics = ARRAY['system_database']
WHERE 
    (LOWER(content) LIKE '%system database%' 
     OR LOWER(content) LIKE '%system db%'
     OR LOWER(content) LIKE '%station database%'
     OR LOWER(content) LIKE '%shared database%')
    AND topic IS NULL;

-- Update chunks with multi_tier_architecture topic
UPDATE chunks
SET 
    topic = CASE 
        WHEN topic IS NULL THEN 'multi_tier_architecture'
        ELSE topic
    END,
    topics = CASE
        WHEN 'system_database' = ANY(topics) THEN array_append(topics, 'multi_tier_architecture')
        WHEN topic IS NULL THEN ARRAY['multi_tier_architecture']
        ELSE topics
    END
WHERE 
    (LOWER(content) LIKE '%multi-tier%'
     OR LOWER(content) LIKE '%multi tier%'
     OR LOWER(content) LIKE '%enterprise supervisor%'
     OR LOWER(content) LIKE '%virtual px%'
     OR LOWER(content) LIKE '%supervisor network%'
     OR LOWER(content) LIKE '%jace network%');

-- Update chunks with graphics topic
UPDATE chunks
SET 
    topic = CASE 
        WHEN topic IS NULL THEN 'graphics'
        ELSE topic
    END,
    topics = CASE
        WHEN array_length(topics, 1) > 0 THEN array_append(topics, 'graphics')
        WHEN topic IS NULL THEN ARRAY['graphics']
        ELSE topics
    END
WHERE 
    (LOWER(content) LIKE '%graphics%'
     OR LOWER(content) LIKE '% px %'
     OR LOWER(content) LIKE '%navigation%'
     OR LOWER(content) LIKE '%display%'
     OR LOWER(content) LIKE '%view%'
     OR LOWER(content) LIKE '%tag dictionary%'
     OR LOWER(content) LIKE '%wiresheet%')
    AND NOT ('graphics' = ANY(topics));

-- Update chunks with provisioning topic
UPDATE chunks
SET 
    topic = CASE 
        WHEN topic IS NULL THEN 'provisioning'
        ELSE topic
    END,
    topics = CASE
        WHEN array_length(topics, 1) > 0 THEN array_append(topics, 'provisioning')
        WHEN topic IS NULL THEN ARRAY['provisioning']
        ELSE topics
    END
WHERE 
    (LOWER(content) LIKE '%provision%'
     OR LOWER(content) LIKE '%backup%'
     OR LOWER(content) LIKE '%restore%'
     OR LOWER(content) LIKE '%job builder%'
     OR LOWER(content) LIKE '%archive%'
     OR LOWER(content) LIKE '%deploy%')
    AND NOT ('provisioning' = ANY(topics));

-- Update chunks with troubleshooting topic
UPDATE chunks
SET 
    topic = CASE 
        WHEN topic IS NULL THEN 'troubleshooting'
        ELSE topic
    END,
    topics = CASE
        WHEN array_length(topics, 1) > 0 THEN array_append(topics, 'troubleshooting')
        WHEN topic IS NULL THEN ARRAY['troubleshooting']
        ELSE topics
    END
WHERE 
    (LOWER(content) LIKE '%alarm%'
     OR LOWER(content) LIKE '%fault%'
     OR LOWER(content) LIKE '%error%'
     OR LOWER(content) LIKE '%diagnostic%'
     OR LOWER(content) LIKE '%troubleshoot%')
    AND NOT ('troubleshooting' = ANY(topics));

-- Update chunks with configuration topic
UPDATE chunks
SET 
    topic = CASE 
        WHEN topic IS NULL THEN 'configuration'
        ELSE topic
    END,
    topics = CASE
        WHEN array_length(topics, 1) > 0 THEN array_append(topics, 'configuration')
        WHEN topic IS NULL THEN ARRAY['configuration']
        ELSE topics
    END
WHERE 
    (LOWER(content) LIKE '%configure%'
     OR LOWER(content) LIKE '%setup%'
     OR LOWER(content) LIKE '%parameter%'
     OR LOWER(content) LIKE '%setting%'
     OR LOWER(content) LIKE '%config%')
    AND NOT ('configuration' = ANY(topics));

-- Update chunks with HVAC systems topic
UPDATE chunks
SET 
    topic = CASE 
        WHEN topic IS NULL THEN 'hvac_systems'
        ELSE topic
    END,
    topics = CASE
        WHEN array_length(topics, 1) > 0 THEN array_append(topics, 'hvac_systems')
        WHEN topic IS NULL THEN ARRAY['hvac_systems']
        ELSE topics
    END
WHERE 
    (LOWER(content) LIKE '%ahu%'
     OR LOWER(content) LIKE '%air handler%'
     OR LOWER(content) LIKE '%vav%'
     OR LOWER(content) LIKE '%variable air volume%'
     OR LOWER(content) LIKE '%fcu%'
     OR LOWER(content) LIKE '%fan coil%'
     OR LOWER(content) LIKE '%chiller%'
     OR LOWER(content) LIKE '%boiler%'
     OR LOWER(content) LIKE '%cooling tower%'
     OR LOWER(content) LIKE '%vfd%'
     OR LOWER(content) LIKE '%sequence of operation%'
     OR LOWER(content) LIKE '%discharge air%'
     OR LOWER(content) LIKE '%supply air%')
    AND NOT ('hvac_systems' = ANY(topics));

-- Update chunks with energy management topic
UPDATE chunks
SET 
    topic = CASE 
        WHEN topic IS NULL THEN 'energy_management'
        ELSE topic
    END,
    topics = CASE
        WHEN array_length(topics, 1) > 0 THEN array_append(topics, 'energy_management')
        WHEN topic IS NULL THEN ARRAY['energy_management']
        ELSE topics
    END
WHERE 
    (LOWER(content) LIKE '%energy%'
     OR LOWER(content) LIKE '%demand%'
     OR LOWER(content) LIKE '%load shedding%'
     OR LOWER(content) LIKE '%utility%'
     OR LOWER(content) LIKE '%kwh%'
     OR LOWER(content) LIKE '% kw %'
     OR LOWER(content) LIKE '%power consumption%'
     OR LOWER(content) LIKE '%energy savings%'
     OR LOWER(content) LIKE '%meter%')
    AND NOT ('energy_management' = ANY(topics));

-- Update chunks with integration topic
UPDATE chunks
SET 
    topic = CASE 
        WHEN topic IS NULL THEN 'integration'
        ELSE topic
    END,
    topics = CASE
        WHEN array_length(topics, 1) > 0 THEN array_append(topics, 'integration')
        WHEN topic IS NULL THEN ARRAY['integration']
        ELSE topics
    END
WHERE 
    (LOWER(content) LIKE '%bacnet%'
     OR LOWER(content) LIKE '%modbus%'
     OR LOWER(content) LIKE '%lonworks%'
     OR LOWER(content) LIKE '% lon %'
     OR LOWER(content) LIKE '%opc%'
     OR LOWER(content) LIKE '%protocol%'
     OR LOWER(content) LIKE '%device driver%'
     OR LOWER(content) LIKE '%point mapping%'
     OR LOWER(content) LIKE '%historian%')
    AND NOT ('integration' = ANY(topics));

-- Set 'other' for chunks still without topics
UPDATE chunks
SET 
    topic = 'other',
    topics = ARRAY['other']
WHERE topic IS NULL;

-- Show summary
SELECT 
    topic,
    COUNT(*) as count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 1) as percentage
FROM chunks
WHERE topic IS NOT NULL
GROUP BY topic
ORDER BY count DESC;
