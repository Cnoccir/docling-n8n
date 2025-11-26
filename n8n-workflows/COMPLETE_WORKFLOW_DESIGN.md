# Complete Enhanced RAG Workflow - Full Technical Specification

## Architecture Overview

### Full Execution Path (All 6 Improvements)

```
┌─────────────────────────────────────────────────────────────────┐
│ PHASE 1: QUERY INTAKE & VALIDATION                             │
└─────────────────────────────────────────────────────────────────┘

1. Webhook (Receive Query)
   ↓
2. Query Analyzer (Intent + Characteristics)
   ↓
3. Query Validator ← NEW
   ├─ Vague/Ambiguous? → Clarification Response → END (Loop back with refined query)
   └─ Valid → Continue
   ↓
4. Conversation State Manager ← NEW
   - Load conversation history
   - Merge with current context
   - Build refined query with conversation context

┌─────────────────────────────────────────────────────────────────┐
│ PHASE 2: MULTI-QUERY SEARCH & FUSION                           │
└─────────────────────────────────────────────────────────────────┘

5. Multi-Query Generator ← NEW
   - Generates 5 query variations using LLM
   ↓
6. Parallel Multi-Search ← NEW
   - Executes 5 hybrid searches in parallel
   - Each returns top 50 candidates
   ↓
7. Reciprocal Rank Fusion ← NEW
   - Combines all results
   - Scores based on rank positions across queries
   - Returns top 50 fused candidates

┌─────────────────────────────────────────────────────────────────┐
│ PHASE 3: RERANKING & VERIFICATION                              │
└─────────────────────────────────────────────────────────────────┘

8. Cross-Encoder Reranking ← NEW
   - Rescores top 50 using Cohere Rerank API
   - Returns TRUE top 15
   ↓
9. Extract Golden Chunks
   - Top 10 = golden chunks (best matches)
   - Remaining 5 = backup candidates
   ↓
10. Context Validator ← NEW
    ├─ System Consistency Check
    ├─ Semantic Coherence Check
    ├─ Mixed Systems? → Ask User Clarification → END (Loop back)
    └─ Valid → Continue

┌─────────────────────────────────────────────────────────────────┐
│ PHASE 4: CONTEXT EXPANSION & GENERATION                        │
└─────────────────────────────────────────────────────────────────┘

11. Context Expansion
    - Hierarchy-based expansion
    - Auto-retrieve images + tables
    ↓
12. Merge Results
    - Combine expanded chunks
    - Extract images/tables
    - Format for LLM
    ↓
13. Answer Generator
    - Golden chunks priority
    - Full context awareness
    ↓
14. Answer Validator ← NEW
    - Verify answer addresses query
    - Check for hallucinations
    - Ensure citations present
    ↓
15. Update Conversation State ← NEW
    - Store query + answer
    - Track document context
    ↓
16. Format Response
    ↓
17. Respond to Webhook
```

## Node-by-Node Implementation

### NODE 1: Webhook
**Type:** n8n-nodes-base.webhook
**Purpose:** Receive incoming query
**Input:**
```json
{
  "query": "How to configure PID loop?",
  "conversation_id": "uuid-optional",
  "doc_id": "kitcontrol_manual-optional",
  "user_id": "user123",
  "username": "Raymond"
}
```

### NODE 2: Query Analyzer
**Type:** n8n-nodes-base.code
**Purpose:** Analyze query characteristics

```javascript
const body = $input.first().json.body || $input.first().json;
const query = body.query || body.chatInput || '';
const conversation_id = body.conversation_id || null;

// Intent detection
const isGreeting = /^(hi|hello|hey|good morning|good afternoon)/i.test(query.trim());

// Characteristic detection
const hasTechnicalTerms = /\b(span|block|gpm|pump|valve|sensor|controller|wire|wiring|component|module|analog|digital|bacnet|niagara|kitcontrol|honeywell|pid|loop|setpoint|damper|actuator|point|extension)\b/i.test(query);
const wantsVisuals = /\b(show|image|diagram|picture|visual|schematic|wiring|drawing|illustration|graphic)\b/i.test(query) || /wir(e|ing)/i.test(query);
const wantsDetails = /\b(detailed|spec|specification|table|parameter|configuration|breakdown|setting|value)\b/i.test(query);

// Query complexity
const wordCount = query.split(/\s+/).length;
const isVeryShort = wordCount < 3;
const isShort = wordCount < 5;

return [{
  json: {
    query,
    conversation_id,
    isGreeting,
    hasTechnicalTerms,
    wantsVisuals,
    wantsDetails,
    wordCount,
    isVeryShort,
    isShort,
    doc_id: body.doc_id || null,
    user_id: body.user_id || body.userId || 'anonymous',
    username: body.username || 'User'
  }
}];
```

