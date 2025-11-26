// Supabase Edge Function: Hybrid Search (FTS + Vector with RRF)
// Combines keyword and semantic search using Reciprocal Rank Fusion

import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2.38.4";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

interface HybridSearchRequest {
  query: string;
  doc_id?: string;  // Single doc filter (legacy)
  doc_ids?: string[];  // Multi-doc filter (new for scale)
  top_k?: number;
  fts_weight?: number;
  vector_weight?: number;
}

interface ChunkResult {
  id: string;
  doc_id: string;
  doc_title: string;
  gdrive_link: string | null;
  content: string;
  page_number: number;
  section_path: string[];
  metadata: Record<string, any>;
  score: number;
  match_type: "fts" | "vector" | "both";
}

// Generate embedding using OpenAI API
async function generateEmbedding(text: string): Promise<number[]> {
  const openaiApiKey = Deno.env.get("OPENAI_API_KEY");
  if (!openaiApiKey) {
    throw new Error("OPENAI_API_KEY not set");
  }

  const response = await fetch("https://api.openai.com/v1/embeddings", {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${openaiApiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model: "text-embedding-3-small",
      input: text,
    }),
  });

  if (!response.ok) {
    throw new Error(`OpenAI API error: ${response.statusText}`);
  }

  const data = await response.json();
  return data.data[0].embedding;
}

// Reciprocal Rank Fusion
function reciprocalRankFusion(
  ftsResults: any[],
  vectorResults: any[],
  ftsWeight: number,
  vectorWeight: number,
  k: number = 60
): ChunkResult[] {
  const scoreMap = new Map<string, any>();

  // Process FTS results
  ftsResults.forEach((result, index) => {
    const chunkId = result.id;
    const ftsScore = ftsWeight / (k + index + 1);
    
    scoreMap.set(chunkId, {
      ...result,
      fts_rank: index + 1,
      fts_score: ftsScore,
      vector_rank: null,
      vector_score: 0,
      match_type: "fts" as const,
    });
  });

  // Process vector results
  vectorResults.forEach((result, index) => {
    const chunkId = result.id;
    const vectorScore = vectorWeight / (k + index + 1);
    
    if (scoreMap.has(chunkId)) {
      // Found in both results
      const existing = scoreMap.get(chunkId);
      existing.vector_rank = index + 1;
      existing.vector_score = vectorScore;
      existing.match_type = "both";
    } else {
      scoreMap.set(chunkId, {
        ...result,
        fts_rank: null,
        fts_score: 0,
        vector_rank: index + 1,
        vector_score: vectorScore,
        match_type: "vector" as const,
      });
    }
  });

  // Calculate final scores and sort
  const results = Array.from(scoreMap.values())
    .map((item) => ({
      id: item.id,
      doc_id: item.doc_id,
      doc_title: item.document_index?.title || item.doc_title || 'Unknown',
      gdrive_link: item.document_index?.gdrive_link || item.gdrive_link || null,
      content: item.content,
      page_number: item.page_number,
      section_id: item.section_id,          // For hierarchy-aware expansion
      section_path: item.section_path || [],
      metadata: item.metadata || {},
      score: item.fts_score + item.vector_score,
      match_type: item.match_type,
      _debug: {
        fts_rank: item.fts_rank,
        vector_rank: item.vector_rank,
        fts_score: item.fts_score,
        vector_score: item.vector_score,
      },
    }))
    .sort((a, b) => b.score - a.score);

  return results;
}

serve(async (req) => {
  // Handle CORS preflight
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }

  try {
    const supabaseUrl = Deno.env.get("SUPABASE_URL")!;
    const supabaseKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
    const supabase = createClient(supabaseUrl, supabaseKey);

    const requestBody: HybridSearchRequest = await req.json();
    const {
      query,
      doc_id = null,
      doc_ids = null,  // NEW: Multi-document filter
      top_k = 10,
      fts_weight = 0.4,
      vector_weight = 0.6,
    } = requestBody;

    if (!query) {
      return new Response(
        JSON.stringify({ error: "Query parameter is required" }),
        { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    // Determine document filter (prioritize doc_ids array for multi-doc)
    const docFilter = doc_ids && doc_ids.length > 0 ? doc_ids : (doc_id ? [doc_id] : null);
    console.log(`Hybrid search: "${query}" (top_k=${top_k}, doc_filter=${docFilter ? JSON.stringify(docFilter) : 'none'})`);

    // Execute FTS and vector search in parallel
    const embedding = await generateEmbedding(query);

    // FTS search with multi-doc support - join with document_index for gdrive_link
    let ftsQuery = supabase
      .from("chunks")
      .select(`
        id, doc_id, content, page_number, section_id, section_path, metadata,
        document_index!inner(title, gdrive_link)
      `)
      .textSearch("content", query, { type: "websearch", config: "english" });

    if (docFilter) {
      ftsQuery = ftsQuery.in("doc_id", docFilter);
    }

    const { data: ftsResults, error: ftsError } = await ftsQuery.limit(top_k * 2);

    if (ftsError) {
      throw new Error(`FTS search failed: ${ftsError.message}`);
    }

    // Vector search with multi-doc support - join with document_index for gdrive_link
    let vectorQuery = supabase
      .from("chunks")
      .select(`
        id, doc_id, content, page_number, section_id, section_path, metadata, embedding,
        document_index!inner(title, gdrive_link)
      `)
      .not("embedding", "is", null);

    if (docFilter) {
      vectorQuery = vectorQuery.in("doc_id", docFilter);
    }

    const { data: allChunks, error: vectorError } = await vectorQuery.limit(1000);

    if (vectorError) {
      throw new Error(`Vector search failed: ${vectorError.message}`);
    }

    // Calculate cosine similarity for each chunk
    const vectorResults = (allChunks || [])
      .map((chunk: any) => {
        const chunkEmbedding = chunk.embedding;
        if (!chunkEmbedding || !Array.isArray(chunkEmbedding)) {
          return null;
        }
        const similarity = cosineSimilarity(embedding, chunkEmbedding);
        return {
          ...chunk,
          similarity,
        };
      })
      .filter((chunk: any) => chunk !== null && chunk.similarity > 0.1)
      .sort((a: any, b: any) => b.similarity - a.similarity)
      .slice(0, top_k * 2);

    // Apply RRF
    const fusedResults = reciprocalRankFusion(
      ftsResults || [],
      vectorResults,
      fts_weight,
      vector_weight
    );

    return new Response(
      JSON.stringify({
        success: true,
        query,
        doc_filter: docFilter,
        total_results: fusedResults.length,
        chunks: fusedResults.slice(0, top_k),
        metadata: {
          fts_weight,
          vector_weight,
          fts_count: ftsResults?.length || 0,
          vector_count: vectorResults.length,
          documents_searched: docFilter ? docFilter.length : "all",
        },
      }),
      {
        status: 200,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      }
    );
  } catch (error) {
    console.error("Hybrid search error:", error);
    return new Response(
      JSON.stringify({ error: error.message }),
      {
        status: 500,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      }
    );
  }
});

// Cosine similarity helper
function cosineSimilarity(a: number[], b: number[]): number {
  if (a.length !== b.length) return 0;
  
  let dotProduct = 0;
  let normA = 0;
  let normB = 0;
  
  for (let i = 0; i < a.length; i++) {
    dotProduct += a[i] * b[i];
    normA += a[i] * a[i];
    normB += b[i] * b[i];
  }
  
  return dotProduct / (Math.sqrt(normA) * Math.sqrt(normB));
}
