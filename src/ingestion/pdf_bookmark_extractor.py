"""Extract PDF bookmarks/outline to complement Docling's section detection."""
from typing import List, Dict, Any, Optional
import pypdf


class PDFBookmarkExtractor:
    """Extract hierarchical bookmarks from PDF files."""
    
    def extract_bookmarks(self, pdf_path: str) -> List[Dict[str, Any]]:
        """
        Extract bookmarks from PDF.
        
        Returns list of bookmark dict with:
        - title: Bookmark text
        - level: Nesting level (0 = top)
        - page: Target page number (1-indexed to match Docling)
        """
        try:
            reader = pypdf.PdfReader(pdf_path)
            
            if not reader.outline:
                return []
            
            bookmarks = []
            self._process_outline(reader, reader.outline, bookmarks, level=1)
            
            return bookmarks
            
        except Exception as e:
            print(f"⚠️  Could not extract PDF bookmarks: {e}")
            return []
    
    def _process_outline(
        self,
        reader: pypdf.PdfReader,
        outline: List,
        bookmarks: List[Dict[str, Any]],
        level: int
    ):
        """Recursively process outline structure."""
        for item in outline:
            if isinstance(item, list):
                # Nested bookmarks
                self._process_outline(reader, item, bookmarks, level + 1)
            else:
                # Individual bookmark
                try:
                    # Extract title
                    if hasattr(item, 'title'):
                        title = item.title
                    elif isinstance(item, dict) and '/Title' in item:
                        title = item['/Title']
                    else:
                        title = 'Untitled'
                    
                    # Get page number from destination
                    page_num = None
                    if hasattr(item, 'page'):
                        page_obj = item.page
                        if page_obj is not None:
                            # Resolve indirect reference and find page
                            try:
                                page_obj_resolved = page_obj.get_object()
                                for i, p in enumerate(reader.pages):
                                    if p == page_obj or p.get_object() == page_obj_resolved:
                                        page_num = i + 1  # 1-indexed
                                        break
                            except (ValueError, AttributeError):
                                pass
                    
                    # Fallback: try indirect_reference comparison
                    if page_num is None and hasattr(page_obj, 'indirect_reference'):
                        try:
                            for i, p in enumerate(reader.pages):
                                if hasattr(p, 'indirect_reference'):
                                    if p.indirect_reference == page_obj.indirect_reference:
                                        page_num = i + 1
                                        break
                        except Exception:
                            pass
                    
                    # Default to page 1 if we couldn't determine
                    if page_num is None:
                        page_num = 1
                    
                    bookmarks.append({
                        'title': str(title),
                        'level': level,
                        'page': page_num
                    })
                    
                except Exception as e:
                    print(f"⚠️  Error processing bookmark '{title if 'title' in locals() else 'unknown'}': {e}")
                    continue