### NODE 3: Is Greeting?
**Type:** n8n-nodes-base.if
**Condition:** `{{ $json.isGreeting }} === true`
**True Path:** Greeting Response → END
**False Path:** Query Validator

### NODE 4: Query Validator ← NEW
**Type:** n8n-nodes-base.code
**Purpose:** Validate query specificity and detect ambiguity

```javascript
const analyzer = $input.first().json;
const query = analyzer.query;
const issues = [];
const suggestions = [];

// Check 1: Vague pronouns without context
const vaguePronounPattern = /\b(it|this|that|they|these|those)\b/i;
if (vaguePronounPattern.test(query) && analyzer.wordCount < 8) {
  issues.push({
    type: 'vague_pronoun',
    severity: 'high',
    message: 'Your query contains pronouns like "it" or "this" without clear context.'
  });
  suggestions.push('Please specify what component or system you\'re referring to');
  suggestions.push('Example: Instead of "How does it work?" try "How does the KitControl PID loop work?"');
}

// Check 2: Very short queries without technical terms
if (analyzer.isVeryShort && !analyzer.hasTechnicalTerms) {
  issues.push({
    type: 'too_vague',
    severity: 'high',
    message: 'Your query is very short and lacks technical details.'
  });
  suggestions.push('Please provide more context about what you need help with');
  suggestions.push('What system are you working with? (KitControl, BACnet, Niagara, etc.)');
  suggestions.push('What specific task are you trying to accomplish?');
}

// Check 3: Ambiguous technical terms
const ambiguousTerms = {
  'pump': ['Which type of pump?', 'Examples: circulation pump, heat pump, condensate pump, water pump'],
  'valve': ['Which type of valve?', 'Examples: control valve, modulating valve, solenoid valve, ball valve'],
  'sensor': ['Which type of sensor?', 'Examples: temperature sensor, pressure sensor, humidity sensor, flow sensor'],
  'loop': ['Which type of loop?', 'Examples: PID loop, control loop, feedback loop, HVAC loop'],
  'point': ['Which type of point?', 'Examples: analog point, digital point, control point, setpoint'],
  'controller': ['Which controller?', 'Examples: KitControl, BACnet controller, DDC controller'],
  'output': ['Which output?', 'Examples: analog output, digital output, control output, AO, DO']
};

for (const [term, hints] of Object.entries(ambiguousTerms)) {
  const termRegex = new RegExp(`\\b${term}\\b`, 'i');
  // Check if term is present but no specifier like "which", "what type", or specific type name
  if (termRegex.test(query) &&
      !query.match(/\b(which|what type|what kind|pid|analog|digital|control|modulating|temperature|pressure|humidity|flow)\b/i)) {
    issues.push({
      type: 'ambiguous_term',
      severity: 'medium',
      term: term,
      message: hints[0]
    });
    suggestions.push(hints[1]);
  }
}

// Check 4: Missing action/intent
const hasAction = /\b(how|configure|wire|install|setup|troubleshoot|connect|set|adjust|calibrate|test|check|diagnose|repair|replace)\b/i.test(query);
const hasQuestion = /\b(what|where|when|why|which|who)\b/i.test(query) || query.includes('?');

if (!hasAction && !hasQuestion && analyzer.wordCount < 6) {
  issues.push({
    type: 'unclear_intent',
    severity: 'medium',
    message: 'It\'s unclear what you want to know or do.'
  });
  suggestions.push('Try phrasing as a question or describing what you want to accomplish');
  suggestions.push('Examples: "How to...", "What is...", "Where can I find..."');
}

// Determine if clarification is needed
const needsClarification = issues.filter(i => i.severity === 'high').length > 0;

return [{
  json: {
    ...analyzer,
    validation: {
      needs_clarification: needsClarification,
      issues,
      suggestions,
      validated_query: query
    }
  }
}];
```

