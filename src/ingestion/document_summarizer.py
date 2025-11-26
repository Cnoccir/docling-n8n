"""Generate AI-powered document summaries for enhanced RAG context."""
import os
from typing import Dict, Any, Tuple
from openai import OpenAI


class DocumentSummarizer:
    """Generate document-level summaries using GPT-4o-mini."""
    
    def __init__(self):
        self.openai_client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        self.model = os.getenv('DOC_SUMMARY_MODEL', 'gpt-4o-mini')
    
    def generate_document_summary(self, doc_json: Dict[str, Any], title: str = None) -> Tuple[str, int]:
        """
        Generate a comprehensive document summary for query routing and context.
        
        Args:
            doc_json: Parsed document from Docling
            title: Optional document title
        
        Returns:
            (summary_text, tokens_used)
        """
        try:
            # Extract key content for summary generation
            content_sample = self._extract_content_sample(doc_json)
            
            # Build prompt
            prompt = self._build_summary_prompt(content_sample, title)
            
            # Generate summary
            response = self.openai_client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a technical document analyst. Generate concise, informative summaries "
                            "that help with document classification and query routing. Focus on document "
                            "purpose, scope, main topics, and target audience."
                        )
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.3,  # Low temperature for consistency
                max_tokens=400  # ~2-3 paragraphs
            )
            
            summary = response.choices[0].message.content.strip()
            tokens_used = response.usage.total_tokens
            
            return summary, tokens_used
        
        except Exception as e:
            print(f"⚠️  Error generating document summary: {e}")
            # Return fallback summary
            fallback = f"Technical document with {len(doc_json.get('pages', []))} pages."
            if title:
                fallback = f"{title}. " + fallback
            return fallback, 0
    
    def _extract_content_sample(self, doc_json: Dict[str, Any]) -> Dict[str, Any]:
        """Extract representative content for summarization."""
        pages = doc_json.get('pages', [])
        
        # Extract first page content (often contains introduction)
        first_page_content = []
        if pages:
            first_page = pages[0]
            for element in first_page.get('elements', []):
                text = element.get('text', '').strip()
                if text and len(text) > 20:  # Skip very short snippets
                    first_page_content.append(text)
        
        # Extract section headers (TOC structure)
        section_headers = []
        for page in pages[:10]:  # First 10 pages to capture TOC
            for element in page.get('elements', []):
                if element.get('type') == 'section_header':
                    text = element.get('text', '').strip()
                    if text:
                        section_headers.append(text)
        
        # Sample content from middle pages
        middle_content = []
        if len(pages) > 3:
            middle_idx = len(pages) // 2
            middle_page = pages[middle_idx]
            for element in middle_page.get('elements', [])[:5]:  # First 5 elements
                text = element.get('text', '').strip()
                if text and len(text) > 30:
                    middle_content.append(text)
        
        return {
            'total_pages': len(pages),
            'first_page_content': first_page_content[:10],  # First 10 paragraphs
            'section_headers': section_headers[:20],  # First 20 headers
            'middle_content': middle_content[:5],  # 5 sample paragraphs
            'has_images': len(doc_json.get('pictures', [])) > 0,
            'has_tables': len(doc_json.get('tables', [])) > 0
        }
    
    def _build_summary_prompt(self, content_sample: Dict[str, Any], title: str = None) -> str:
        """Build the prompt for summary generation."""
        prompt_parts = []
        
        # Document metadata
        prompt_parts.append(f"Document Analysis Request:")
        if title:
            prompt_parts.append(f"Title: {title}")
        prompt_parts.append(f"Total Pages: {content_sample['total_pages']}")
        prompt_parts.append(f"Contains Images: {'Yes' if content_sample['has_images'] else 'No'}")
        prompt_parts.append(f"Contains Tables: {'Yes' if content_sample['has_tables'] else 'No'}")
        prompt_parts.append("")
        
        # First page content
        if content_sample['first_page_content']:
            prompt_parts.append("First Page Content:")
            for para in content_sample['first_page_content'][:5]:  # Limit to avoid token bloat
                prompt_parts.append(f"- {para[:200]}")  # Truncate long paragraphs
            prompt_parts.append("")
        
        # Section structure
        if content_sample['section_headers']:
            prompt_parts.append("Main Sections/Headers:")
            for header in content_sample['section_headers'][:15]:
                prompt_parts.append(f"• {header}")
            prompt_parts.append("")
        
        # Sample content
        if content_sample['middle_content']:
            prompt_parts.append("Sample Content:")
            for para in content_sample['middle_content']:
                prompt_parts.append(f"- {para[:150]}")
            prompt_parts.append("")
        
        # Request
        prompt_parts.append("Generate a 2-3 paragraph summary covering:")
        prompt_parts.append("1. Document purpose and scope")
        prompt_parts.append("2. Main topics and sections covered")
        prompt_parts.append("3. Document type (e.g., manual, guide, specification, reference)")
        prompt_parts.append("4. Target audience and technical level")
        prompt_parts.append("5. Key concepts or technologies discussed")
        
        return "\n".join(prompt_parts)
