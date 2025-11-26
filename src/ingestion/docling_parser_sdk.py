"""Docling SDK-based parser with native image extraction."""
from __future__ import annotations
import io
import base64
from typing import Dict, Any, List
from pathlib import Path

# Docling SDK imports
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions, EasyOcrOptions, TableFormerMode
from docling_core.types.doc.document import PictureItem, TableItem


class DoclingSDKParser:
    """Parse PDFs using Docling SDK with native image extraction."""
    
    def __init__(self):
        """Initialize with optimal pipeline options."""
        # Configure pipeline with latest best practices
        pipeline_options = PdfPipelineOptions()
        
        # Core extraction options
        pipeline_options.do_ocr = True
        pipeline_options.do_table_structure = True
        
        # IMAGE EXTRACTION - CRITICAL for your use case
        pipeline_options.generate_page_images = True
        pipeline_options.generate_picture_images = True  # Extract picture data!
        pipeline_options.images_scale = 2.0  # Higher resolution images
        
        # Picture classification (logo, chart, diagram, etc.)
        pipeline_options.do_picture_classification = True
        
        # OCR configuration - Use EasyOCR (matches local setup)
        pipeline_options.ocr_options = EasyOcrOptions(
            lang=["en"],
            confidence_threshold=0.5
        )
        
        # Table extraction with accurate mode
        pipeline_options.table_structure_options.mode = TableFormerMode.ACCURATE
        pipeline_options.table_structure_options.do_cell_matching = True
        
        # Initialize converter
        self.converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(
                    pipeline_options=pipeline_options
                )
            }
        )
    
    def parse_pdf(self, pdf_path: str) -> Dict[str, Any]:
        """
        Parse PDF and return structured data with IMAGES.
        
        Returns same structure as old parser but with actual image data:
            {
                "pages": [
                    {
                        "page_no": 0,
                        "elements": [
                            {
                                "type": "section_header" | "text" | "table" | "figure",
                                "text": "content",
                                "label": "section-header-1",
                                "level": 1,
                                "bbox": {...},
                                "page": 0
                            }
                        ]
                    }
                ],
                "pictures": [
                    {
                        "image": "base64_encoded_image_data",  # NOW WITH DATA!
                        "annotations": [...],
                        "prov": [{"page_no": 1, "bbox": {...}}],
                        ...
                    }
                ],
                "tables": [...]
            }
        """
        # Convert PDF
        print(f"🔄 Converting PDF with Docling SDK: {pdf_path}")
        result = self.converter.convert(pdf_path)
        doc = result.document
        
        # Extract structured data
        return self._convert_to_legacy_format(doc)
    
    def _convert_to_legacy_format(self, doc) -> Dict[str, Any]:
        """
        Convert Docling SDK document to your existing format.
        Maintains backward compatibility while adding image data.
        """
        # Organize elements by page
        page_elements: Dict[int, List[Dict[str, Any]]] = {}
        
        # Process all document items
        for item, level in doc.iterate_items():
            item_dict = self._process_item(item, level)
            if item_dict:
                page_no = item_dict["page"]
                page_elements.setdefault(page_no, []).append(item_dict)
        
        # Build pages array
        max_page = max(page_elements.keys()) if page_elements else 1
        min_page = min(page_elements.keys()) if page_elements else 1
        pages = []
        
        for page_no in range(min_page, max_page + 1):
            pages.append({
                "page_no": page_no,
                "elements": page_elements.get(page_no, [])
            })
        
        # Extract pictures WITH IMAGE DATA
        pictures = self._extract_pictures(doc)
        
        # Extract tables
        tables = self._extract_tables(doc)
        
        print(f"✅ Extracted: {len(pages)} pages, {len(pictures)} pictures with data, {len(tables)} tables")
        
        return {
            "pages": pages,
            "pictures": pictures,
            "tables": tables
        }
    
    def _process_item(self, item, level) -> Dict[str, Any] | None:
        """Process a single document item."""
        # Get provenance (location info)
        if not hasattr(item, 'prov') or not item.prov:
            return None
        
        prov = item.prov[0]
        page_no = prov.page_no
        bbox = {
            "l": prov.bbox.l,
            "t": prov.bbox.t,
            "r": prov.bbox.r,
            "b": prov.bbox.b
        } if hasattr(prov, 'bbox') and prov.bbox else None
        
        # Get text content
        text = getattr(item, 'text', '').strip()
        if not text:
            return None
        
        # Determine type and label
        label = getattr(item, 'label', 'text')
        item_type = "text"
        item_level = None
        
        # Check if it's a section header
        if hasattr(item, 'label'):
            if 'title' in label.lower():
                item_type = "section_header"
                item_level = 0
            elif 'section' in label.lower() or 'heading' in label.lower():
                item_type = "section_header"
                item_level = self._parse_level(label)
        
        result = {
            "type": item_type,
            "text": text,
            "label": label,
            "page": page_no,
            "bbox": bbox
        }
        
        if item_level is not None:
            result["level"] = item_level
        
        return result
    
    def _extract_pictures(self, doc) -> List[Dict[str, Any]]:
        """Extract pictures WITH actual image data."""
        pictures = []
        
        for item, _ in doc.iterate_items():
            if not isinstance(item, PictureItem):
                continue
            
            # Get image data as base64
            image_base64 = None
            try:
                if hasattr(item, 'image') and item.image:
                    # Get PIL image from Docling
                    pil_image = item.get_image(doc)
                    if pil_image:
                        # Convert to base64
                        buffer = io.BytesIO()
                        pil_image.save(buffer, format="PNG")
                        image_bytes = buffer.getvalue()
                        image_base64 = base64.b64encode(image_bytes).decode('utf-8')
            except Exception as e:
                print(f"⚠️  Failed to extract image: {e}")
            
            # Get provenance
            prov_list = []
            if hasattr(item, 'prov') and item.prov:
                for p in item.prov:
                    prov_list.append({
                        "page_no": p.page_no,
                        "bbox": {
                            "l": p.bbox.l,
                            "t": p.bbox.t,
                            "r": p.bbox.r,
                            "b": p.bbox.b
                        } if hasattr(p, 'bbox') and p.bbox else None
                    })
            
            # Get annotations (classifications, descriptions)
            annotations = []
            if hasattr(item, 'annotations'):
                for ann in item.annotations:
                    ann_dict = {
                        "type": ann.__class__.__name__
                    }
                    
                    # Picture classification (logo, chart, etc.)
                    if hasattr(ann, 'predicted_classes'):
                        ann_dict["predicted_classes"] = [
                            {
                                "class_name": cls.class_name,
                                "confidence": cls.confidence
                            }
                            for cls in ann.predicted_classes
                        ]
                    
                    # Picture description
                    if hasattr(ann, 'text'):
                        ann_dict["text"] = ann.text
                    
                    annotations.append(ann_dict)
            
            # Get caption
            caption = ""
            if hasattr(item, 'caption_text'):
                caption = item.caption_text(doc=doc)
            
            picture_dict = {
                "data": image_base64,  # Changed from 'image' to 'data' for compatibility
                "image": image_base64,  # Keep 'image' for backward compatibility
                "prov": prov_list,
                "annotations": annotations,
                "text": caption,  # Changed from 'caption' to 'text' for compatibility
                "caption": caption,  # Keep 'caption' for backward compatibility
                "self_ref": getattr(item, 'self_ref', '')
            }
            
            pictures.append(picture_dict)
        
        return pictures
    
    def _extract_tables(self, doc) -> List[Dict[str, Any]]:
        """Extract tables with structure."""
        tables = []
        
        for item, _ in doc.iterate_items():
            if not isinstance(item, TableItem):
                continue
            
            # Get provenance
            prov_list = []
            if hasattr(item, 'prov') and item.prov:
                for p in item.prov:
                    prov_list.append({
                        "page_no": p.page_no,
                        "bbox": {
                            "l": p.bbox.l,
                            "t": p.bbox.t,
                            "r": p.bbox.r,
                            "b": p.bbox.b
                        } if hasattr(p, 'bbox') and p.bbox else None
                    })
            
            # Get table data (convert TableData to list if needed)
            table_data = []
            if hasattr(item, 'data') and item.data:
                # TableData object has table_rows attribute or can be converted to grid
                if hasattr(item.data, 'table_rows'):
                    # Convert table rows to 2D list
                    table_data = [[cell.text for cell in row.cells] for row in item.data.table_rows]
                elif hasattr(item.data, 'grid'):
                    table_data = item.data.grid
                else:
                    # Try to iterate directly
                    try:
                        table_data = list(item.data)
                    except:
                        table_data = []
            
            # Convert table data to markdown for consistency
            markdown = self._table_to_markdown(table_data) if table_data else ""
            
            # Get caption if available
            caption = ""
            if hasattr(item, 'caption_text'):
                caption = item.caption_text(doc=doc)
            
            table_dict = {
                "data": table_data,
                "markdown": markdown,
                "prov": prov_list,
                "text": caption,
                "self_ref": getattr(item, 'self_ref', '')
            }
            
            tables.append(table_dict)
        
        return tables
    
    def _table_to_markdown(self, data) -> str:
        """Convert table data to markdown."""
        # Handle empty data
        if not data:
            return ""
        
        # Convert to list if it's not already
        if not isinstance(data, list):
            try:
                data = list(data)
            except:
                return ""
        
        if len(data) < 1:
            return ""
        
        try:
            # Header row
            if len(data) >= 2:
                headers = data[0]
                markdown = "| " + " | ".join(str(h) for h in headers) + " |\n"
                markdown += "|" + "|".join(["---" for _ in headers]) + "|\n"
                
                # Data rows
                for row in data[1:]:
                    markdown += "| " + " | ".join(str(cell) for cell in row) + " |\n"
            else:
                # Single row, treat as data
                markdown = "| " + " | ".join(str(cell) for cell in data[0]) + " |\n"
            
            return markdown
        except Exception as e:
            print(f"⚠️  Error converting table to markdown: {e}")
            return ""
    
    def _parse_level(self, label: str) -> int:
        """Parse section level from label."""
        label_lower = (label or "").lower()
        
        if "section" in label_lower or "heading" in label_lower:
            # Try to extract number (e.g., "section-header-1" -> 1)
            parts = label_lower.split("-")
            for part in parts:
                if part.isdigit():
                    return int(part)
            return 1
        
        return 99  # Unknown level