### NODE 5: Needs Clarification?
**Type:** n8n-nodes-base.if
**Condition:** `{{ $json.validation.needs_clarification }} === true`
**True Path:** Clarification Response → END
**False Path:** Conversation State Manager

**Clarification Response Node:**
```javascript
const data = $input.first().json;
const validation = data.validation;

return [{
  json: {
    answer: "I need more information to provide an accurate answer.",
    clarification_needed: true,
    original_query: data.query,
    issues: validation.issues,
    suggestions: validation.suggestions,
    helpful_examples: [
      "How to configure KitControl PID loop for temperature control?",
      "What are the wiring specifications for analog output to pump?",
      "Show me the diagram for BACnet network topology",
      "Where is the setpoint parameter in the loop configuration?"
    ],
    metadata: {
      timestamp: new Date().toISOString(),
      queryType: 'clarification_request',
      user_id: data.user_id,
      username: data.username
    }
  }
}];
```

### NODE 6: Conversation State Manager ← NEW
**Type:** n8n-nodes-base.code
**Purpose:** Load and manage conversation context

```javascript
const data = $input.first().json;
const query = data.query;
const conversation_id = data.conversation_id;
const doc_id = data.doc_id;

// For now, we'll use simple in-memory state
// In production, this would query a database/Redis

const conversationContext = {
  id: conversation_id || `conv_${Date.now()}`,
  user_id: data.user_id,
  current_doc: doc_id,
  previous_queries: [],  // Would load from DB
  accumulated_context: {
    detected_system: null,  // e.g., "kitcontrol", "bacnet"
    detected_topic: null,   // e.g., "pid_loop", "wiring"
    relevant_sections: []
  }
};

// Build enhanced query with conversation context
let enhanced_query = query;
if (conversationContext.accumulated_context.detected_system) {
  enhanced_query = `${conversationContext.accumulated_context.detected_system} ${query}`;
}

return [{
  json: {
    ...data,
    conversation: conversationContext,
    enhanced_query: enhanced_query,
    search_params: {
      top_k: data.wantsDetails ? 50 : 50,  // Always get 50 for fusion
      fts_weight: data.hasTechnicalTerms ? 0.6 : 0.4,
      vector_weight: data.hasTechnicalTerms ? 0.4 : 0.6
    }
  }
}];
```

### NODE 7: Multi-Query Generator ← NEW
**Type:** @n8n/n8n-nodes-langchain.chainLlm
**Purpose:** Generate 5 query variations for comprehensive search

**Prompt:**
```
You are a technical documentation search expert. Generate 5 alternative search queries for the following technical query.

Original Query: "{{ $json.enhanced_query }}"

Requirements:
1. Use different technical terminology and synonyms
2. Focus on different aspects: configuration, wiring, troubleshooting, specifications, installation
3. Include related technical terms and component names
4. Maintain technical accuracy
5. Each query should be 5-15 words

Return ONLY a JSON array (no markdown, no explanation):
["query1", "query2", "query3", "query4", "query5"]

Examples:

Original: "How to configure PID loop for temperature control?"
Output: [
  "pid loop temperature control configuration settings parameters",
  "proportional integral derivative loop setup temperature sensor",
  "configure loop point temperature control setpoint tuning",
  "pid controller temperature regulation configuration guide",
  "loop configuration temperature control proportional gain integral"
]

Now generate 5 variations for the query above:
```

**Model:** gpt-4o-mini (fast, cheap, good enough for this task)
**Temperature:** 0.5
**Max Tokens:** 300

### NODE 8: Parse Multi-Query Output
**Type:** n8n-nodes-base.code
**Purpose:** Extract query array from LLM response

