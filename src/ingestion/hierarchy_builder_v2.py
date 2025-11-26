"""Build document hierarchy with proper TOC structure and asset tracking."""
from __future__ import annotations
from typing import Dict, Any, List, Tuple, Optional
import os
import re
import sys
from pathlib import Path
sys.path.append('..')
from database.models import DocumentHierarchy, Section, Page, Chunk
from openai import OpenAI
from .pdf_bookmark_extractor import PDFBookmarkExtractor


class HierarchyBuilderV2:
    """Build proper document hierarchy with TOC parsing and asset tracking."""
    
    def __init__(self):
        self.openai_client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        self.model = os.getenv('DOC_SUMMARY_MODEL', 'gpt-4o-mini')
        
        # Section number patterns for hierarchy detection
        self.section_patterns = [
            (r'^(\d+)\.\s+(.+)$', 1),  # "1. Chapter" → Level 1
            (r'^(\d+)\.(\d+)\s+(.+)$', 2),  # "1.1 Section" → Level 2
            (r'^(\d+)\.(\d+)\.(\d+)\s+(.+)$', 3),  # "1.1.1 Subsection" → Level 3
            (r'^(\d+)\.(\d+)\.(\d+)\.(\d+)\s+(.+)$', 4),  # "1.1.1.1 Sub-subsection" → Level 4
        ]
    
    def build(
        self, 
        doc_json: Dict[str, Any], 
        doc_id: str,
        pdf_path: Optional[str] = None
    ) -> Tuple[DocumentHierarchy, List[Chunk], Dict[str, Any], Dict[str, Any]]:
        """
        Build hierarchy with proper TOC structure.
        
        Args:
            doc_json: Parsed Docling document
            doc_id: Document identifier
            pdf_path: Optional path to original PDF (for bookmark extraction)
        
        Returns:
            (DocumentHierarchy, List[Chunk], PageIndex dict, AssetIndex dict)
        """
        pages_data = doc_json.get("pages", [])
        
        print(f"\n🔨 Building hierarchy for {doc_id}...")
        print(f"   • Raw pages from Docling: {len(pages_data)}")
        
        # Phase 1: Extract PDF bookmarks (if available)
        print("\n1️⃣  Extracting PDF bookmarks...")
        bookmarks = self._extract_bookmarks(pdf_path) if pdf_path else []
        if bookmarks:
            print(f"   ✅ Found {len(bookmarks)} PDF bookmarks")
        else:
            print(f"   ⚠️  No bookmarks found, using Docling detection only")
        
        # Phase 2: Parse TOC structure from document
        print("\n2️⃣  Parsing TOC structure...")
        sections = self._parse_toc_structure_hybrid(pages_data, bookmarks)
        print(f"   ✅ Found {len(sections)} sections")
        
        # Phase 3: Build section tree with parent-child relationships (BEFORE chunking)
        print("\n3️⃣  Building section tree...")
        self._build_section_tree(sections)
        print(f"   ✅ Section tree built")
        
        # Phase 4: Build full section paths (BEFORE chunking so chunks inherit paths)
        print("\n4️⃣  Building section paths...")
        self._build_section_paths(sections)
        print(f"   ✅ Section paths built")
        
        # Phase 5: Create chunks and assign to sections (now sections have paths)
        print("\n5️⃣  Creating chunks and assigning to sections...")
        chunks, pages = self._create_chunks_and_assign(pages_data, sections, doc_id)
        print(f"   ✅ Created {len(chunks)} chunks across {len(pages)} pages")
        
        # Phase 6: Track images and tables
        print("\n6️⃣  Tracking images and tables...")
        asset_index = self._track_assets(doc_json, sections, pages)
        print(f"   ✅ Tracked {len(asset_index.get('images', {}))} images, {len(asset_index.get('tables', {}))} tables")
        
        # Phase 6.5: Add chunk ranges to sections
        print("\n6️⃣.5 Adding chunk ranges to sections...")
        self._add_chunk_ranges(sections)
        print(f"   ✅ Chunk ranges added to all sections")
        
        # Phase 7: Generate PageIndex
        print("\n7️⃣  Generating PageIndex...")
        page_index = self._generate_page_index(pages, sections, chunks)
        print(f"   ✅ PageIndex generated for {len(page_index)} pages")
        
        # Phase 7: Build hierarchy object
        hierarchy = DocumentHierarchy(
            doc_id=doc_id,
            pages=pages,
            sections=sections,
            total_pages=len(pages),
            total_chunks=len(chunks),
            total_sections=len(sections)
        )
        
        return hierarchy, chunks, page_index, asset_index
    
    def _extract_bookmarks(self, pdf_path: str) -> List[Dict[str, Any]]:
        """Extract bookmarks from PDF using PDFBookmarkExtractor."""
        try:
            extractor = PDFBookmarkExtractor()
            return extractor.extract_bookmarks(pdf_path)
        except Exception as e:
            print(f"   ⚠️  Bookmark extraction failed: {e}")
            return []
    
    def _parse_toc_structure_hybrid(
        self,
        pages_data: List[Dict[str, Any]],
        bookmarks: List[Dict[str, Any]]
    ) -> List[Section]:
        """
        Build TOC using hybrid approach:
        1. If PDF has bookmarks, use them as authoritative structure
        2. Match bookmark titles to Docling content for page/content mapping
        3. Fall back to Docling detection for bookmarks without matches
        """
        if not bookmarks:
            # No bookmarks - use pure Docling detection
            return self._parse_toc_structure(pages_data)
        
        # Extract Docling sections for matching
        docling_sections = self._parse_toc_structure(pages_data)
        
        # Build hybrid TOC
        hybrid_sections = []
        used_docling_sections = set()
        
        for bookmark in bookmarks:
            # Try to find matching Docling section by fuzzy title match
            best_match = None
            best_score = 0
            
            for i, ds in enumerate(docling_sections):
                if i in used_docling_sections:
                    continue
                
                # Simple similarity: check if bookmark title is substring or vice versa
                bm_title_lower = bookmark['title'].lower()
                ds_title_lower = ds.title.lower()
                
                # Remove special chars for better matching
                bm_clean = re.sub(r'[^a-z0-9\s]', '', bm_title_lower)
                ds_clean = re.sub(r'[^a-z0-9\s]', '', ds_title_lower)
                
                score = 0
                if bm_clean == ds_clean:
                    score = 100  # Exact match
                elif bm_clean in ds_clean or ds_clean in bm_clean:
                    score = 80  # Substring match
                elif any(word in ds_clean for word in bm_clean.split() if len(word) > 3):
                    score = 50  # Word overlap
                
                if score > best_score and score >= 50:  # Threshold
                    best_score = score
                    best_match = (i, ds)
            
            # Create section from bookmark
            if best_match:
                i, ds = best_match
                used_docling_sections.add(i)
                # Use bookmark hierarchy + Docling page
                section = Section(
                    id=f"sec_{len(hybrid_sections):04d}",
                    title=bookmark['title'],  # Clean bookmark title
                    level=bookmark['level'],   # Bookmark hierarchy
                    start_page=ds.start_page,  # Docling's detected page
                    end_page=ds.end_page,
                    metadata={
                        'source': 'bookmark',
                        'bookmark_page': bookmark['page'],
                        'docling_match_score': best_score
                    }
                )
            else:
                # No Docling match - use bookmark page directly
                section = Section(
                    id=f"sec_{len(hybrid_sections):04d}",
                    title=bookmark['title'],
                    level=bookmark['level'],
                    start_page=bookmark['page'],
                    end_page=bookmark['page'],
                    metadata={
                        'source': 'bookmark_only',
                        'bookmark_page': bookmark['page']
                    }
                )
            
            hybrid_sections.append(section)
        
        # When we have bookmarks, trust them as the authoritative TOC
        # Don't add Docling sections - they're just OCR noise
        
        # Re-sort by page and position
        hybrid_sections.sort(key=lambda s: (s.start_page, s.level))
        
        # Re-assign section IDs
        for i, section in enumerate(hybrid_sections):
            section.id = f"sec_{i:04d}"
        
        return hybrid_sections
    
    def _parse_toc_structure(self, pages_data: List[Dict[str, Any]]) -> List[Section]:
        """
        Parse document structure to extract TOC with proper hierarchy.

        Uses section numbering patterns to determine hierarchy:
        - "1. Chapter" → Level 1
        - "1.1 Section" → Level 2
        - "1.1.1 Subsection" → Level 3

        Filters out document metadata (titles, copyright, etc.)
        """
        sections = []
        toc_pages = self._detect_toc_pages(pages_data)

        # Track seen section titles to avoid duplicates
        seen_titles = set()

        for page in pages_data:
            page_no = page.get("page_no", 1)  # Keep Docling's 1-indexed pages
            elements = page.get("elements", [])

            # Skip TOC pages - they contain links/references, not actual sections
            if page_no in toc_pages:
                print(f"   📑 Skipping TOC page {page_no}")
                continue

            for elem in elements:
                if elem.get("type") != "section_header":
                    continue

                text = elem.get("text", "").strip()
                if not text or len(text) < 3:
                    continue

                # ===== COMPREHENSIVE NOISE FILTERING =====

                # 1. Filter header/footer patterns
                if self._is_header_footer_noise(text):
                    continue

                # 2. Filter cookie banners and legal text
                if self._is_cookie_or_legal_text(text):
                    continue

                # 3. Filter URLs and technical identifiers
                if self._is_url_or_identifier(text):
                    continue

                # 4. Filter navigation/TOC links (e.g., "Previous Study Guides (link)")
                if self._is_navigation_link(text):
                    continue

                # 5. Filter very short ambiguous text
                if len(text) < 10:
                    continue

                # 6. Filter document metadata on first page
                if page_no == 1 and self._is_document_metadata(text):
                    continue

                # 7. Skip duplicate section titles (likely repeated headers)
                text_lower = text.lower()
                if text_lower in seen_titles:
                    continue

                # ===== SECTION PATTERN MATCHING =====

                # Try to match section number patterns
                section_number = None
                section_title = text
                level = 1  # Default level

                for pattern, detected_level in self.section_patterns:
                    match = re.match(pattern, text)
                    if match:
                        groups = match.groups()
                        # Last group is always the title
                        section_title = groups[-1].strip()
                        # Everything before is the number
                        section_number = '.'.join(groups[:-1])
                        level = detected_level
                        break

                # If no pattern matched, try to infer from Docling's level hint
                if section_number is None:
                    docling_level = elem.get("level", 1)
                    level = docling_level if docling_level > 0 else 1

                # Only add if it looks like a real section
                if self._is_valid_section_title(section_title):
                    section = Section(
                        id=f"sec_{len(sections):04d}",
                        title=section_title,
                        level=level,
                        start_page=page_no,
                        end_page=page_no,
                        metadata={
                            'section_number': section_number,
                            'raw_title': text
                        }
                    )

                    sections.append(section)
                    seen_titles.add(text_lower)

        return sections

    def _detect_toc_pages(self, pages_data: List[Dict[str, Any]]) -> set:
        """
        Detect which pages are Table of Contents pages.

        TOC pages have characteristics:
        - Many section headers in a row (> 5)
        - Short text fragments
        - Lots of dots or page numbers
        - Keywords: "Contents", "Table of Contents"
        """
        toc_pages = set()

        for page in pages_data:
            page_no = page.get("page_no", 1)
            elements = page.get("elements", [])

            # Count characteristics
            section_headers = 0
            has_toc_keyword = False
            has_many_dots = 0
            has_page_numbers = 0

            for elem in elements:
                text = elem.get("text", "").strip()
                elem_type = elem.get("type", "text")

                # Check for TOC keywords
                if re.search(r'\b(table of )?contents\b', text, re.IGNORECASE):
                    has_toc_keyword = True

                # Count section headers
                if elem_type == "section_header":
                    section_headers += 1

                # Count dots (common in TOC lines: "Chapter 1 ......... 5")
                if text.count('.') > 5:
                    has_many_dots += 1

                # Check for page number patterns
                if re.search(r'\d+\s*$', text):  # Ends with number
                    has_page_numbers += 1

            # Heuristic: TOC page if many headers + dots + page numbers
            if has_toc_keyword or (section_headers > 8 and has_many_dots > 3):
                toc_pages.add(page_no)

        return toc_pages

    def _is_header_footer_noise(self, text: str) -> bool:
        """Check if text is likely header/footer noise."""
        patterns = [
            r'^\s*page\s+\d+\s*$',  # "Page 5"
            r'^\s*\d+\s*$',  # Just numbers
            r'^\s*\d+\s*/\s*\d+\s*$',  # "5 / 10"
            r'\.pdf$',  # PDF filename
            r'\.docx?$',  # Word filename
            r'^Chapter\s+\d+\s*$',  # Just "Chapter 5" with no title
            r'^Section\s+\d+\.?\d*\s*$',  # Just "Section 1.2" with no title
            r'^\d{4}-\d{2}-\d{2}',  # Dates
            r'confidential',  # Common header
            r'proprietary',  # Common header
            r'copyright\s+©',  # Copyright notices
            r'all rights reserved',  # Legal footer
        ]

        text_lower = text.lower()
        return any(re.search(pattern, text_lower) for pattern in patterns)

    def _is_cookie_or_legal_text(self, text: str) -> bool:
        """Check if text is cookie banner or legal notice."""
        keywords = [
            'cookie', 'privacy policy', 'privacy statement', 'gdpr',
            'accept cookies', 'manage cookies', 'cookie settings',
            'we use cookies', 'this website uses', 'terms of service',
            'terms and conditions', 'legal notice', 'disclaimer'
        ]

        text_lower = text.lower()
        return any(keyword in text_lower for keyword in keywords)

    def _is_url_or_identifier(self, text: str) -> bool:
        """Check if text is a URL, email, or technical identifier."""
        patterns = [
            r'https?://',  # URLs
            r'www\.',  # URLs
            r'@[a-z0-9]+\.',  # Emails
            r'^[A-Z_]{3,}$',  # ALL_CAPS_IDENTIFIERS
            r'^[a-z]+\.[a-z]+\.[a-z]+',  # domain.name.com
            r'^\[.*\]$',  # [Bracketed text]
            r'^<.*>$',  # <Angled text>
        ]

        return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)

    def _is_navigation_link(self, text: str) -> bool:
        """Check if text is a navigation link or TOC reference."""
        keywords = [
            'previous', 'next', 'back to', 'go to', 'see also',
            'related', 'reference', 'link', 'click here', 'more info'
        ]

        text_lower = text.lower()

        # Check for keywords
        if any(keyword in text_lower for keyword in keywords):
            return True

        # Check for pattern: "Text (/some/url/path)"
        if re.search(r'\([/a-z0-9\-_]+\)', text_lower):
            return True

        return False

    def _is_document_metadata(self, text: str) -> bool:
        """Check if text is document metadata (title, author, version, etc.)."""
        patterns = [
            r'^version\s+\d',  # "Version 2.0"
            r'^rev\.?\s*\d',  # "Rev 1.2"
            r'^draft',  # "Draft"
            r'^document\s+(title|name|id)',  # "Document Title"
            r'^author:',  # "Author: John"
            r'^date:',  # "Date: 2024"
            r'^prepared by',  # "Prepared by"
            r'^approved by',  # "Approved by"
            r'^status:',  # "Status: Final"
        ]

        text_lower = text.lower()
        return any(re.search(pattern, text_lower) for pattern in patterns)

    def _is_valid_section_title(self, title: str) -> bool:
        """Check if title looks like a valid section heading."""
        # Must have some alphabetic characters
        if not re.search(r'[a-zA-Z]{3,}', title):
            return False

        # Should not be ALL CAPS (unless acronym)
        if title.isupper() and len(title.split()) > 1:
            # Exception: Acronyms like "API REFERENCE" are OK
            words = title.split()
            if not all(len(w) <= 4 for w in words):  # All words short = acronym
                return False

        # Should not be excessively long (> 150 chars = likely paragraph)
        if len(title) > 150:
            return False

        # Should not start with special chars
        if title[0] in ['#', '*', '-', '.', ',', ';', ':', '!', '?']:
            return False

        return True
    
    def _create_chunks_and_assign(
        self,
        pages_data: List[Dict[str, Any]],
        sections: List[Section],
        doc_id: str
    ) -> Tuple[List[Chunk], List[Page]]:
        """
        Create intelligent chunks by merging consecutive elements.
        
        Strategy:
        - Filter out headers/footers (very short, repeated text)
        - Merge consecutive elements until reaching target size (500-1500 chars)
        - Respect section boundaries (flush buffer on new section)
        - Preserve page and section context
        - Filter header/footer noise (filenames, page numbers, etc.)
        """
        # Production-optimized chunk sizes (read from .env or use defaults)
        TARGET_CHUNK_SIZE = int(os.getenv('CHUNK_SIZE', '1200'))  # Optimized for large PDFs
        MIN_CHUNK_SIZE = int(os.getenv('MIN_CHUNK_CHARS', '150'))  # Minimum viable
        MAX_CHUNK_SIZE = 2000     # Maximum before forcing split
        MIN_ELEMENT_SIZE = 30     # Filter out tiny fragments
        
        chunks = []
        pages = []
        
        current_section = None
        chunk_counter = 0
        
        # Buffer for merging elements
        chunk_buffer = []
        buffer_page = None
        buffer_section = None
        
        def flush_buffer():
            """Create chunk from buffer and reset."""
            nonlocal chunk_counter, chunk_buffer, buffer_page, buffer_section
            
            if not chunk_buffer:
                return None
            
            # Merge all buffered text
            content = " ".join(chunk_buffer).strip()
            
            # Enforce minimum chunk size (unless it's the last chunk)
            if len(content) < MIN_CHUNK_SIZE:
                chunk_buffer = []
                return None
            
            chunk_id = f"{doc_id}_chunk_{chunk_counter:06d}"
            chunk_counter += 1
            
            # Get section_path and level from current section
            section_path = None
            section_level = None
            parent_section_id = None
            
            if buffer_section:
                # Use the section_path built during _build_section_paths
                section_path = buffer_section.metadata.get('section_path')
                section_level = buffer_section.level
                parent_section_id = buffer_section.parent_section_id
            
            chunk = Chunk(
                id=chunk_id,
                doc_id=doc_id,
                content=content,
                page_number=buffer_page,
                bbox=None,  # Merged chunks don't have single bbox
                element_type="merged",
                section_id=buffer_section.id if buffer_section else None,
                parent_section_id=parent_section_id,
                section_path=section_path,
                section_level=section_level
            )
            
            # Update section
            if buffer_section:
                buffer_section.chunk_ids.append(chunk_id)
            
            chunk_buffer = []
            return chunk
        
        # Map deepest section by page for default assignment
        section_by_page: Dict[int, Section] = {}
        for sec in sections:
            for pno in range(sec.start_page or 0, (sec.end_page or sec.start_page or 0) + 1):
                if pno not in section_by_page or sec.level >= section_by_page[pno].level:
                    section_by_page[pno] = sec
        
        for page_data in pages_data:
            page_no = page_data.get("page_no", 1)  # Keep Docling's 1-indexed pages (matches sections)
            elements = page_data.get("elements", [])
            
            # Initialize buffer_page if not set
            if buffer_page is None:
                buffer_page = page_no
            
            # Default current and buffer section to the page's deepest section
            if current_section is None:
                current_section = section_by_page.get(page_no)
            if buffer_section is None:
                buffer_section = current_section
            
            page = Page(page_no=page_no)
            page_chunks = []
            
            for elem in elements:
                elem_type = elem.get("type", "text")
                
                # Check if this is a section header → flush buffer, switch section, include header
                if elem_type == "section_header":
                    text = elem.get("text", "").strip()
                    
                    # Flush any pending buffer
                    chunk = flush_buffer()
                    if chunk:
                        chunks.append(chunk)
                        page_chunks.append(chunk.id)
                    
                    # Find matching section
                    for section in sections:
                        if section.start_page == page_no:
                            raw_title = section.metadata.get('raw_title', section.title)
                            if text == raw_title or text == section.title:
                                current_section = section
                                page.section_ids.append(section.id)
                                # Add section header to buffer with markdown formatting
                                section_number = section.metadata.get('section_number', '')
                                if section_number:
                                    chunk_buffer.append(f"## {section_number} {section.title}")
                                else:
                                    chunk_buffer.append(f"## {section.title}")
                                buffer_section = current_section
                                buffer_page = page_no
                                break
                    
                    continue
                
                # Skip non-content elements
                if elem_type not in ["text", "paragraph", "list_item"]:
                    continue
                
                text = elem.get("text", "").strip()
                
                # Filter out very short text (likely headers/footers)
                if len(text) < MIN_ELEMENT_SIZE:
                    continue
                
                # **NEW: Header/Footer Noise Filter**
                # Skip document filename patterns
                if re.match(r'^.+\.(docx?|pdf)$', text, re.IGNORECASE):
                    continue
                
                # Skip standalone page numbers and simple repeated headers
                if re.match(r'^\s*\d+\s*$', text):  # Just page numbers
                    continue
                
                if re.match(r'^(page|p\.?)\s*\d+\s*$', text, re.IGNORECASE):  # "Page 5"
                    continue
                
                # Skip very short repeated text (headers/footers < 60 chars)
                if len(text) < 60:
                    # Count occurrences across all pages (simple heuristic)
                    occurrences = sum(1 for p in pages_data for e in p.get('elements', []) 
                                     if e.get('text', '').strip() == text)
                    if occurrences > 3:  # Appears on 3+ pages = likely header/footer
                        continue
                
                # Check if section changed → flush buffer
                if buffer_section != current_section:
                    chunk = flush_buffer()
                    if chunk:
                        chunks.append(chunk)
                        page_chunks.append(chunk.id)
                    buffer_section = current_section
                    buffer_page = page_no
                
                # Add to buffer
                chunk_buffer.append(text)
                
                # Check if buffer is large enough
                buffer_size = sum(len(t) for t in chunk_buffer)
                if buffer_size >= TARGET_CHUNK_SIZE:
                    chunk = flush_buffer()
                    if chunk:
                        chunks.append(chunk)
                        page_chunks.append(chunk.id)
                    buffer_page = page_no
            
            # Track page
            page.chunk_ids = page_chunks
            page.chunk_count = len(page_chunks)
            pages.append(page)
        
        # Flush any remaining buffer
        chunk = flush_buffer()
        if chunk:
            chunks.append(chunk)
            if pages:
                pages[-1].chunk_ids.append(chunk.id)
                pages[-1].chunk_count += 1
        
        return chunks, pages
    
    def _build_section_tree(self, sections: List[Section]):
        """
        Build parent-child relationships based on section levels.
        
        Rules:
        - A section's parent is the nearest previous section with level < current level
        - Example: Section 1.1.1 (level 3) → parent is Section 1.1 (level 2)
        """
        for i, section in enumerate(sections):
            # Find parent: nearest previous section with lower level
            for j in range(i - 1, -1, -1):
                prev_section = sections[j]
                if prev_section.level < section.level:
                    section.parent_section_id = prev_section.id
                    prev_section.child_section_ids.append(section.id)
                    break
    
    def _build_section_paths(self, sections: List[Section]):
        """
        Build full section paths for each section.
        
        Example: Section 1.1.1 → ['Chapter 1: Basics', 'Section 1.1: Overview', 'Subsection 1.1.1: Details']
        """
        # Create lookup dict
        section_dict = {s.id: s for s in sections}
        
        for section in sections:
            path = []
            current = section
            
            # Traverse up the tree
            while current:
                # Build readable section name
                number = current.metadata.get('section_number')
                if number:
                    name = f"{number} {current.title}"
                else:
                    name = current.title
                
                path.insert(0, name)
                
                # Move to parent
                if current.parent_section_id:
                    current = section_dict.get(current.parent_section_id)
                else:
                    break
            
            section.metadata['section_path'] = path
    
    def _track_assets(
        self,
        pages_data: List[Dict[str, Any]],
        sections: List[Section],
        pages: List[Page]
    ) -> Dict[str, Any]:
        """
        Track images and tables with section/page references.
        
        Updates Page objects with image_ids and table_ids.
        Returns asset_index for separate storage.
        """
        asset_index = {
            "images": {},
            "tables": {}
        }
        
        # Build section lookup by page
        section_by_page = {}
        for section in sections:
            for page_no in range(section.start_page, section.end_page + 1):
                if page_no not in section_by_page or section.level >= section_by_page[page_no].level:
                    section_by_page[page_no] = section
        
        # Build page lookup by page_no
        page_by_no = {p.page_no: p for p in pages}
        
        # Track images from doc_json['pictures']
        pictures = pages_data.get('pictures', [])
        for idx, picture in enumerate(pictures):
            prov = picture.get('prov', [])
            if not prov:
                continue

            page_no = prov[0].get('page_no', 1)  # FIXED: Use 'page_no' not 'page'
            bbox = prov[0].get('bbox')
            section = section_by_page.get(page_no)
            
            caption = picture.get('text', '').strip()
            number = self._extract_asset_number(caption, 'figure')
            image_id = f"img_{idx:03d}"
            
            # Store in asset_index
            asset_index['images'][image_id] = {
                'id': image_id,
                'number': number,
                'caption': caption,
                'page': page_no,
                'section_id': section.id if section else None,
                'section_title': section.title if section else None,
                'bbox': bbox
            }
            
            # NEW: Update Page object
            if page_no in page_by_no:
                page_by_no[page_no].image_ids.append(image_id)
                page_by_no[page_no].image_count += 1
        
        # Track tables from doc_json['tables']
        tables = pages_data.get('tables', [])
        for idx, table in enumerate(tables):
            prov = table.get('prov', [])
            if not prov:
                continue
            
            page_no = prov[0].get('page_no', 1)  # FIXED: Use 'page_no' not 'page'
            bbox = prov[0].get('bbox')
            section = section_by_page.get(page_no)

            caption = table.get('text', '').strip()
            number = self._extract_asset_number(caption, 'table')
            table_id = f"tbl_{idx:03d}"
            
            # Store in asset_index
            asset_index['tables'][table_id] = {
                'id': table_id,
                'number': number,
                'caption': caption,
                'page': page_no,
                'section_id': section.id if section else None,
                'section_title': section.title if section else None,
                'bbox': bbox
            }
            
            # NEW: Update Page object
            if page_no in page_by_no:
                page_by_no[page_no].table_ids.append(table_id)
                page_by_no[page_no].table_count += 1
        
        return asset_index
    
    def _add_chunk_ranges(self, sections: List[Section]):
        """
        Add chunk range metadata to sections for quick lookup.
        
        Adds to section.metadata:
        - chunk_start: First chunk ID in section
        - chunk_end: Last chunk ID in section
        - chunk_range: [start_idx, end_idx] for quick slicing
        """
        for section in sections:
            if not section.chunk_ids:
                continue
            
            # Add chunk range metadata
            section.metadata['chunk_start'] = section.chunk_ids[0]
            section.metadata['chunk_end'] = section.chunk_ids[-1]
            section.metadata['chunk_count'] = len(section.chunk_ids)
            
            # Extract numeric indices for easier range queries
            try:
                start_idx = int(section.chunk_ids[0].split('_')[-1])
                end_idx = int(section.chunk_ids[-1].split('_')[-1])
                section.metadata['chunk_range'] = [start_idx, end_idx]
            except:
                pass
    
    def _extract_asset_number(self, text: str, asset_type: str) -> Optional[str]:
        """
        Extract asset number from caption or text.
        
        Examples:
        - "Figure 1: System Architecture" → "Figure 1"
        - "Table 2.1 - Browser Comparison" → "Table 2.1"
        """
        if not text:
            return None
        
        # Patterns for different asset types
        patterns = {
            "figure": r'(Figure|Fig\.?)\s+(\d+(?:\.\d+)?)',
            "table": r'(Table|Tbl\.?)\s+(\d+(?:\.\d+)?)',
            "image": r'(Image|Img\.?)\s+(\d+(?:\.\d+)?)'
        }
        
        pattern = patterns.get(asset_type.lower())
        if not pattern:
            return None
        
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return f"{match.group(1).capitalize()} {match.group(2)}"
        
        return None
    
    def _generate_page_index(
        self,
        pages: List[Page],
        sections: List[Section],
        chunks: List[Chunk]
    ) -> Dict[str, Any]:
        """Generate PageIndex with page summaries."""
        page_index = {}
        
        for page in pages:
            # Get chunks on this page
            page_chunks = [c for c in chunks if c.page_number == page.page_no]
            
            if not page_chunks:
                continue
            
            # Generate summary
            page_content = "\n".join([c.content for c in page_chunks[:10]])
            
            try:
                summary = self._generate_page_summary(page_content, page.page_no)
            except Exception as e:
                print(f"⚠️  Warning: Could not generate summary for page {page.page_no}: {e}")
                summary = f"Page {page.page_no} content"
            
            # Get sections on this page
            page_sections = [s for s in sections if s.start_page <= page.page_no <= s.end_page]
            
            page_index[str(page.page_no)] = {
                "summary": summary,
                "section_ids": page.section_ids,
                "key_topics": self._extract_key_topics(page_content),
                "has_images": page.image_count > 0,
                "image_count": page.image_count,
                "has_tables": page.table_count > 0,
                "table_count": page.table_count,
                "chunk_count": len(page_chunks),
                "sections": [
                    {
                        "id": s.id,
                        "title": s.title,
                        "level": s.level
                    }
                    for s in page_sections
                ]
            }
        
        return page_index
    
    def _generate_page_summary(self, content: str, page_no: int) -> str:
        """Generate 1-sentence summary of page content."""
        max_chars = 2000
        truncated = content[:max_chars] if len(content) > max_chars else content
        
        response = self.openai_client.chat.completions.create(
            model=self.model,
            messages=[{
                "role": "user",
                "content": f"""Summarize this page content in ONE sentence (max 15 words):

{truncated}

Summary:"""
            }],
            max_tokens=50,
            temperature=0.3
        )
        
        return response.choices[0].message.content.strip()
    
    def _extract_key_topics(self, content: str, max_topics: int = 5) -> List[str]:
        """Extract key topics from page content."""
        words = content.lower().split()
        
        # Simple keyword extraction
        keywords = set()
        for word in words:
            # Filter: length > 4, alphabetic, not common words
            if len(word) > 4 and word.isalpha():
                if word not in ['about', 'there', 'their', 'where', 'which', 'these', 'those']:
                    keywords.add(word)
        
        return list(keywords)[:max_topics]
