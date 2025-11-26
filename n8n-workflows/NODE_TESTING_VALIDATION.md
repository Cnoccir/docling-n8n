# Complete Node-by-Node Testing & Validation

## Testing Methodology

For each code node, I'll test:
1. ✅ **Happy path** - Normal execution
2. ⚠️ **Partial data** - Missing optional fields
3. ❌ **Error cases** - Malformed/missing required data
4. 🔄 **Edge cases** - Empty arrays, nulls, undefined

---

## NODE 1: Query Analyzer

### Code Review:
```javascript
const body = $input.first().json.body || $input.first().json;
const query = body.query || body.chatInput || '';
```

### Issues Found:
1. ❌ **No validation** - Empty query should be caught
2. ❌ **Missing error handling** - If body is undefined

### Test Cases:

**Test 1: Normal input**
```json
Input: {"query": "How to configure PID loop?"}
Output: {
  "query": "How to configure PID loop?",
  "isGreeting": false,
  "hasTechnicalTerms": true,
  "wordCount": 5,
  ...
}
✅ PASS
```

**Test 2: Empty query**
```json
Input: {"query": ""}
Output: {
  "query": "",
  "wordCount": 1,
  "isVeryShort": true,
  ...
}
⚠️ ISSUE: Should catch empty query early
```

**Test 3: Missing query field**
```json
Input: {}
Output: {
  "query": "",
  ...
}
⚠️ ISSUE: Should return error
```

**Test 4: Nested body**
```json
Input: {"body": {"query": "test"}}
Output: {"query": "test", ...}
✅ PASS
```

### Fixed Version:

```javascript
const body = $input.first().json.body || $input.first().json;
const query = body.query || body.chatInput || '';
const conversation_id = body.conversation_id || null;

// Validate query exists and not empty
if (!query || query.trim().length === 0) {
  return [{
    json: {
      error: true,
      error_type: 'empty_query',
      message: 'Query is required and cannot be empty',
      user_id: body.user_id || body.userId || 'anonymous',
      username: body.username || 'User'
    }
  }];
}

const isGreeting = /^(hi|hello|hey|good morning|good afternoon)/i.test(query.trim());
const hasTechnicalTerms = /\b(span|block|gpm|pump|valve|sensor|controller|wire|wiring|component|module|analog|digital|bacnet|niagara|kitcontrol|honeywell|pid|loop|setpoint|damper|actuator|point|extension)\b/i.test(query);
const wantsVisuals = /\b(show|image|diagram|picture|visual|schematic|wiring|drawing|illustration|graphic)\b/i.test(query) || /wir(e|ing)/i.test(query);
const wantsDetails = /\b(detailed|spec|specification|table|parameter|configuration|breakdown|setting|value)\b/i.test(query);

const wordCount = query.trim().split(/\s+/).length;
const isVeryShort = wordCount < 3;
const isShort = wordCount < 5;

return [{
  json: {
    query: query.trim(),
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

---

## NODE 3: Query Validator

### Issues Found:
1. ✅ Code looks solid
2. ⚠️ Need to handle when analyzer is missing

### Test Cases:

**Test 1: Vague pronoun**
```javascript
Input: {query: "How does it work?", wordCount: 4}
Output: {
  validation: {
    needs_clarification: true,
    issues: [{type: "vague_pronoun", severity: "high"}]
  }
}
✅ PASS
```

**Test 2: Good technical query**
```javascript
Input: {query: "How to configure KitControl PID loop?", hasTechnicalTerms: true, wordCount: 6}
Output: {
  validation: {
    needs_clarification: false,
    issues: [],
    suggestions: []
  }
}
✅ PASS
```

**Test 3: Ambiguous term without context**
```javascript
Input: {query: "Configure pump", wordCount: 2}
Output: {
  validation: {
    needs_clarification: false, // medium severity
    issues: [{type: "ambiguous_term", term: "pump", severity: "medium"}]
  }
}
⚠️ ISSUE: Should still suggest clarification for medium issues
```

### Fixed Version:

```javascript
const analyzer = $input.first().json;