```javascript
const llmOutput = $input.first().json;
const originalData = $('6. Conversation State Manager').first().json;

let queries = [];

// Handle different LLM response formats
if (llmOutput.response) {
  const responseText = llmOutput.response;
  // Try to extract JSON array
  const jsonMatch = responseText.match(/\[[\s\S]*\]/);
  if (jsonMatch) {
    try {
      queries = JSON.parse(jsonMatch[0]);
    } catch (e) {
      // Fallback: use original query 5 times
      queries = [originalData.enhanced_query].concat(
        Array(4).fill(originalData.enhanced_query)
      );
    }
  }
} else if (Array.isArray(llmOutput)) {
  queries = llmOutput;
}

// Ensure we have exactly 5 queries
if (queries.length < 5) {
  while (queries.length < 5) {
    queries.push(originalData.enhanced_query);
  }
} else if (queries.length > 5) {
  queries = queries.slice(0, 5);
}

return [{
  json: {
    ...originalData,
    query_variations: queries,
    multi_query_debug: {
      original_query: originalData.enhanced_query,
      generated_count: queries.length
    }
  }
}];
```

### NODE 9: Parallel Multi-Search ← NEW
**Type:** n8n-nodes-base.code
**Purpose:** Execute 5 hybrid searches in parallel

**IMPORTANT:** This node will output 5 items (one per query), which n8n will handle automatically.

```javascript
const data = $input.first().json;
const queries = data.query_variations;
const searchParams = data.search_params;
const doc_ids = data.doc_id ? [data.doc_id] : null;

// Return 5 items, n8n will execute HTTP requests in parallel
return queries.map((query, index) => ({
  json: {
    query: query,
    query_index: index,
    doc_ids: doc_ids,
    top_k: searchParams.top_k,
    fts_weight: searchParams.fts_weight,
    vector_weight: searchParams.vector_weight,
    original_data: data  // Pass through for later nodes
  }
}));
```

### NODE 10: Execute Hybrid Search (Parallel)
**Type:** n8n-nodes-base.httpRequest
**Purpose:** Execute hybrid search for each query variation
**Executes:** 5 times in parallel (one for each item from previous node)

```
Method: POST
URL: https://dwisbglrutplhcotbehy.supabase.co/functions/v1/hybrid-search
Body: {{ JSON.stringify({
  query: $json.query,
  doc_ids: $json.doc_ids,
  top_k: $json.top_k,
  fts_weight: $json.fts_weight,
  vector_weight: $json.vector_weight
}) }}
```

**Output:** 5 separate items, each with search results

### NODE 11: Reciprocal Rank Fusion ← NEW
**Type:** n8n-nodes-base.code
**Purpose:** Combine and rerank all search results

```javascript
// Collect all search results from parallel execution
const allSearchResults = $input.all();
const originalData = allSearchResults[0].json.original_data;

// Extract chunks from each query's results
const multiQueryResults = allSearchResults.map(item => item.json.chunks || []);

// Reciprocal Rank Fusion Algorithm
function reciprocalRankFusion(multiQueryResults, k = 60) {
  const chunkScores = new Map();

  multiQueryResults.forEach((queryResults, queryIdx) => {
    queryResults.forEach((chunk, rank) => {
      const chunkId = chunk.id;
      const rrfScore = 1 / (k + rank + 1);

      if (!chunkScores.has(chunkId)) {
        chunkScores.set(chunkId, {
          chunk: chunk,
          rrfScore: 0,
          appearances: 0,
          queryAppearances: [],
          ranks: [],
          originalScores: []
        });
      }

      const entry = chunkScores.get(chunkId);
      entry.rrfScore += rrfScore;
      entry.appearances++;
      entry.queryAppearances.push(queryIdx);
      entry.ranks.push(rank);
      entry.originalScores.push(chunk.score || 0);
    });
  });

  // Sort by RRF score (higher = better)
  const fusedResults = Array.from(chunkScores.values())
    .map(entry => ({
      ...entry.chunk,
      rrf_score: entry.rrfScore,
      query_appearances: entry.appearances,
      avg_rank: entry.ranks.reduce((a, b) => a + b, 0) / entry.ranks.length,
      query_indices: entry.queryAppearances
    }))
    .sort((a, b) => b.rrf_score - a.rrf_score);

  return fusedResults;
}

const fusedChunks = reciprocalRankFusion(multiQueryResults);

// Take top 50 for reranking
const top50ForReranking = fusedChunks.slice(0, 50);

return [{
  json: {
    ...originalData,
    fused_chunks: top50ForReranking,
    fusion_stats: {
      total_unique_chunks: fusedChunks.length,
      queries_executed: multiQueryResults.length,
      top_chunk_appearances: top50ForReranking[0]?.query_appearances || 0,
      chunks_for_reranking: top50ForReranking.length
    }
  }
}];
```

