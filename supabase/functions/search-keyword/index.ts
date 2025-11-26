// Supabase Edge Function: Keyword Search (FTS only)
// Pure full-text search for exact technical terms, model numbers, error codes

import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2.38.4";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

interface KeywordSearchRequest {
  query: string;
  doc_id?: string;
  top_k?: number;
  include_images?: boolean;
  include_tables?: boolean;
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
      doc_id = null,
      top_k = 10,
      include_images = false,
      include_tables = false,
    }: KeywordSearchRequest = await req.json();

    if (!query) {
      return new Response(
        JSON.stringify({ error: "Query parameter is required" }),
        { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    console.log(`Keyword search: "${query}" (top_k=${top_k}, doc_id=${doc_id})`);

    // Search chunks
    const { data: chunks, error: chunkError } = await supabase.rpc("search_chunks_keyword", {
      p_query: query,
      p_doc_id: doc_id,
      p_limit: top_k,
    });

    if (chunkError) {
      throw new Error(`Chunk search failed: ${chunkError.message}`);
    }

    const result: any = {
      success: true,
      query,
      chunks: chunks || [],
    };

    // Optionally search images
    if (include_images) {
      const { data: images, error: imageError } = await supabase.rpc("search_images_keyword", {
        p_query: query,
        p_doc_id: doc_id,
        p_limit: 5,
      });

      if (!imageError) {
        result.images = images || [];
      }
    }

    // Optionally search tables
    if (include_tables) {
      const { data: tables, error: tableError } = await supabase.rpc("search_tables_keyword", {
        p_query: query,
        p_doc_id: doc_id,
        p_limit: 5,
      });

      if (!tableError) {
        result.tables = tables || [];
      }
    }

    return new Response(JSON.stringify(result), {
      status: 200,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  } catch (error) {
    console.error("Keyword search error:", error);
    return new Response(
      JSON.stringify({ error: error.message }),
      { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  }
});
