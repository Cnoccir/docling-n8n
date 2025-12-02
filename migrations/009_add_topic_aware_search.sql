-- Migration 009: Add topic-aware search function
-- Purpose: Enable topic filtering and boosting in hybrid search
-- Date: 2024-11-29
-- Phase: Phase 3 of retrieval improvements

-- Drop existing function if exists
DROP FUNCTION IF EXISTS search_chunks_hybrid_with_topics;

-- Create topic-aware hybrid search function
CREATE OR REPLACE FUNCTION search_chunks_hybrid_with_topics(
    query_embedding vector(1536),
    query_text text,
    filter_doc_id text DEFAULT NULL,
    include_topics text[] DEFAULT NULL,  -- NEW: Topics to include
    exclude_topics text[] DEFAULT NULL,  -- NEW: Topics to exclude
    semantic_weight float DEFAULT 0.5,
    keyword_weight float DEFAULT 0.5,
    top_k int DEFAULT 10
)
RETURNS TABLE (
    id text,
    doc_id text,
    content text,
    page_number int,
    bbox jsonb,
    section_id text,
    parent_section_id text,
    section_path text[],
    section_level int,
    element_type text,
    metadata jsonb,
    topic text,          -- NEW
    topics text[],       -- NEW
    semantic_score float,
    keyword_score float,
    topic_boost float,   -- NEW: 1.0 (no boost) or 1.3 (matched topic)
    final_score float
) AS $$
BEGIN
    RETURN QUERY
    WITH vector_search AS (
        SELECT
            c.id,
            c.doc_id,
            c.content,
            c.page_number,
            c.bbox,
            c.section_id,
            c.parent_section_id,
            c.section_path,
            c.section_level,
            c.element_type,
            c.metadata,
            c.topic,
            c.topics,
            1 - (c.embedding <=> query_embedding) AS semantic_score,
            0.0::float AS keyword_score,
            -- NEW: Graduated topic boost (multi-topic scoring)
            CASE
                -- Strong boost: Multiple topic matches (2+ overlaps)
                WHEN include_topics IS NOT NULL AND 
                     cardinality(array(SELECT UNNEST(c.topics) INTERSECT SELECT UNNEST(include_topics))) >= 2 
                THEN 1.5::float
                -- Medium boost: Single topic match in array OR primary topic match
                WHEN include_topics IS NOT NULL AND 
                     (c.topics && include_topics OR c.topic = ANY(include_topics)) 
                THEN 1.3::float
                -- Weak boost: Related but not primary (future: add secondary topic map)
                -- No match: Normal ranking (1.0x - still searchable!)
                ELSE 1.0::float
            END AS topic_boost
        FROM chunks c
        WHERE
            (filter_doc_id IS NULL OR c.doc_id = filter_doc_id)
            -- REMOVED: Hard topic filters - use soft boosting instead
            -- Only exclude if explicitly requested (rarely used)
            AND (exclude_topics IS NULL OR NOT (c.topics && exclude_topics) AND (c.topic IS NULL OR NOT (c.topic = ANY(exclude_topics))))
        ORDER BY c.embedding <=> query_embedding
        LIMIT top_k * 2
    ),
    keyword_search AS (
        SELECT
            c.id,
            c.doc_id,
            c.content,
            c.page_number,
            c.bbox,
            c.section_id,
            c.parent_section_id,
            c.section_path,
            c.section_level,
            c.element_type,
            c.metadata,
            c.topic,
            c.topics,
            0.0::float AS semantic_score,
            ts_rank_cd(
                to_tsvector('english', c.content),
                plainto_tsquery('english', query_text)
            )::float AS keyword_score,
            -- NEW: Graduated topic boost (match vector_search logic)
            CASE
                WHEN include_topics IS NOT NULL AND 
                     cardinality(array(SELECT UNNEST(c.topics) INTERSECT SELECT UNNEST(include_topics))) >= 2 
                THEN 1.5::float
                WHEN include_topics IS NOT NULL AND 
                     (c.topics && include_topics OR c.topic = ANY(include_topics)) 
                THEN 1.3::float
                ELSE 1.0::float
            END AS topic_boost
        FROM chunks c
        WHERE
            (filter_doc_id IS NULL OR c.doc_id = filter_doc_id)
            AND to_tsvector('english', c.content) @@ plainto_tsquery('english', query_text)
            -- REMOVED: Hard filters - soft boosting only
            AND (exclude_topics IS NULL OR NOT (c.topics && exclude_topics) AND (c.topic IS NULL OR NOT (c.topic = ANY(exclude_topics))))
        ORDER BY keyword_score DESC
        LIMIT top_k * 2
    ),
    combined AS (
        SELECT * FROM vector_search
        UNION
        SELECT * FROM keyword_search
    ),
    scored AS (
        SELECT
            c.id,
            c.doc_id,
            c.content,
            c.page_number,
            c.bbox,
            c.section_id,
            c.parent_section_id,
            c.section_path,
            c.section_level,
            c.element_type,
            c.metadata,
            c.topic,
            c.topics,
            COALESCE(MAX(c.semantic_score), 0.0) AS max_semantic,
            COALESCE(MAX(c.keyword_score), 0.0) AS max_keyword,
            MAX(c.topic_boost) AS max_topic_boost,
            -- NEW: Apply topic boost to final score
            (
                (semantic_weight * COALESCE(MAX(c.semantic_score), 0.0) +
                 keyword_weight * COALESCE(MAX(c.keyword_score), 0.0))
                * MAX(c.topic_boost)
            )::float AS computed_score
        FROM combined c
        GROUP BY c.id, c.doc_id, c.content, c.page_number, c.bbox, c.section_id,
                 c.parent_section_id, c.section_path, c.section_level,
                 c.element_type, c.metadata, c.topic, c.topics
    )
    SELECT
        s.id,
        s.doc_id,
        s.content,
        s.page_number,
        s.bbox,
        s.section_id,
        s.parent_section_id,
        s.section_path,
        s.section_level,
        s.element_type,
        s.metadata,
        s.topic,
        s.topics,
        s.max_semantic AS semantic_score,
        s.max_keyword AS keyword_score,
        s.max_topic_boost AS topic_boost,
        s.computed_score AS final_score
    FROM scored s
    ORDER BY final_score DESC
    LIMIT top_k;
END;
$$ LANGUAGE plpgsql;

-- Add comments
COMMENT ON FUNCTION search_chunks_hybrid_with_topics IS 'Hybrid search with graduated topic boosting. Multi-topic matches get 1.5x, single matches 1.3x, no match 1.0x. NO HARD FILTERS - all content searchable.';

-- Verify function exists
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_proc 
        WHERE proname = 'search_chunks_hybrid_with_topics'
    ) THEN
        RAISE NOTICE '✅ Migration 009 completed successfully';
        RAISE NOTICE 'Created search_chunks_hybrid_with_topics function with topic support';
    ELSE
        RAISE EXCEPTION '❌ Migration 009 failed: function not created';
    END IF;
END $$;