### NODE 12: Cross-Encoder Reranking ← NEW
**Type:** n8n-nodes-base.httpRequest
**Purpose:** Rerank top 50 using Cohere Rerank API

```
Method: POST
URL: https://api.cohere.ai/v1/rerank
Headers:
  Authorization: Bearer {{ $credentials.cohereApi.apiKey }}
  Content-Type: application/json

Body:
{{
  JSON.stringify({
    model: 'rerank-english-v3.0',
    query: $json.enhanced_query,
    documents: $json.fused_chunks.map(c => c.content),
    top_n: 15,
    return_documents: false
  })
}}
```

**Note:** Requires Cohere API credentials in n8n

### NODE 13: Process Reranked Results
**Type:** n8n-nodes-base.code
**Purpose:** Map reranked results back to chunk objects

```javascript
const rerankResponse = $input.first().json;
const previousData = $('11. Reciprocal Rank Fusion').first().json;
const fusedChunks = previousData.fused_chunks;

// Map Cohere results back to our chunks
const rerankedChunks = rerankResponse.results.map(result => ({
  ...fusedChunks[result.index],
  rerank_score: result.relevance_score,
  rerank_rank: result.index,
  final_rank: result.index  // After reranking, this is the final rank
}));

return [{
  json: {
    ...previousData,
    reranked_chunks: rerankedChunks,
    reranking_stats: {
      input_chunks: fusedChunks.length,
      output_chunks: rerankedChunks.length,
      top_rerank_score: rerankedChunks[0]?.rerank_score || 0
    }
  }
}];
```

### NODE 14: Extract Golden Chunks
**Type:** n8n-nodes-base.code
**Purpose:** Identify top 10 as golden chunks

```javascript
const data = $input.first().json;
const rerankedChunks = data.reranked_chunks;

// Top 10 = golden chunks (best matches)
const goldenChunks = rerankedChunks.slice(0, 10).map((c, idx) => ({
  id: c.id,
  doc_id: c.doc_id,
  page: c.page_number,
  section: c.section_path ? c.section_path.join(' > ') : 'Unknown',
  section_id: c.section_id,
  score: c.rerank_score,
  rank: idx + 1,
  rrf_score: c.rrf_score,
  query_appearances: c.query_appearances,
  preview: c.content.substring(0, 200),
  full_content: c.content
}));

// Remaining 5 as backup
const backupChunks = rerankedChunks.slice(10, 15);

// Extract chunk IDs for context expansion
const chunk_ids = goldenChunks.map(c => c.id);
const doc_id = goldenChunks[0]?.doc_id || data.doc_id;

return [{
  json: {
    ...data,
    chunk_ids,
    doc_id,
    golden_chunks: goldenChunks,
    backup_chunks: backupChunks,
    chunks_count: rerankedChunks.length
  }
}];
```

### NODE 15: Context Validator ← NEW
**Type:** n8n-nodes-base.code
**Purpose:** Verify context consistency and detect mixed systems

