// Supabase Edge Function: Retrieve Chunks with Tables
// Fetches chunks and their associated structured tables with LLM insights

import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2.38.4";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

interface RetrieveTablesRequest {
  chunk_ids: string[];
  include_markdown?: boolean;
  include_insights?: boolean;
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
      chunk_ids,
      include_markdown = true,
      include_insights = true,
    }: RetrieveTablesRequest = await req.json();

    if (!chunk_ids || !Array.isArray(chunk_ids) || chunk_ids.length === 0) {
      return new Response(
        JSON.stringify({ error: "chunk_ids array is required" }),
        { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    console.log(`Retrieving ${chunk_ids.length} chunks with tables`);

    // Fetch chunks with section_id for hierarchy-aware table retrieval
    const { data: chunks, error: chunkError } = await supabase
      .from("chunks")
      .select("id, doc_id, content, page_number, section_id, section_path, metadata")
      .in("id", chunk_ids);

    if (chunkError) {
      throw new Error(`Chunk retrieval failed: ${chunkError.message}`);
    }

    // Extract unique section_ids and doc_ids
    const sectionIds = [...new Set(chunks!.map((c: any) => c.section_id).filter(Boolean))];
    const docIds = [...new Set(chunks!.map((c: any) => c.doc_id))];

    let selectFields = "id, doc_id, page_number, section_id, bbox";
    if (include_markdown) {
      selectFields += ", markdown, num_rows, num_cols";
    }
    if (include_insights) {
      selectFields += ", description, key_insights";
    }

    // Fetch tables by section_id (hierarchy-aware) AND page_number (fallback)
    const { data: tables, error: tableError } = await supabase
      .from("document_tables")
      .select(selectFields)
      .in("doc_id", docIds)
      .or(`section_id.in.(${sectionIds.join(",")}),section_id.is.null`);

    if (tableError) {
      console.warn("Table retrieval warning:", tableError.message);
    }

    // Group tables by section_id first (preferred), then by page_number
    const tablesBySection = new Map<string, any[]>();
    const tablesByPage = new Map<number, any[]>();
    
    (tables || []).forEach((tbl: any) => {
      // Group by section if available
      if (tbl.section_id) {
        if (!tablesBySection.has(tbl.section_id)) {
          tablesBySection.set(tbl.section_id, []);
        }
        tablesBySection.get(tbl.section_id)!.push(tbl);
      }
      
      // Also group by page as fallback
      if (!tablesByPage.has(tbl.page_number)) {
        tablesByPage.set(tbl.page_number, []);
      }
      tablesByPage.get(tbl.page_number)!.push(tbl);
    });

    // Attach tables to chunks (section-aware)
    const chunksWithTables = chunks!.map((chunk: any) => {
      // Prefer tables from same section, fallback to same page
      let chunkTables: any[] = [];
      
      if (chunk.section_id && tablesBySection.has(chunk.section_id)) {
        chunkTables = tablesBySection.get(chunk.section_id)!;
      } else {
        chunkTables = tablesByPage.get(chunk.page_number) || [];
      }
      
      return {
        ...chunk,
        tables: chunkTables.map((tbl: any) => {
          const result: any = {
            table_id: tbl.id,
            page_number: tbl.page_number,
            section_id: tbl.section_id,
            bbox: tbl.bbox,
          };

          if (include_markdown) {
            result.markdown = tbl.markdown || "";
            result.rows = tbl.num_rows;
            result.cols = tbl.num_cols;
          }

          if (include_insights) {
            result.description = tbl.description || "";
            result.insights = tbl.key_insights || "";
          }

          return result;
        }),
      };
    });

    return new Response(
      JSON.stringify({
        success: true,
        chunks: chunksWithTables,
        total_chunks: chunksWithTables.length,
        total_tables: tables?.length || 0,
      }),
      {
        status: 200,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      }
    );
  } catch (error) {
    console.error("Retrieve tables error:", error);
    return new Response(
      JSON.stringify({ error: error.message }),
      { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  }
});