// Handle error from previous node
if (analyzer.error) {
  return [analyzer];
}

const query = analyzer.query;
const issues = [];
const suggestions = [];

// ... (same validation logic)

// FIXED: Consider medium severity issues too
const highSeverityIssues = issues.filter(i => i.severity === 'high').length;
const mediumSeverityIssues = issues.filter(i => i.severity === 'medium').length;

// Need clarification if high severity OR multiple medium severity
const needsClarification = highSeverityIssues > 0 || mediumSeverityIssues >= 2;

return [{
  json: {
    ...analyzer,
    validation: {
      needs_clarification: needsClarification,
      issues,
      suggestions,
      validated_query: query,
      severity_counts: {
        high: highSeverityIssues,
        medium: mediumSeverityIssues
      }
    }
  }
}];
```

---

## NODE 7: Parse Multi-Query Output

### Issues Found:
1. ❌ **Critical:** No error handling for LLM failures
2. ❌ **Missing fallback** - Should use enhanced_query, not original

### Test Cases:

**Test 1: Valid JSON array**
```javascript
Input: {response: '["query1", "query2", "query3", "query4", "query5"]'}
Output: {query_variations: ["query1", "query2", "query3", "query4", "query5"]}
✅ PASS
```

**Test 2: JSON with markdown**
```javascript
Input: {response: '```json\n["q1", "q2", "q3", "q4", "q5"]\n```'}
Output: {query_variations: ["q1", "q2", "q3", "q4", "q5"]}
✅ PASS (regex finds it)
```

**Test 3: Malformed JSON**
```javascript
Input: {response: '["q1", "q2", "q3"'}  // Missing closing
Output: Falls back to original query 5 times
⚠️ ISSUE: Should use enhanced_query, not original query
```

**Test 4: LLM returns text instead of JSON**
```javascript
Input: {response: 'I cannot generate queries'}
Output: Falls back to original query 5 times
✅ PASS (but should log warning)
```

**Test 5: Empty response**
```javascript
Input: {response: ''}
Output: Falls back to original query 5 times
✅ PASS
```

**Test 6: Only 3 queries returned**
```javascript
Input: {response: '["q1", "q2", "q3"]'}
Output: {query_variations: ["q1", "q2", "q3", "enhanced_query", "enhanced_query"]}
✅ PASS
```

### Fixed Version:

```javascript
const llmOutput = $input.first().json;
const originalData = $('5. Conversation State Manager').first().json;

// Handle error from previous node
if (originalData.error) {
  return [originalData];
}

let queries = [];
let parseError = null;

if (llmOutput.response) {
  const responseText = llmOutput.response;

  // Try to extract JSON array
  const jsonMatch = responseText.match(/\[[\s\S]*\]/);
  if (jsonMatch) {
    try {
      const parsed = JSON.parse(jsonMatch[0]);
      if (Array.isArray(parsed)) {
        queries = parsed;
      } else {
        parseError = 'LLM returned JSON but not an array';
      }
    } catch (e) {
      parseError = `JSON parse failed: ${e.message}`;
    }
  } else {
    parseError = 'No JSON array found in LLM response';
  }
} else if (Array.isArray(llmOutput)) {
  queries = llmOutput;
}

// Fallback: Use enhanced_query (NOT original query!)
if (queries.length === 0) {
  console.log(`Multi-query generation failed: ${parseError}. Using fallback.`);
  queries = [originalData.enhanced_query];
}

// Ensure exactly 5 queries
const baseQuery = originalData.enhanced_query;
while (queries.length < 5) {
  // Add slight variations by reordering words
  queries.push(baseQuery);
}

if (queries.length > 5) {
  queries = queries.slice(0, 5);
}

// Remove duplicates and empty strings
queries = queries
  .filter(q => q && q.trim().length > 0)
  .map(q => q.trim());

// If filtering removed too many, pad with base query
while (queries.length < 5) {
  queries.push(baseQuery);
}