```javascript
const data = $input.first().json;
const goldenChunks = data.golden_chunks;

// Check 1: System consistency
const systems = goldenChunks
  .map(c => {
    const path = c.section.split(' > ');
    return path[0] || 'Unknown';
  })
  .filter(s => s !== 'Unknown');

const systemCounts = {};
systems.forEach(s => {
  systemCounts[s] = (systemCounts[s] || 0) + 1;
});

const uniqueSystems = Object.keys(systemCounts);
const dominantSystem = uniqueSystems.length > 0
  ? uniqueSystems.reduce((a, b) => systemCounts[a] > systemCounts[b] ? a : b)
  : null;

// Flag if multiple systems and none is dominant (>70%)
const systemWarning = uniqueSystems.length > 1 &&
  (systemCounts[dominantSystem] / goldenChunks.length) < 0.7;

// Check 2: Page distribution
const pages = goldenChunks.map(c => c.page);
const pageSpread = Math.max(...pages) - Math.min(...pages);
const pageWarning = pageSpread > 50;  // Chunks spread across >50 pages

// Check 3: Section diversity
const sections = [...new Set(goldenChunks.map(c => c.section))];
const sectionWarning = sections.length > 8;  // Chunks from >8 different sections

const hasWarnings = systemWarning || pageWarning || sectionWarning;

if (hasWarnings) {
  const warnings = [];

  if (systemWarning) {
    warnings.push({
      type: 'mixed_systems',
      message: `Found content from multiple systems: ${uniqueSystems.join(', ')}`,
      systems: uniqueSystems.map(s => ({
        name: s,
        chunk_count: systemCounts[s],
        percentage: Math.round((systemCounts[s] / goldenChunks.length) * 100)
      }))
    });
  }

  if (pageWarning) {
    warnings.push({
      type: 'wide_page_spread',
      message: `Content spans ${pageSpread} pages (${Math.min(...pages)}-${Math.max(...pages)})`,
      suggestion: 'This may indicate overly broad results. Consider refining your query.'
    });
  }

  if (sectionWarning) {
    warnings.push({
      type: 'diverse_sections',
      message: `Content from ${sections.length} different sections`,
      sections: sections.slice(0, 5)  // Show top 5
    });
  }

  return [{
    json: {
      ...data,
      context_validation: {
        needs_clarification: systemWarning,  // Only ask user for system conflicts
        warnings,
        dominant_system: dominantSystem,
        system_counts: systemCounts
      }
    }
  }];
} else {
  return [{
    json: {
      ...data,
      context_validation: {
        needs_clarification: false,
        validated: true,
        primary_system: dominantSystem,
        page_range: [Math.min(...pages), Math.max(...pages)],
        section_count: sections.length
      }
    }
  }];
}
```

### NODE 16: Context Warning?
**Type:** n8n-nodes-base.if
**Condition:** `{{ $json.context_validation.needs_clarification }} === true`
**True Path:** Context Clarification Response → END
**False Path:** Context Expansion

**Context Clarification Response:**
```javascript
const data = $input.first().json;
const validation = data.context_validation;
const systemWarning = validation.warnings.find(w => w.type === 'mixed_systems');

if (systemWarning) {
  return [{
    json: {
      answer: "I found relevant information in multiple systems. Please specify which one you're working with:",
      clarification_needed: true,
      clarification_type: 'system_selection',
      original_query: data.query,
      options: systemWarning.systems.map(s => ({
        label: s.name,
        doc_hint: `${s.chunk_count} relevant sections found (${s.percentage}% of results)`,
        value: s.name
      })),
      metadata: {
        timestamp: new Date().toISOString(),
        queryType: 'context_clarification',
        user_id: data.user_id
      }
    }
  }];
}
```

### NODE 17: Context Expansion
**Type:** n8n-nodes-base.httpRequest
**Same as before, but now receives validated chunks**

```
Method: POST
URL: https://dwisbglrutplhcotbehy.supabase.co/functions/v1/context-expansion
Body: {{ JSON.stringify({
  chunk_ids: $json.chunk_ids,
  doc_id: $json.doc_id,
  token_budget: 6000,
  expand_siblings: true,
  expand_parents: true,
  expand_children: false,
  include_images: true,
  include_tables: true
}) }}
```

### NODE 18: Merge Results (Same as before)

### NODE 19: Answer Generator (Enhanced Prompt)

