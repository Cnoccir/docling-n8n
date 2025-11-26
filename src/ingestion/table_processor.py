"""Table processing with LLM insights extraction."""
import os
from typing import List, Dict, Any
from openai import OpenAI


class TableProcessor:
    """Process tables from Docling with LLM insights."""
    
    def __init__(self):
        self.openai_client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        self.model = os.getenv('DOC_SUMMARY_MODEL', 'gpt-4o-mini')
    
    def process_tables(self, doc_json: Dict[str, Any], doc_id: str) -> List[Dict[str, Any]]:
        """Process all tables from Docling output."""
        tables_data = doc_json.get("tables", [])
        
        if not tables_data:
            return []
        
        print(f"Processing {len(tables_data)} tables...")
        
        processed_tables = []
        for idx, table_data in enumerate(tables_data):
            prov = table_data.get("prov", [])
            if not prov:
                continue

            page = prov[0].get("page_no", 1)  # FIXED: Use 'page_no' not 'page'
            bbox = prov[0].get("bbox")
            
            # Get structured data and convert TableCell objects to strings
            raw_data = table_data.get("data", [])
            structured_data = []
            for row in raw_data:
                str_row = []
                for cell in row:
                    if hasattr(cell, 'text'):
                        str_row.append(str(cell.text))
                    else:
                        str_row.append(str(cell))
                structured_data.append(str_row)
            
            # Convert to markdown
            markdown = self._convert_to_markdown(structured_data)
            
            if not markdown:
                continue
            
            # Extract insights with LLM
            description, key_insights = self._analyze_table(markdown)
            
            processed_tables.append({
                'id': f"{doc_id}_table_{page}_{idx:02d}",
                'doc_id': doc_id,
                'page_number': page,
                'bbox': bbox,
                'raw_html': table_data.get("html", ""),
                'markdown': markdown,
                'structured_data': structured_data,
                'title': table_data.get("title"),
                'description': description,
                'key_insights': key_insights
            })
        
        print(f"✅ Processed {len(processed_tables)} tables")
        return processed_tables
    
    def _convert_to_markdown(self, data) -> str:
        """Convert 2D array to markdown table."""
        if not data or len(data) < 2:
            return ""
        
        # Convert TableCell objects to strings if needed
        def cell_to_str(cell):
            if hasattr(cell, 'text'):
                return str(cell.text)
            return str(cell)
        
        # Header row
        headers = data[0]
        markdown = "| " + " | ".join(cell_to_str(h) for h in headers) + " |\n"
        markdown += "|" + "|".join(["---" for _ in headers]) + "|\n"
        
        # Data rows
        for row in data[1:]:
            markdown += "| " + " | ".join(cell_to_str(cell) for cell in row) + " |\n"
        
        return markdown
    
    def _analyze_table(self, markdown: str) -> tuple[str, List[str]]:
        """Extract description and key insights from table."""
        try:
            response = self.openai_client.chat.completions.create(
                model=self.model,
                messages=[{
                    "role": "user",
                    "content": f"""Analyze this table and provide:
1. A brief description (1 sentence)
2. Key insights (3-5 bullet points)

Table:
{markdown}

Format:
DESCRIPTION: ...
INSIGHTS:
- ...
- ..."""
                }],
                max_tokens=200,
                temperature=0.3
            )
            
            content = response.choices[0].message.content
            
            # Parse response
            description = ""
            insights = []
            
            lines = content.strip().split('\n')
            in_insights = False
            
            for line in lines:
                line = line.strip()
                if line.startswith('DESCRIPTION:'):
                    description = line.replace('DESCRIPTION:', '').strip()
                elif line.startswith('INSIGHTS:'):
                    in_insights = True
                elif in_insights and line.startswith('-'):
                    insights.append(line[1:].strip())
            
            return description or "Table data", insights
        
        except Exception as e:
            print(f"Error analyzing table: {e}")
            return "Table data", []