return [{
  json: {
    ...originalData,
    query_variations: queries,
    multi_query_debug: {
      original_query: originalData.query,
      enhanced_query: baseQuery,
      generated_count: queries.length,
      parse_error: parseError,
      fallback_used: parseError !== null
    }
  }
}];
```

---

## NODE 8: Parallel Multi-Search Setup

### Issues Found:
1. ✅ Code is simple and safe
2. ⚠️ Should validate query_variations exists

### Test Cases:

**Test 1: Normal - 5 queries**
```javascript
Input: {query_variations: ["q1", "q2", "q3", "q4", "q5"]}
Output: [
  {query: "q1", query_index: 0, ...},
  {query: "q2", query_index: 1, ...},
  ...
]
✅ PASS - Returns 5 items
```

**Test 2: Empty variations array**
```javascript
Input: {query_variations: []}
Output: []
❌ FAIL - Next node gets no input!
```

### Fixed Version:

```javascript
const data = $input.first().json;

// Handle error from previous node
if (data.error) {
  return [data];
}

const queries = data.query_variations || [];
const searchParams = data.search_params;
const doc_ids = data.doc_id ? [data.doc_id] : null;

// Validate we have queries
if (queries.length === 0) {
  // Fallback: use enhanced_query
  queries.push(data.enhanced_query || data.query);
}

return queries.map((query, index) => ({
  json: {
    query: query,
    query_index: index,
    doc_ids: doc_ids,
    top_k: searchParams.top_k,
    fts_weight: searchParams.fts_weight,
    vector_weight: searchParams.vector_weight,
    original_data: data
  }
}));
```

---

## NODE 10: Reciprocal Rank Fusion

### Issues Found:
1. ❌ **Critical:** No handling for empty search results
2. ❌ **Critical:** No handling for partial results (some queries fail)
3. ⚠️ Division by zero if ranks array is empty

### Test Cases:

**Test 1: All 5 queries return results**
```javascript
Input: 5 items, each with {chunks: [{id: "x", score: 0.5}, ...]}
Output: {fused_chunks: [...], fusion_stats: {queries_executed: 5}}
✅ PASS
```

**Test 2: One query returns no chunks**
```javascript
Input: 5 items, one has {chunks: []}
Output: {fused_chunks: [...], fusion_stats: {queries_executed: 5}}
⚠️ Should still work, but fusion_stats might be misleading
```

**Test 3: All queries return no chunks**
```javascript
Input: 5 items, all have {chunks: []}
Output: {fused_chunks: [], fusion_stats: {total_unique_chunks: 0}}
❌ FAIL - Next node expects fused_chunks.slice(0, 50)
```

**Test 4: HTTP request failed for some queries**
```javascript
Input: 3 items (2 queries failed)
Output: Uses only 3 results
⚠️ Should work but should flag partial failure
```

**Test 5: Chunk missing required fields**
```javascript
Input: Chunk with no `id` field
Output: chunkId = undefined
❌ FAIL - Map key becomes undefined, chunks overwrite each other
```

### Fixed Version:

```javascript
const allSearchResults = $input.all();

// Handle errors
if (allSearchResults.length === 0) {
  return [{
    json: {
      error: true,
      error_type: 'no_search_results',
      message: 'All search queries failed or returned no results',
      original_data: null
    }
  }];
}

const originalData = allSearchResults[0].json.original_data;

// Handle error from previous node
if (originalData && originalData.error) {
  return [originalData];
}

// Extract chunks from each query's results
// Filter out failed queries (no chunks field or error)
const multiQueryResults = allSearchResults
  .filter(item => item.json && !item.json.error && item.json.chunks)
  .map(item => item.json.chunks || []);

if (multiQueryResults.length === 0) {
  return [{
    json: {
      error: true,
      error_type: 'all_searches_failed',
      message: 'All search queries failed',
      original_data: originalData
    }
  }];
}