**Enhanced Prompt with All Context:**
```
=You are a technical documentation assistant for building automation systems (BACnet, Niagara, KitControl, HVAC).

User Query: {{ $('2. Query Analyzer').first().json.query }}

CONTEXT VALIDATION:
✅ Primary System: {{ $json.context_validation.primary_system }}
✅ Content verified from pages {{ $json.context_validation.page_range[0] }}-{{ $json.context_validation.page_range[1] }}

=== GOLDEN CHUNKS (BEST MATCHES - HIGHEST PRIORITY) ===
These chunks scored highest after multi-query search and cross-encoder reranking:
{{ $json.golden_summary }}

Details:
{{ $json.golden_chunks.map((c, i) => `${i+1}. [Rank ${c.rank}, Score ${c.score.toFixed(3)}] ${c.section} (Page ${c.page})\n   Appeared in ${c.query_appearances}/5 query variations\n   Preview: ${c.preview}...`).join('\n\n') }}

=== EXPANDED CONTEXT (Supporting Information) ===
🎯 = Golden chunk (highest relevance)
{{ $json.context }}

=== VISUAL ASSETS ===
{{ $json.images_description }}

=== DATA TABLES ===
{{ $json.tables_content }}

=== INSTRUCTIONS ===
1. **CRITICAL:** Answer ONLY based on the provided context - do NOT use external knowledge
2. **Prioritize golden chunks** - these are verified best matches through multi-stage ranking
3. The query went through:
   - Multi-query search (5 variations)
   - Reciprocal rank fusion
   - Cross-encoder reranking
   - Context validation
4. **Always cite pages:** Use [Page X] format after each fact
5. **Reference visuals:** When diagrams exist: "See wiring diagram [Page X]"
6. **Reference tables:** When data exists: "See specifications table [Page X]"
7. **Be technically precise:** Use exact terminology from the source
8. **Acknowledge limitations:** If context doesn't fully answer, say so explicitly
9. **System context:** All content is from {{ $json.context_validation.primary_system }}
10. **Format:** Use headings, bullet points, and clear structure

Generate your technical answer:
```

### NODE 20: Answer Validator ← NEW
**Type:** @n8n/n8n-nodes-langchain.chainLlm
**Purpose:** Validate answer quality

**Prompt:**
```
=You are a technical QA validator. Evaluate this answer for accuracy and completeness.

Original Query: {{ $('2. Query Analyzer').first().json.query }}

Generated Answer:
{{ $input.first().json.response }}

Citations Present: {{ $input.first().json.response.match(/\[Page \d+\]/g)?.length || 0 }}

Evaluate:
1. Does the answer directly address the query?
2. Are citations present and specific?
3. Any signs of hallucination (info not from context)?
4. Is technical terminology used correctly?
5. Are limitations acknowledged if context incomplete?

Return JSON:
{
  "valid": true/false,
  "confidence": 0.0-1.0,
  "issues": ["issue1", "issue2"],
  "recommendations": ["rec1", "rec2"]
}
```

**Model:** gpt-4o-mini
**Temperature:** 0.2

### NODE 21: Parse Validation Result
**Type:** n8n-nodes-base.code

```javascript
const validationOutput = $input.first().json;
const answerData = $('19. Answer Generator').first().json;
const mergedData = $('18. Merge Results').first().json;
const data = $('14. Extract Golden Chunks').first().json;

let validation = { valid: true, confidence: 1.0, issues: [], recommendations: [] };

try {
  if (validationOutput.response) {
    const jsonMatch = validationOutput.response.match(/\{[\s\S]*\}/);
    if (jsonMatch) {
      validation = JSON.parse(jsonMatch[0]);
    }
  }
} catch (e) {
  console.log('Validation parsing failed, assuming valid');
}

return [{
  json: {
    answer_text: answerData.response || answerData.text,
    validation: validation,
    golden_chunks: mergedData.golden_chunks,
    images: mergedData.images_array,
    tables: mergedData.tables_array,
    context_validation: data.context_validation,
    fusion_stats: data.fusion_stats,
    reranking_stats: data.reranking_stats,
    query_data: data
  }
}];
```

### NODE 22: Update Conversation State
**Type:** n8n-nodes-base.code
**Purpose:** Store conversation for future queries

```javascript
const data = $input.first().json;
const analyzer = $('2. Query Analyzer').first().json;

// In production, this would write to Redis/Database
// For now, we'll just prepare the state object

const conversationUpdate = {
  conversation_id: analyzer.conversation_id || `conv_${Date.now()}`,
  user_id: analyzer.user_id,
  timestamp: new Date().toISOString(),
  query: analyzer.query,
  answer: data.answer_text,
  golden_chunks: data.golden_chunks.map(c => c.id),
  primary_system: data.context_validation.primary_system,
  primary_doc: data.query_data.doc_id,
  validation_passed: data.validation.valid
};

// Would execute: await redis.setex(`conv:${conversation_id}`, 3600, JSON.stringify(conversationUpdate));

return [{
  json: {
    ...data,
    conversation_update: conversationUpdate
  }
}];
```

