// Supabase Edge Function: Retrieve Chunks with Images
// Fetches chunks and their associated images with S3 URLs

import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2.38.4";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

interface RetrieveImagesRequest {
  chunk_ids: string[];
  include_summaries?: boolean;
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
      include_summaries = true,
    }: RetrieveImagesRequest = await req.json();

    if (!chunk_ids || !Array.isArray(chunk_ids) || chunk_ids.length === 0) {
      return new Response(
        JSON.stringify({ error: "chunk_ids array is required" }),
        { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    console.log(`Retrieving ${chunk_ids.length} chunks with images`);

    // Fetch chunks with section_id for hierarchy-aware image retrieval
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

    const selectFields = include_summaries
      ? "id, doc_id, page_number, section_id, s3_url, caption, basic_summary, bbox"
      : "id, doc_id, page_number, section_id, s3_url, caption, bbox";

    // Fetch images by section_id (hierarchy-aware) AND page_number (fallback)
    const { data: images, error: imageError } = await supabase
      .from("images")
      .select(selectFields)
      .in("doc_id", docIds)
      .or(`section_id.in.(${sectionIds.join(",")}),section_id.is.null`);

    if (imageError) {
      console.warn("Image retrieval warning:", imageError.message);
    }

    // Group images by section_id first (preferred), then by page_number
    const imagesBySection = new Map<string, any[]>();
    const imagesByPage = new Map<number, any[]>();
    
    (images || []).forEach((img: any) => {
      // Group by section if available
      if (img.section_id) {
        if (!imagesBySection.has(img.section_id)) {
          imagesBySection.set(img.section_id, []);
        }
        imagesBySection.get(img.section_id)!.push(img);
      }
      
      // Also group by page as fallback
      if (!imagesByPage.has(img.page_number)) {
        imagesByPage.set(img.page_number, []);
      }
      imagesByPage.get(img.page_number)!.push(img);
    });

    // Attach images to chunks (section-aware)
    const chunksWithImages = chunks!.map((chunk: any) => {
      // Prefer images from same section, fallback to same page
      let chunkImages: any[] = [];
      
      if (chunk.section_id && imagesBySection.has(chunk.section_id)) {
        chunkImages = imagesBySection.get(chunk.section_id)!;
      } else {
        chunkImages = imagesByPage.get(chunk.page_number) || [];
      }
      
      return {
        ...chunk,
        images: chunkImages.map((img: any) => ({
          image_id: img.id,
          s3_url: img.s3_url,
          caption: img.caption || "",
          summary: include_summaries ? img.basic_summary : undefined,
          bbox: img.bbox,
          section_id: img.section_id,
          page_number: img.page_number,
        })),
      };
    });

    return new Response(
      JSON.stringify({
        success: true,
        chunks: chunksWithImages,
        total_chunks: chunksWithImages.length,
        total_images: images?.length || 0,
      }),
      {
        status: 200,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      }
    );
  } catch (error) {
    console.error("Retrieve images error:", error);
    return new Response(
      JSON.stringify({ error: error.message }),
      { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  }
});
