// Supabase Edge Function: Document Router
// Routes queries to relevant documents using LLM query enhancement + doc summary search
// CRITICAL for multi-document RAG at scale (100+ documents)

import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2.38.4";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

interface DocumentRouterRequest {
  query: string;
  max_documents?: number;  // Max docs to return (default 3)
  use_llm_enhancement?: boolean;  // Use LLM to rephrase query (default true)
  conversation_context?: any;  // Previous conversation for context
  filter_by_type?: string;  // Optional: filter by document_type
}

// OpenAI API call for query enhancement
async function enhanceQuery(
  originalQuery: string,
  conversationContext?: any
): Promise<{ enhanced_query: string; search_terms: string[] }> {
  const openaiApiKey = Deno.env.get("OPENAI_API_KEY")!;

  const systemPrompt = `You are a query enhancement specialist for technical documentation search.

Your task:
1. Rephrase the user's query to be more specific and searchable
2. Extract key search terms that would appear in document titles or summaries
3. Consider domain context: HVAC, BMS, Building Controls, Niagara, Honeywell, kitControl

Output JSON with:
- enhanced_query: Improved version of the query
- search_terms: Array of 3-5 key terms to search for

Examples:
User: "span block setup"
Output: {"enhanced_query": "How to configure and wire a span block for analog signal scaling in BMS systems", "search_terms": ["span block", "analog scaling", "signal configuration", "BMS wiring", "control components"]}

User: "pump gpm logic"
Output: {"enhanced_query": "Implementing pump flow control logic using GPM measurements and scaling", "search_terms": ["pump control", "gpm flow", "scaling logic", "flow measurement", "HVAC pumps"]}`;

  const userPrompt = conversationContext?.previous_topic
    ? `Previous topic: ${conversationContext.previous_topic}\n\nCurrent query: ${originalQuery}`
    : originalQuery;

  try {
    const response = await fetch("https://api.openai.com/v1/chat/completions", {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${openaiApiKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        model: "gpt-4o-mini",
        messages: [
          { role: "system", content: systemPrompt },
          { role: "user", content: userPrompt },
        ],
        response_format: { type: "json_object" },
        temperature: 0.3,
        max_tokens: 200,
      }),
    });

    if (!response.ok) {
      throw new Error(`OpenAI API error: ${response.statusText}`);
    }

    const data = await response.json();
    const result = JSON.parse(data.choices[0].message.content);

    return {
      enhanced_query: result.enhanced_query || originalQuery,
      search_terms: result.search_terms || [originalQuery],
    };
  } catch (error) {
    console.error("LLM enhancement failed, using original query:", error);
    // Fallback to original query
    return {
      enhanced_query: originalQuery,
      search_terms: [originalQuery],
    };
  }
}

serve(async (req) => {
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }

  try {
    const supabaseUrl = Deno.env.get("SUPABASE_URL")!;
    const supabaseKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
    const supabase = createClient(supabaseUrl, supabaseKey);

    const {
      query,
      max_documents = 3,
      use_llm_enhancement = true,
      conversation_context = null,
      filter_by_type = null,
    }: DocumentRouterRequest = await req.json();

    if (!query || query.trim().length === 0) {
      return new Response(
        JSON.stringify({ error: "query is required" }),
        { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    console.log(`Document routing for: "${query}"`);

    // STEP 1: Enhance query using LLM
    let enhancedQuery = query;
    let searchTerms = [query];

    if (use_llm_enhancement) {
      const enhancement = await enhanceQuery(query, conversation_context);
      enhancedQuery = enhancement.enhanced_query;
      searchTerms = enhancement.search_terms;
      console.log(`Enhanced query: "${enhancedQuery}"`);
      console.log(`Search terms: ${searchTerms.join(", ")}`);
    }

    // STEP 2: Search document summaries using FTS
    // Build search query combining all terms with OR
    const searchQuery = searchTerms.join(" | ");

    let documentsQuery = supabase
      .from("document_index")
      .select("id, title, summary, document_type, total_pages, total_chunks, tags, categories")
      .eq("status", "completed")
      .textSearch("summary", searchQuery, {
        type: "websearch",
        config: "english",
      });

    // Optional type filtering
    if (filter_by_type) {
      documentsQuery = documentsQuery.eq("document_type", filter_by_type);
    }

    const { data: documents, error: searchError } = await documentsQuery
      .limit(max_documents * 2);  // Get more candidates for ranking

    if (searchError) {
      throw new Error(`Document search failed: ${searchError.message}`);
    }

    if (!documents || documents.length === 0) {
      // No documents found via FTS, try fallback with title search
      console.log("No FTS results, trying title search");

      const { data: titleDocs, error: titleError } = await supabase
        .from("document_index")
        .select("id, title, summary, document_type, total_pages, total_chunks, tags, categories")
        .eq("status", "completed")
        .ilike("title", `%${searchTerms[0]}%`)
        .limit(max_documents);

      if (titleError || !titleDocs || titleDocs.length === 0) {
        // Still nothing? Return all documents (fallback for single-doc or broad search)
        const { data: allDocs } = await supabase
          .from("document_index")
          .select("id, title, summary, document_type, total_pages, total_chunks")
          .eq("status", "completed")
          .limit(max_documents);

        return new Response(
          JSON.stringify({
            success: true,
            query: query,
            enhanced_query: enhancedQuery,
            search_terms: searchTerms,
            routing_strategy: "fallback_all",
            documents: allDocs || [],
            doc_ids: (allDocs || []).map((d: any) => d.id),
            total_found: (allDocs || []).length,
          }),
          {
            status: 200,
            headers: { ...corsHeaders, "Content-Type": "application/json" },
          }
        );
      }

      documents.push(...titleDocs);
    }

    // STEP 3: Rank documents by relevance
    // Simple ranking: count how many search terms appear in title + summary
    const rankedDocs = documents.map((doc: any) => {
      const titleLower = (doc.title || "").toLowerCase();
      const summaryLower = (doc.summary || "").toLowerCase();
      const combinedText = `${titleLower} ${summaryLower}`;

      let score = 0;
      searchTerms.forEach((term) => {
        const termLower = term.toLowerCase();
        // Title matches count more
        if (titleLower.includes(termLower)) score += 3;
        // Summary matches count less
        if (summaryLower.includes(termLower)) score += 1;
      });

      // Bonus for exact query match
      if (combinedText.includes(query.toLowerCase())) {
        score += 5;
      }

      return { ...doc, relevance_score: score };
    });

    // Sort by score descending
    rankedDocs.sort((a, b) => b.relevance_score - a.relevance_score);

    // Take top N
    const topDocs = rankedDocs.slice(0, max_documents);

    // Extract doc_ids
    const docIds = topDocs.map((d: any) => d.id);

    return new Response(
      JSON.stringify({
        success: true,
        query: query,
        enhanced_query: enhancedQuery,
        search_terms: searchTerms,
        routing_strategy: "llm_enhanced_fts",
        documents: topDocs,
        doc_ids: docIds,
        total_found: documents.length,
        total_returned: topDocs.length,
      }),
      {
        status: 200,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      }
    );
  } catch (error) {
    console.error("Document routing error:", error);
    return new Response(
      JSON.stringify({ error: error.message }),
      { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  }
});