### NODE 23: Format Final Response
**Type:** n8n-nodes-base.code

```javascript
const data = $input.first().json;
const analyzer = $('2. Query Analyzer').first().json;

// Extract citations
const answerText = data.answer_text;
const citationRegex = /\[Page\s+(\d+)\]/gi;
const citations = [];
let match;
while ((match = citationRegex.exec(answerText)) !== null) {
  citations.push({ page: parseInt(match[1]) });
}
const uniqueCitations = [...new Set(citations.map(c => c.page))].map(page => ({ page }));

return [{
  json: {
    answer: answerText,
    citations: uniqueCitations,
    images: data.images || [],
    tables: data.tables || [],
    golden_chunks: data.golden_chunks.map(c => ({
      id: c.id,
      page: c.page,
      section: c.section,
      rank: c.rank,
      score: c.rerank_score,
      preview: c.preview
    })),
    metadata: {
      timestamp: new Date().toISOString(),
      query: analyzer.query,
      query_type: analyzer.isGreeting ? 'greeting' : 'technical',
      conversation_id: data.conversation_update.conversation_id,
      user_id: analyzer.user_id,
      username: analyzer.username,

      // Search metrics
      chunks_retrieved: data.query_data.chunks_count,
      golden_chunks_count: data.golden_chunks.length,
      images_retrieved: data.images?.length || 0,
      tables_retrieved: data.tables?.length || 0,

      // Processing metrics
      fusion_stats: data.fusion_stats,
      reranking_stats: data.reranking_stats,
      context_validation: data.context_validation,
      answer_validation: data.validation,

      // System context
      primary_system: data.context_validation.primary_system,
      primary_doc: data.query_data.doc_id
    },
    debug: {
      pipeline: 'enhanced-rag-v3-complete',
      features_enabled: [
        'query_validation',
        'multi_query_search',
        'reciprocal_rank_fusion',
        'cross_encoder_reranking',
        'context_validation',
        'conversation_state',
        'answer_validation'
      ],
      total_api_calls: 10,
      estimated_cost: 0.004
    }
  }
}];
```

### NODE 24: Respond to Webhook
**Type:** n8n-nodes-base.respondToWebhook
**Response:** `={{ $json }}`

## Execution Paths Summary

### Path 1: Greeting
```
Webhook → Query Analyzer → Is Greeting? [YES]
  → Greeting Response → Respond to Webhook
```

### Path 2: Needs Query Clarification
```
Webhook → Query Analyzer → Is Greeting? [NO]
  → Query Validator → Needs Clarification? [YES]
  → Clarification Response → Respond to Webhook
```

### Path 3: Needs Context Clarification
```
Webhook → Query Analyzer → Query Validator [VALID]
  → Conversation State Manager
  → Multi-Query Generator → Parse Output
  → Parallel Multi-Search (5x) → RRF → Reranking
  → Extract Golden Chunks → Context Validator → Context Warning? [YES]
  → Context Clarification Response → Respond to Webhook
```

### Path 4: Full Technical Answer (Happy Path)
```
Webhook → Query Analyzer → Query Validator [VALID]
  → Conversation State Manager
  → Multi-Query Generator → Parse Output
  → Parallel Multi-Search (5x) → RRF → Reranking
  → Extract Golden Chunks → Context Validator [VALID]
  → Context Expansion → Merge Results
  → Answer Generator → Answer Validator
  → Update Conversation State → Format Response
  → Respond to Webhook
```

## Total Node Count

- Webhook: 1
- Query Analysis: 2 (Analyzer + Greeting Check)
- Query Validation: 3 (Validator + Clarification Check + Response)
- Conversation: 1
- Multi-Query: 2 (Generator + Parser)
- Search: 2 (Parallel Multi-Search + HTTP)
- Fusion: 1
- Reranking: 2 (HTTP + Parser)
- Golden Chunks: 1
- Context Validation: 3 (Validator + Warning Check + Response)
- Context Expansion: 1
- Merge: 1
- Answer: 2 (Generator + Validator)
- Conversation Update: 1
- Response: 2 (Format + Webhook Response)

**Total: ~25 nodes** (full production system)

## Next: Generate Complete Workflow JSON

Ready to proceed with creating the complete workflow JSON?
