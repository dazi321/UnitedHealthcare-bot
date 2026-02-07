import streamlit as st
import anthropic
import os
from pathlib import Path
import base64
import tempfile
import pandas as pd

# Page config
st.set_page_config(
    page_title="Guardian Insurance Claims Checker",
    page_icon="📋",
    layout="wide"
)

st.title("📋 Guardian Insurance Claims Verification")
st.markdown("Upload PDFs and Excel files to verify data matches")

# API key - check secrets first, then allow manual entry
try:
    api_key = st.secrets["ANTHROPIC_API_KEY"]
    st.success("✅ API key loaded from secure storage")
except:
    api_key = st.text_input("Enter your Claude API key:", type="password", help="Get your API key from console.anthropic.com")
    if not api_key:
        st.warning("Please enter your Claude API key to continue")
        st.info("💡 **Tip for admin:** Store the API key in Streamlit secrets (Settings → Secrets) so users don't need to enter it each time.")
        st.stop()

# File upload section
st.header("Upload Files")

col1, col2 = st.columns(2)

with col1:
    st.subheader("📄 PDF Files")
    pdf_files = st.file_uploader(
        "Upload PDF invoices/claims",
        type=['pdf'],
        accept_multiple_files=True,
        key="pdf"
    )

with col2:
    st.subheader("📊 Excel Files")
    excel_files = st.file_uploader(
        "Upload corresponding Excel files",
        type=['xlsx', 'xls', 'csv'],
        accept_multiple_files=True,
        key="excel"
    )

# Show file counts
if pdf_files or excel_files:
    st.info(f"Uploaded: {len(pdf_files) if pdf_files else 0} PDFs, {len(excel_files) if excel_files else 0} Excel files")

