// Supabase Edge Function: Context Expansion
// Expands seed chunks using document hierarchy (section chunk_ids arrays)
// Uses PageIndex and section relationships from Phase 1 ingestion

import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2.38.4";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

interface ContextExpansionRequest {
  chunk_ids: string[];
  doc_id?: string;
  token_budget?: number;
  expand_siblings?: boolean;  // Expand to other chunks in same section
  expand_parents?: boolean;   // Expand to parent section chunks
  expand_children?: boolean;  // Expand to child section chunks
  include_images?: boolean;   // Auto-retrieve images for expanded chunks
  include_tables?: boolean;   // Auto-retrieve tables for expanded chunks
}

// Simple token estimation (avg 4 chars per token)
function estimateTokens(text: string): number {
  return Math.ceil(text.length / 4);
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
      doc_id = null,
      token_budget = 8000,
      expand_siblings = true,
      expand_parents = true,
      expand_children = false,
      include_images = true,
      include_tables = true,
    }: ContextExpansionRequest = await req.json();

    if (!chunk_ids || !Array.isArray(chunk_ids) || chunk_ids.length === 0) {
      return new Response(
        JSON.stringify({ error: "chunk_ids array is required" }),
        { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    console.log(`Context expansion: ${chunk_ids.length} seeds, budget=${token_budget}`);

    // Fetch seed chunks with section references
    const { data: seedChunks, error: seedError } = await supabase
      .from("chunks")
      .select("id, doc_id, content, page_number, section_id, section_path, metadata")
      .in("id", chunk_ids);

    if (seedError) {
      throw new Error(`Seed chunk retrieval failed: ${seedError.message}`);
    }

    if (!seedChunks || seedChunks.length === 0) {
      return new Response(
        JSON.stringify({ error: "No seed chunks found" }),
        { status: 404, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    // Get doc_id from first seed chunk
    const targetDocId = doc_id || seedChunks[0].doc_id;

    // Fetch document hierarchy (critical for expansion)
    const { data: hierarchyData, error: hierarchyError } = await supabase
      .from("document_hierarchy")
      .select("hierarchy")
      .eq("doc_id", targetDocId)
      .single();

    if (hierarchyError || !hierarchyData) {
      console.warn("No hierarchy found, falling back to page-based expansion");
    }

    const hierarchy = hierarchyData?.hierarchy || { sections: [] };
    const sections = hierarchy.sections || [];

    // Build section lookup: section_id -> section object
    const sectionMap = new Map();
    sections.forEach((s: any) => {
      sectionMap.set(s.id, s);
    });

    const expandedChunks: any[] = [];
    const seenIds = new Set<string>();
    let totalTokens = 0;

    // Add seed chunks first
    for (const chunk of seedChunks!) {
      const tokens = estimateTokens(chunk.content);
      if (totalTokens + tokens > token_budget) break;
      
      expandedChunks.push({ ...chunk, is_seed: true });
      seenIds.add(chunk.id);
      totalTokens += tokens;
    }

    // Expansion stats
    let siblingsAdded = 0;
    let parentsAdded = 0;
    let childrenAdded = 0;
    const chunkIdsToFetch = new Set<string>();

    // Expansion Strategy using Hierarchy
    for (const seed of seedChunks!) {
      if (totalTokens >= token_budget) break;
      if (!seed.section_id) continue;

      const section = sectionMap.get(seed.section_id);
      if (!section) continue;

      // 1. Expand siblings: all chunks in the same section
      if (expand_siblings && section.chunk_ids) {
        for (const chunkId of section.chunk_ids) {
          if (!seenIds.has(chunkId)) {
            chunkIdsToFetch.add(chunkId);
          }
        }
      }

      // 2. Expand parents: chunks from parent sections
      if (expand_parents && section.parent_section_id) {
        const parentSection = sectionMap.get(section.parent_section_id);
        if (parentSection && parentSection.chunk_ids) {
          for (const chunkId of parentSection.chunk_ids) {
            if (!seenIds.has(chunkId)) {
              chunkIdsToFetch.add(chunkId);
            }
          }
        }
      }

      // 3. Expand children: chunks from child sections
      if (expand_children && section.child_section_ids) {
        for (const childSecId of section.child_section_ids) {
          const childSection = sectionMap.get(childSecId);
          if (childSection && childSection.chunk_ids) {
            for (const chunkId of childSection.chunk_ids) {
              if (!seenIds.has(chunkId)) {
                chunkIdsToFetch.add(chunkId);
              }
            }
          }
        }
      }
    }

    // Fetch all expansion chunks in one query
    if (chunkIdsToFetch.size > 0) {
      const { data: expansionChunks, error: expansionError } = await supabase
        .from("chunks")
        .select("id, doc_id, content, page_number, section_id, section_path, metadata")
        .in("id", Array.from(chunkIdsToFetch));

      if (!expansionError && expansionChunks) {
        // Sort by page order for natural reading flow
        expansionChunks.sort((a, b) => a.page_number - b.page_number);

        for (const chunk of expansionChunks) {
          if (seenIds.has(chunk.id)) continue;
          
          const tokens = estimateTokens(chunk.content);
          if (totalTokens + tokens > token_budget) break;

          // Determine expansion type
          let expansionType = "sibling";
          for (const seed of seedChunks!) {
            const seedSection = sectionMap.get(seed.section_id);
            if (!seedSection) continue;

            if (chunk.section_id === seed.section_id) {
              expansionType = "sibling";
              siblingsAdded++;
              break;
            } else if (chunk.section_id === seedSection.parent_section_id) {
              expansionType = "parent";
              parentsAdded++;
              break;
            } else if (seedSection.child_section_ids?.includes(chunk.section_id)) {
              expansionType = "child";
              childrenAdded++;
              break;
            }
          }

          expandedChunks.push({ ...chunk, is_seed: false, expansion_type: expansionType });
          seenIds.add(chunk.id);
          totalTokens += tokens;
        }
      }
    }

    // Sort by page order
    expandedChunks.sort((a, b) => {
      if (a.doc_id !== b.doc_id) return a.doc_id.localeCompare(b.doc_id);
      return a.page_number - b.page_number;
    });

    // ==================== AUTO-RETRIEVE IMAGES AND TABLES ====================
    let totalImages = 0;
    let totalTables = 0;

    if (include_images || include_tables) {
      // Extract unique section_ids from all expanded chunks
      const allSectionIds = [...new Set(expandedChunks.map(c => c.section_id).filter(Boolean))];
      const allPages = [...new Set(expandedChunks.map(c => c.page_number))];

      // Retrieve images if requested
      if (include_images) {
        const { data: images, error: imageError } = await supabase
          .from("images")
          .select("id, doc_id, page_number, section_id, s3_url, caption, basic_summary, bbox")
          .eq("doc_id", targetDocId)
          .or(`section_id.in.(${allSectionIds.join(",")}),page_number.in.(${allPages.join(",")})`);

        if (!imageError && images && images.length > 0) {
          totalImages = images.length;

          // Group images by section_id and page_number
          const imagesBySection = new Map<string, any[]>();
          const imagesByPage = new Map<number, any[]>();

          images.forEach((img: any) => {
            if (img.section_id) {
              if (!imagesBySection.has(img.section_id)) {
                imagesBySection.set(img.section_id, []);
              }
              imagesBySection.get(img.section_id)!.push(img);
            }
            if (!imagesByPage.has(img.page_number)) {
              imagesByPage.set(img.page_number, []);
            }
            imagesByPage.get(img.page_number)!.push(img);
          });

          // Attach images to relevant chunks
          expandedChunks.forEach((chunk: any) => {
            const chunkImages: any[] = [];

            // Prefer section match, fallback to page match
            if (chunk.section_id && imagesBySection.has(chunk.section_id)) {
              chunkImages.push(...imagesBySection.get(chunk.section_id)!);
            } else if (imagesByPage.has(chunk.page_number)) {
              chunkImages.push(...imagesByPage.get(chunk.page_number)!);
            }

            if (chunkImages.length > 0) {
              chunk.images = chunkImages.map((img: any) => ({
                image_id: img.id,
                s3_url: img.s3_url,
                caption: img.caption || "",
                summary: img.basic_summary || "",
                bbox: img.bbox,
                page_number: img.page_number,
              }));
            }
          });
        }
      }

      // Retrieve tables if requested
      if (include_tables) {
        const { data: tables, error: tableError } = await supabase
          .from("document_tables")
          .select("id, doc_id, page_number, section_id, markdown, description, key_insights, num_rows, num_cols, bbox")
          .eq("doc_id", targetDocId)
          .or(`section_id.in.(${allSectionIds.join(",")}),page_number.in.(${allPages.join(",")})`);

        if (!tableError && tables && tables.length > 0) {
          totalTables = tables.length;

          // Group tables by section_id and page_number
          const tablesBySection = new Map<string, any[]>();
          const tablesByPage = new Map<number, any[]>();

          tables.forEach((tbl: any) => {
            if (tbl.section_id) {
              if (!tablesBySection.has(tbl.section_id)) {
                tablesBySection.set(tbl.section_id, []);
              }
              tablesBySection.get(tbl.section_id)!.push(tbl);
            }
            if (!tablesByPage.has(tbl.page_number)) {
              tablesByPage.set(tbl.page_number, []);
            }
            tablesByPage.get(tbl.page_number)!.push(tbl);
          });

          // Attach tables to relevant chunks
          expandedChunks.forEach((chunk: any) => {
            const chunkTables: any[] = [];

            // Prefer section match, fallback to page match
            if (chunk.section_id && tablesBySection.has(chunk.section_id)) {
              chunkTables.push(...tablesBySection.get(chunk.section_id)!);
            } else if (tablesByPage.has(chunk.page_number)) {
              chunkTables.push(...tablesByPage.get(chunk.page_number)!);
            }

            if (chunkTables.length > 0) {
              chunk.tables = chunkTables.map((tbl: any) => ({
                table_id: tbl.id,
                markdown: tbl.markdown || "",
                description: tbl.description || "",
                insights: tbl.key_insights || "",
                page_number: tbl.page_number,
                rows: tbl.num_rows,
                cols: tbl.num_cols,
                bbox: tbl.bbox,
              }));
            }
          });
        }
      }
    }

    return new Response(
      JSON.stringify({
        success: true,
        expanded_chunks: expandedChunks,
        total_tokens: totalTokens,
        expansion_summary: {
          seed_chunks: seedChunks!.length,
          siblings_added: siblingsAdded,
          parents_added: parentsAdded,
          children_added: childrenAdded,
          total_chunks: expandedChunks.length,
          token_budget,
          tokens_used: totalTokens,
          hierarchy_used: sections.length > 0,
          images_retrieved: totalImages,
          tables_retrieved: totalTables,
        },
      }),
      {
        status: 200,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      }
    );
  } catch (error) {
    console.error("Context expansion error:", error);
    return new Response(
      JSON.stringify({ error: error.message }),
      { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  }
});