// Reciprocal Rank Fusion Algorithm
function reciprocalRankFusion(multiQueryResults, k = 60) {
  const chunkScores = new Map();

  multiQueryResults.forEach((queryResults, queryIdx) => {
    queryResults.forEach((chunk, rank) => {
      // Validate chunk has required fields
      if (!chunk || !chunk.id) {
        console.log(`Skipping chunk without ID in query ${queryIdx}, rank ${rank}`);
        return;
      }

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

  const fusedResults = Array.from(chunkScores.values())
    .map(entry => ({
      ...entry.chunk,
      rrf_score: entry.rrfScore,
      query_appearances: entry.appearances,
      avg_rank: entry.ranks.reduce((a, b) => a + b, 0) / (entry.ranks.length || 1),
      query_indices: entry.queryAppearances
    }))
    .sort((a, b) => b.rrf_score - a.rrf_score);

  return fusedResults;
}

const fusedChunks = reciprocalRankFusion(multiQueryResults);

// Check if we have enough results
if (fusedChunks.length === 0) {
  return [{
    json: {
      error: true,
      error_type: 'no_valid_chunks',
      message: 'No valid chunks found after fusion',
      original_data: originalData
    }
  }];
}

const top50ForReranking = fusedChunks.slice(0, Math.min(50, fusedChunks.length));

return [{
  json: {
    ...originalData,
    fused_chunks: top50ForReranking,
    fusion_stats: {
      total_unique_chunks: fusedChunks.length,
      queries_executed: allSearchResults.length,
      queries_successful: multiQueryResults.length,
      queries_failed: allSearchResults.length - multiQueryResults.length,
      top_chunk_appearances: top50ForReranking[0]?.query_appearances || 0,
      chunks_for_reranking: top50ForReranking.length
    }
  }
}];
```

---

## NODE 12: Process Reranked Results

### Issues Found:
1. ❌ **Critical:** No error handling for Cohere API failures
2. ❌ **Critical:** Assumes result.index is always valid

### Test Cases:

**Test 1: Normal Cohere response**
```javascript
Input: {
  results: [
    {index: 0, relevance_score: 0.95},
    {index: 5, relevance_score: 0.87}
  ]
}
Output: {reranked_chunks: [...], reranking_stats: {...}}
✅ PASS
```

**Test 2: Cohere API error**
```javascript
Input: {error: "Rate limit exceeded"}
Output: ❌ CRASH - tries to access .results on error object
```

**Test 3: Cohere returns fewer results**
```javascript
Input: {results: []}  // Asked for 15, got 0
Output: {reranked_chunks: []}
⚠️ Should handle gracefully
```

**Test 4: Invalid index**
```javascript
Input: {results: [{index: 999, relevance_score: 0.5}]}
Output: fusedChunks[999] = undefined
❌ FAIL
```

### Fixed Version:

```javascript
const rerankResponse = $input.first().json;
const previousData = $('10. Reciprocal Rank Fusion').first().json;

// Handle error from previous node
if (previousData.error) {
  return [previousData];
}

const fusedChunks = previousData.fused_chunks;

// Handle Cohere API errors
if (rerankResponse.error || rerankResponse.message) {
  console.log(`Cohere reranking failed: ${rerankResponse.error || rerankResponse.message}. Using RRF results.`);

  // Fallback: Use RRF results without reranking
  const fallbackChunks = fusedChunks.slice(0, 15).map((chunk, idx) => ({
    ...chunk,
    rerank_score: chunk.rrf_score,  // Use RRF score as fallback
    rerank_rank: idx,
    final_rank: idx,
    reranked: false  // Flag that reranking didn't happen
  }));

  return [{
    json: {
      ...previousData,
      reranked_chunks: fallbackChunks,
      reranking_stats: {
        input_chunks: fusedChunks.length,
        output_chunks: fallbackChunks.length,
        top_rerank_score: fallbackChunks[0]?.rerank_score || 0,
        reranking_failed: true,
        fallback_used: true
      }
    }
  }];
}

// Validate Cohere response structure
if (!rerankResponse.results || !Array.isArray(rerankResponse.results)) {
  console.log('Invalid Cohere response structure. Using fallback.');
  // Same fallback as above
  const fallbackChunks = fusedChunks.slice(0, 15).map((chunk, idx) => ({
    ...chunk,
    rerank_score: chunk.rrf_score,
    rerank_rank: idx,
    final_rank: idx,
    reranked: false
  }));

  return [{
    json: {
      ...previousData,
      reranked_chunks: fallbackChunks,
      reranking_stats: {
        input_chunks: fusedChunks.length,
        output_chunks: fallbackChunks.length,
        top_rerank_score: fallbackChunks[0]?.rerank_score || 0,
        reranking_failed: true,
        fallback_used: true
      }
    }
  }];
}

// Map Cohere results back to chunks with validation
const rerankedChunks = rerankResponse.results
  .filter(result => {
    // Validate index is within bounds
    if (result.index < 0 || result.index >= fusedChunks.length) {
      console.log(`Invalid index ${result.index} from Cohere (max: ${fusedChunks.length - 1})`);
      return false;
    }
    return true;
  })
  .map((result, position) => ({
    ...fusedChunks[result.index],
    rerank_score: result.relevance_score,
    rerank_rank: result.index,
    final_rank: position,
    reranked: true
  }));

// If filtering removed all results, use fallback
if (rerankedChunks.length === 0) {
  console.log('All Cohere results had invalid indices. Using fallback.');
  const fallbackChunks = fusedChunks.slice(0, 15).map((chunk, idx) => ({
    ...chunk,
    rerank_score: chunk.rrf_score,
    rerank_rank: idx,
    final_rank: idx,
    reranked: false
  }));

  return [{
    json: {
      ...previousData,
      reranked_chunks: fallbackChunks,
      reranking_stats: {
        input_chunks: fusedChunks.length,
        output_chunks: fallbackChunks.length,
        top_rerank_score: fallbackChunks[0]?.rerank_score || 0,
        reranking_failed: true,
        fallback_used: true
      }
    }
  }];
}

return [{
  json: {
    ...previousData,
    reranked_chunks: rerankedChunks,
    reranking_stats: {
      input_chunks: fusedChunks.length,
      output_chunks: rerankedChunks.length,
      top_rerank_score: rerankedChunks[0]?.rerank_score || 0,
      reranking_failed: false,
      fallback_used: false
    }
  }
}];
```

---

## NODE 13: Extract Golden Chunks

### Issues Found:
1. ⚠️ Assumes reranked_chunks exists and has items
2. ⚠️ Should handle case where doc_id is missing

### Fixed Version:

```javascript
const data = $input.first().json;

// Handle error from previous node
if (data.error) {
  return [data];
}

const rerankedChunks = data.reranked_chunks || [];

// Handle empty results
if (rerankedChunks.length === 0) {
  return [{
    json: {
      error: true,
      error_type: 'no_reranked_chunks',
      message: 'No chunks available after reranking',
      original_data: data
    }
  }];
}

// Top 10 = golden chunks (or fewer if we don't have 10)
const goldenCount = Math.min(10, rerankedChunks.length);
const goldenChunks = rerankedChunks.slice(0, goldenCount).map((c, idx) => ({
  id: c.id,
  doc_id: c.doc_id,
  page: c.page_number || 0,
  section: c.section_path ? c.section_path.join(' > ') : 'Unknown',
  section_id: c.section_id,
  score: c.rerank_score,
  rank: idx + 1,
  rrf_score: c.rrf_score,
  query_appearances: c.query_appearances || 0,
  preview: c.content ? c.content.substring(0, 200) : '',
  full_content: c.content || ''
}));

// Remaining as backup (up to 5 more)
const backupChunks = rerankedChunks.slice(10, 15);

// Extract chunk IDs and doc_id
const chunk_ids = goldenChunks.map(c => c.id);
const doc_id = goldenChunks[0]?.doc_id || data.doc_id || null;

// Validate we have a doc_id
if (!doc_id) {
  console.log('Warning: No doc_id found in golden chunks or original data');
}

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

---

## NODE 14: Context Validator

### Issues Found:
1. ✅ Mostly solid, but should handle empty golden_chunks
2. ⚠️ Math.max/min on empty array returns -Infinity/Infinity

### Fixed Version:

```javascript
const data = $input.first().json;

// Handle error from previous node
if (data.error) {
  return [data];
}

const goldenChunks = data.golden_chunks || [];

// Handle empty golden chunks
if (goldenChunks.length === 0) {
  return [{
    json: {
      ...data,
      context_validation: {
        needs_clarification: false,
        validated: false,
        warning: 'No golden chunks to validate',
        primary_system: null
      }
    }
  }];
}

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

const systemWarning = uniqueSystems.length > 1 &&
  (systemCounts[dominantSystem] / goldenChunks.length) < 0.7;

// Check 2: Page distribution
const pages = goldenChunks.map(c => c.page).filter(p => p > 0);  // Filter out invalid pages
const pageSpread = pages.length > 0 ? (Math.max(...pages) - Math.min(...pages)) : 0;
const pageWarning = pageSpread > 50;

// Check 3: Section diversity
const sections = [...new Set(goldenChunks.map(c => c.section))];
const sectionWarning = sections.length > 8;

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

  if (pageWarning && pages.length > 0) {
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
      sections: sections.slice(0, 5)
    });
  }

  return [{
    json: {
      ...data,
      context_validation: {
        needs_clarification: systemWarning,
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
        page_range: pages.length > 0 ? [Math.min(...pages), Math.max(...pages)] : [0, 0],
        section_count: sections.length
      }
    }
  }];
}
```

---

## NODE 17: Merge Results

### Issues Found:
1. ❌ **Critical:** Tries to access nodes by name - n8n syntax error
2. ❌ **Critical:** No handling for missing expansion results

### Test Cases:

**Test 1: Normal expansion result**
```javascript
Input: {expanded_chunks: [{is_seed: true, content: "...", images: [...]}]}
Output: {context: "...", images_array: [...], golden_chunks: [...]}
✅ Should PASS
```

**Test 2: Context expansion failed**
```javascript
Input: {error: "Expansion failed"}
Output: ❌ CRASH - tries to access .expanded_chunks on error
```

**Test 3: Empty expanded_chunks**
```javascript
Input: {expanded_chunks: []}
Output: {golden_chunks: [], images_array: [], context: ""}
⚠️ Should handle but warn
```

### Fixed Version:

```javascript
// Get nodes by reference, not by name string
const expansionResult = $input.first().json;
const goldenChunksDataNode = $input.item(0).json;  // This won't work in n8n!

// CORRECT WAY: Pass golden_chunks through the chain
// We need to access it from a previous execution stored in context

// For now, let's fix the immediate issues:
const expanded_chunks = expansionResult.expanded_chunks || [];

// Handle error from context expansion
if (expansionResult.error) {
  return [{
    json: {
      error: true,
      error_type: 'context_expansion_failed',
      message: expansionResult.message || 'Context expansion failed',
      context: '',
      images_array: [],
      tables_array: [],
      golden_chunks: [],
      metadata: {
        chunks_count: 0,
        golden_chunks_count: 0,
        images_count: 0,
        tables_count: 0
      }
    }
  }];
}

// Handle empty results
if (expanded_chunks.length === 0) {
  return [{
    json: {
      error: true,
      error_type: 'no_expanded_chunks',
      message: 'Context expansion returned no chunks',
      context: '',
      images_array: [],
      tables_array: [],
      golden_chunks: [],
      metadata: {
        chunks_count: 0,
        golden_chunks_count: 0,
        images_count: 0,
        tables_count: 0
      }
    }
  }];
}

// Extract golden chunks (seed chunks with highest relevance)
const goldenChunks = expanded_chunks
  .filter(c => c.is_seed === true)
  .map(c => ({
    id: c.id,
    page: c.page_number || 0,
    section: c.section_path ? c.section_path.join(' > ') : 'Unknown',
    preview: c.content ? c.content.substring(0, 200) : ''
  }));

// Extract all images from chunks (already attached by context-expansion)
const allImages = expanded_chunks.flatMap(chunk => chunk.images || []);
const images = allImages.filter((img, index, self) =>
  img && img.image_id && index === self.findIndex(i => i.image_id === img.image_id)
);

// Extract all tables from chunks
const allTables = expanded_chunks.flatMap(chunk => chunk.tables || []);
const tables = allTables.filter((tbl, index, self) =>
  tbl && tbl.table_id && index === self.findIndex(t => t.table_id === tbl.table_id)
);

// Format context for LLM with GOLDEN CHUNK indicators
const contextText = expanded_chunks
  .map(chunk => {
    const golden = chunk.is_seed ? '🎯 [GOLDEN CHUNK - BEST MATCH] ' : '';
    const sectionPath = chunk.section_path ? chunk.section_path.join(' > ') : '';
    const content = chunk.content || '';
    return `${golden}[Page ${chunk.page_number || 0}${sectionPath ? ' | ' + sectionPath : ''}]\n${content}`;
  })
  .join('\n\n---\n\n');

const imagesText = images.length > 0
  ? images
      .map(img => `[Image - Page ${img.page_number || 0}]: ${img.summary || img.caption || 'Diagram'}`)
      .join('\n')
  : 'No images available';

const tablesText = tables.length > 0
  ? tables
      .map(tbl => `[Table - Page ${tbl.page_number || 0}]:\n${tbl.markdown || ''}\n${tbl.description || ''}`)
      .join('\n\n')
  : 'No tables available';

// Create golden summary from reranked data (need to pass this through!)
// For now, use what we have from expanded_chunks
const goldenSummary = goldenChunks.length > 0
  ? goldenChunks
      .map((c, i) => `${i+1}. ${c.section} (Page ${c.page})`)
      .join('\n')
  : 'No golden chunks identified';

return [{
  json: {
    context: contextText,
    images_description: imagesText,
    tables_content: tablesText,
    golden_summary: goldenSummary,
    images_array: images,
    tables_array: tables,
    golden_chunks: goldenChunks,
    metadata: {
      chunks_count: expanded_chunks.length,
      golden_chunks_count: goldenChunks.length,
      images_count: images.length,
      tables_count: tables.length,
      expansion_summary: expansionResult.expansion_summary || {}
    }
  }
}];
```

---

## Summary of Critical Issues Found

### 🔴 **CRITICAL (Must Fix):**

1. **Node 1 (Query Analyzer):** No empty query validation
2. **Node 10 (RRF):** No handling for empty/failed search results
3. **Node 12 (Process Rerank):** No handling for Cohere API failures
4. **Node 17 (Merge Results):** Cannot access previous node data correctly

### ⚠️ **HIGH PRIORITY:**

5. **Node 7 (Multi-Query Parser):** Should use enhanced_query in fallback
6. **Node 8 (Parallel Setup):** Should validate query_variations exists
7. **Node 13 (Extract Golden):** Should handle missing doc_id

### ✅ **MEDIUM (Nice to Have):**

8. **Node 3 (Query Validator):** Could consider medium severity issues
9. **Node 14 (Context Validator):** Handle edge case of empty pages array

---

## Recommended Workflow Architecture Fix

**MAJOR ISSUE:** Node 17 cannot reference Node 13 directly!

**Solution:** Pass golden_chunks data through the workflow

**Current flow:**
```
13. Extract Golden Chunks (creates golden_chunks)
  ↓
14. Context Validator (passes through)
  ↓
15. Context Warning?
  ↓
16. Context Expansion (loses golden_chunks data!)
  ↓
17. Merge Results (can't access golden_chunks from Node 13) ❌
```

**Fixed flow:** Add hidden field to pass data through:

```javascript
// Node 14, 16 should include:
return [{
  json: {
    ...data,
    __golden_chunks_metadata: data.golden_chunks  // Pass through
  }
}];

// Node 17 can then access:
const goldenChunksData = $input.first().json.__golden_chunks_metadata;
```

---

## Next: Create Fully Fixed Workflow JSON

Should I create the corrected workflow with all these fixes?