# Process button
if st.button("🔍 Check for Discrepancies", type="primary", disabled=not (pdf_files and excel_files)):
    
    # Match files by name
    def get_base_name(filename):
        """Extract base name for matching (removes extension and common suffixes)"""
        name = Path(filename).stem  # Remove extension
        # Remove common suffixes like _invoice, _claim, etc
        for suffix in ['_invoice', '_claim', '_statement', ' invoice', ' claim', ' statement']:
            name = name.replace(suffix, '')
        return name.strip().lower()
    
    # Create dictionaries for matching
    pdf_dict = {get_base_name(f.name): f for f in pdf_files}
    excel_dict = {get_base_name(f.name): f for f in excel_files}
    
    # Find matching pairs
    matched_pairs = []
    unmatched_pdfs = []
    unmatched_excels = []
    
    for name, pdf in pdf_dict.items():
        if name in excel_dict:
            matched_pairs.append((pdf, excel_dict[name]))
        else:
            unmatched_pdfs.append(pdf.name)
    
    for name, excel in excel_dict.items():
        if name not in pdf_dict:
            unmatched_excels.append(excel.name)
    
    # Show matching summary
    st.info(f"✅ Found {len(matched_pairs)} matching pairs")
    
    if unmatched_pdfs or unmatched_excels:
        st.warning("⚠️ Some files couldn't be matched:")
        if unmatched_pdfs:
            st.write("**Unmatched PDFs:**", ", ".join(unmatched_pdfs))
        if unmatched_excels:
            st.write("**Unmatched Excel files:**", ", ".join(unmatched_excels))
        
        if not st.checkbox("Continue with matched pairs only"):
            st.stop()
    
    if len(matched_pairs) == 0:
        st.error("No matching pairs found. Make sure PDF and Excel files have similar names.")
        st.info("Example: 'claim_001.pdf' matches with 'claim_001.xlsx'")
        st.stop()
    
    # Initialize Claude client
    client = anthropic.Anthropic(api_key=api_key)
    
    # Progress tracking
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    results = []
    total_pairs = len(matched_pairs)
    
    # Process each pair
    for idx, (pdf_file, excel_file) in enumerate(matched_pairs):
        status_text.text(f"Processing {idx + 1} of {total_pairs}: {pdf_file.name}")
        
        try:
            # Read PDF as base64
            pdf_content = pdf_file.read()
            pdf_base64 = base64.b64encode(pdf_content).decode('utf-8')
            
            # Read Excel/CSV file as text
            excel_file.seek(0)  # Reset file pointer
            if excel_file.name.endswith('.csv'):
                # Read CSV directly as text
                excel_text = excel_file.read().decode('utf-8', errors='ignore')
            else:
                # For Excel files, convert to readable format
                df = pd.read_excel(excel_file)
                excel_text = df.to_string()
            
            # Create message to Claude
            message = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=2000,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "document",
                            "source": {
                                "type": "base64",
                                "media_type": "application/pdf",
                                "data": pdf_base64
                            }
                        },
                        {
                            "type": "text",
                            "text": f"""Here is the Excel/CSV data:

{excel_text}

---

**IMPORTANT: READ ALL PAGES OF THE PDF**
The PDF has multiple pages. Employee details are usually on pages 5-9, not just the first page. Make sure you read the ENTIRE document.

**HOW TO CHECK EACH ITEM:**

1. **Policy Number**: Simply check if the policy number matches in both documents.

2. **Names**: 
   - List ALL names from the PDF (check ALL pages, especially pages 5-9)
   - Count them
   - List ALL names from the CSV (count only rows where Relationship = "Employee")
   - Count them
   - If the counts match AND the names match, say "MATCH"
   - Only flag as discrepancy if: (a) counts are different, OR (b) specific names are missing from one document

3. **Coverage Periods**:
   - If coverage periods are NOT shown in the PDF, say "No coverage periods shown in PDF"
   - If they ARE shown, compare each employee's period between documents
   - Only flag discrepancies for employees whose periods don't match

4. **Total Amounts**:
   - In the PDF, find the "Total Current Premium" (usually on page 9 or 10)
   - In the CSV, add up all employee premiums (only count rows where Relationship = "Employee")
   - Compare these two totals
   - If they match (within $1 due to rounding), say "MATCH"
   - If different, state both amounts

5. **Employee Count**:
   - Count employees in PDF
   - Count employees in CSV (only rows where Relationship = "Employee")
   - If the numbers are THE SAME, say "MATCH - Both have X employees"
   - Only flag as discrepancy if the numbers are DIFFERENT

6. **Premium Per Employee**:
   - In the PDF, each employee has a "Total Premium" column (far right)
   - In the CSV, each employee has a total premium
   - Compare these for each employee
   - If they all match, say "MATCH"
   - Only list employees whose premiums DON'T match

**CRITICAL COMPARISON RULES:**
- If two numbers are the SAME, that's a MATCH - don't flag it as a discrepancy
- Only flag discrepancies when things are actually DIFFERENT
- Don't assume there's a problem just because you see a lot of data
- Be confident: if you counted 64 employees in both documents, that's a MATCH

**INCLUDE HANDWRITTEN NOTES**: If there are pen marks or handwritten numbers on the PDF, include those in your analysis.

Provide your response EXACTLY in this format:

**Status:** [MATCH or DISCREPANCY FOUND]

**Results:**
1. Policy Number: [MATCH or state the discrepancy]
2. Names: [MATCH or list specific names that are missing]
3. Coverage Periods: [MATCH or "No coverage periods shown in PDF" or list employees with different periods]
4. Total Amounts: [MATCH or state both amounts - "PDF: $X, CSV: $Y"]
5. Employee Count: [MATCH - Both have X employees OR state the discrepancy "PDF has X, CSV has Y"]
6. Premium Per Employee: [MATCH or list specific employees with different premiums]

**Summary:** [One sentence: either "All fields match" or "X discrepancies found in: [list which fields]"]"""
                        }
                    ]
                }]
            )
            
            # Extract response
            response_text = message.content[0].text
            
            results.append({
                "pdf": pdf_file.name,
                "excel": excel_file.name,
                "result": response_text
            })
            
        except Exception as e:
            results.append({
                "pdf": pdf_file.name,
                "excel": excel_file.name,
                "result": f"❌ Error processing: {str(e)}"
            })
        
        # Update progress
        progress_bar.progress((idx + 1) / total_pairs)
    
    # Display results
    status_text.text("✅ Processing complete!")
    st.success(f"Processed {total_pairs} claim pairs")
    
    st.header("Results")
    
    # Count discrepancies
    discrepancy_count = sum(1 for r in results if "DISCREPANCY" in r["result"])
    match_count = total_pairs - discrepancy_count
    
    col1, col2 = st.columns(2)
    with col1:
        st.metric("✅ Matches", match_count)
    with col2:
        st.metric("⚠️ Discrepancies", discrepancy_count)
    
    # Show each result
    for idx, result in enumerate(results, 1):
        with st.expander(f"Claim #{idx}: {result['pdf']} ↔ {result['excel']}", expanded="DISCREPANCY" in result["result"]):
            st.markdown(result["result"])
    
    # Download results option
    results_text = "\n\n" + "="*80 + "\n\n".join([
        f"CLAIM #{idx}\nPDF: {r['pdf']}\nExcel: {r['excel']}\n\n{r['result']}"
        for idx, r in enumerate(results, 1)
    ])
    
    st.download_button(
        label="📥 Download Full Report",
        data=results_text,
        file_name="claims_verification_report.txt",
        mime="text/plain"
    )

# Instructions
with st.sidebar:
    st.header("ℹ️ How to Use")
    st.markdown("""
    1. Enter your Claude API key
    2. Upload all PDF files (any order)
    3. Upload all matching Excel files (any order)
    4. Click "Check for Discrepancies"
    5. Review results and download report
    
    **File Matching:**
    Files are automatically matched by name. 
    
    ✅ These will match:
    - `claim_001.pdf` ↔ `claim_001.xlsx`
    - `invoice_123.pdf` ↔ `invoice_123.csv`
    - `policy 456.pdf` ↔ `policy 456.xlsx`
    
    **Supported Formats:**
    - PDFs: .pdf (including scanned)
    - Excel: .xlsx, .xls, .csv
    """)
    
    st.header("💡 Tips")
    st.markdown("""
    - Upload order doesn't matter
    - Name your files consistently for easy matching
    - You can upload all files at once
    - Unmatched files will be shown before processing
    """)
