import pymupdf4llm
import pathlib

# Input and output paths
pdf_path = r"c:\Users\Warren\Documents\BubbleViews\MVP Reddit AI Agent – Technical Specification.pdf"
output_path = r"c:\Users\Warren\Documents\BubbleViews\MVP_Reddit_AI_Agent_Technical_Specification.md"

# Convert PDF to Markdown
md_text = pymupdf4llm.to_markdown(pdf_path)

# Write to file
with open(output_path, 'w', encoding='utf-8') as f:
    f.write(md_text)

print(f"Successfully converted PDF to Markdown!")
print(f"Output file: {output_path}")
