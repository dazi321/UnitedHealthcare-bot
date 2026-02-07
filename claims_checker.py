import streamlit as st
import anthropic
import os
from pathlib import Path
import base64
import tempfile
import pandas as pd

# Page config
st.set_page_config(
    page_title="UHC Claims Checker",
    page_icon="📋",
    layout="wide"
)

st.title("📋 United Healthcare Claims Verification")
st.markdown("Upload PDFs and CSV files to verify data matches")

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
    st.subheader("📊 CSV Files")
    csv_files = st.file_uploader(
        "Upload corresponding CSV files",
        type=['csv'],
        accept_multiple_files=True,
        key="csv"
    )

# Show file counts
if pdf_files or csv_files:
    st.info(f"Uploaded: {len(pdf_files) if pdf_files else 0} PDFs, {len(csv_files) if csv_files else 0} CSV files")

# Process button
if st.button("🔍 Check for Discrepancies", type="primary", disabled=not (pdf_files and csv_files)):
    
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
    csv_dict = {get_base_name(f.name): f for f in csv_files}
    
    # Find matching pairs
    matched_pairs = []
    unmatched_pdfs = []
    unmatched_csvs = []
    
    for name, pdf in pdf_dict.items():
        if name in csv_dict:
            matched_pairs.append((pdf, csv_dict[name]))
        else:
            unmatched_pdfs.append(pdf.name)
    
    for name, csv in csv_dict.items():
        if name not in pdf_dict:
            unmatched_csvs.append(csv.name)
    
    # Show matching summary
    st.info(f"✅ Found {len(matched_pairs)} matching pairs")
    
    if unmatched_pdfs or unmatched_csvs:
        st.warning("⚠️ Some files couldn't be matched:")
        if unmatched_pdfs:
            st.write("**Unmatched PDFs:**", ", ".join(unmatched_pdfs))
        if unmatched_csvs:
            st.write("**Unmatched CSV files:**", ", ".join(unmatched_csvs))
        
        if not st.checkbox("Continue with matched pairs only"):
            st.stop()
    
    if len(matched_pairs) == 0:
        st.error("No matching pairs found. Make sure PDF and CSV files have similar names.")
        st.info("Example: 'claim_001.pdf' matches with 'claim_001.csv'")
        st.stop()
    
    # Initialize Claude client
    client = anthropic.Anthropic(api_key=api_key)
    
    # Progress tracking
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    results = []
    total_pairs = len(matched_pairs)
    
    # Process each pair
    for idx, (pdf_file, csv_file) in enumerate(matched_pairs):
        status_text.text(f"Processing {idx + 1} of {total_pairs}: {pdf_file.name}")
        
        try:
            # Read PDF as base64
            pdf_content = pdf_file.read()
            pdf_base64 = base64.b64encode(pdf_content).decode('utf-8')
            
            # Read CSV file as text
            csv_file.seek(0)  # Reset file pointer
            csv_text = csv_file.read().decode('utf-8', errors='ignore')
            
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
                            "text": f"""Here is the CSV data:

{csv_text}

---

**UNDERSTANDING UNITED HEALTHCARE PDF STRUCTURE**
This is a United Healthcare invoice with a specific structure:
- Page 1: Cover page with invoice number and account info
- Pages 2-3: SUMMARY showing totals by plan type (medical, dental, vision, life insurance)
- Pages 4-6-7: DETAILED EMPLOYEE LISTINGS with individual names and charges

**CRITICAL: YOU MUST READ PAGES 4-6-7 FOR EMPLOYEE DETAILS**
The summary pages (2-3) only show plan categories. Employee names and individual charges are on pages 4-6-7.

**UNDERSTANDING THE CSV STRUCTURE**
The CSV lists EVERY person (employees, spouses, children) with their coverage:
- Each row shows: Relationship, First Name, Last Name, Coverage Level, Cost
- For family coverage, the SAME cost appears multiple times (once per family member)
- Example: Employee + Family at $1,170.56 will show this cost 5 times (employee + spouse + 3 kids)
- **ONLY count rows where Relationship = "Employee" when counting employees**
- **ONLY count UNIQUE medical plan costs when calculating totals (don't add duplicate family costs)**

**HOW TO CHECK EACH ITEM:**

1. **Invoice Number**: 
   - Find the invoice number on page 1 of the PDF
   - State what it is (there's no invoice number in CSV to compare)

2. **Names**: 
   - Go to pages 4-6-7 of the PDF and list ALL employee names you see
   - Count them
   - From CSV, list all unique names where Relationship = "Employee"
   - Count them
   - Compare: if counts match AND names match, say "MATCH"
   - If different, list which names are missing from either document

3. **Coverage Period**:
   - Find coverage period on PDF (usually page 1 or 2)
   - There is no coverage period in CSV to compare
   - Just state what the PDF shows

4. **Total Amount**:
   - PDF: Find the "TOTAL" or "Total Balance Due" on page 2 or 3
   - CSV: Calculate total by counting UNIQUE medical plan coverages only
     * For each unique employee, count their medical plan cost ONCE (not for each family member)
     * Example: If "Jason Bull" has "Employee + Family" at $1,170.56, count $1,170.56 ONCE even though it appears 4 times in CSV
   - Compare these totals
   - If they match (within $1), say "MATCH"
   - If different, state both amounts

5. **Employee Count**:
   - PDF: On page 3, look for "TOTAL" with a number next to it - this is the EMPLOYEE count
   - CSV: Count rows where Relationship = "Employee"
   - If the numbers match, say "MATCH - Both have X employees"
   - If different, state both counts

6. **Premium Per Employee**:
   - PDF: On pages 4-6-7, each employee has individual charges listed
   - CSV: Each employee row shows their medical plan cost
   - Compare a few examples to verify they match
   - If they match, say "MATCH"
   - If any don't match, list those employees with the discrepancy

**CRITICAL RULES:**
- READ PAGES 4-6-7 for employee names and details - don't rely only on summary pages
- When counting employees, ONLY count "Employee" rows, not spouses/children
- When calculating CSV total, ONLY count each unique employee's medical cost ONCE
- The number "29" on page 3 is the EMPLOYEE count, not total covered people
- If two numbers are the SAME, say "MATCH" - don't flag it as a discrepancy

Provide your response EXACTLY in this format:

**Status:** [MATCH or DISCREPANCY FOUND]

**Results:**
1. Invoice Number: [State the invoice number from PDF]
2. Names: [MATCH or list specific names that are missing]
3. Coverage Period: [State the coverage period from PDF]
4. Total Amount: [MATCH or state both amounts - "PDF: $X, CSV: $Y"]
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
                "csv": csv_file.name,
                "result": response_text
            })
            
        except Exception as e:
            results.append({
                "pdf": pdf_file.name,
                "csv": csv_file.name,
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
        with st.expander(f"Claim #{idx}: {result['pdf']} ↔ {result['csv']}", expanded="DISCREPANCY" in result["result"]):
            st.markdown(result["result"])
    
    # Download results option
    results_text = "\n\n" + "="*80 + "\n\n".join([
        f"CLAIM #{idx}\nPDF: {r['pdf']}\nCSV: {r['csv']}\n\n{r['result']}"
        for idx, r in enumerate(results, 1)
    ])
    
    st.download_button(
        label="📥 Download Full Report",
        data=results_text,
        file_name="uhc_claims_verification_report.txt",
        mime="text/plain"
    )

# Instructions
with st.sidebar:
    st.header("ℹ️ How to Use")
    st.markdown("""
    1. Enter your Claude API key
    2. Upload all PDF files (any order)
    3. Upload all matching CSV files (any order)
    4. Click "Check for Discrepancies"
    5. Review results and download report
    
    **File Matching:**
    Files are automatically matched by name. 
    
    ✅ These will match:
    - `claim_001.pdf` ↔ `claim_001.csv`
    - `invoice_123.pdf` ↔ `invoice_123.csv`
    - `uhc_456.pdf` ↔ `uhc_456.csv`
    
    **Supported Formats:**
    - PDFs: .pdf (including scanned)
    - CSV: .csv files only
    """)
    
    st.header("💡 Tips")
    st.markdown("""
    - Upload order doesn't matter
    - Name your files consistently for easy matching
    - You can upload all files at once
    - Unmatched files will be shown before processing
    """)
    
    st.header("🏥 UHC Format Notes")
    st.markdown("""
    This tool is specifically designed for United Healthcare invoices:
    - Summary pages show plan totals
    - Detail pages list individual employees
    - CSV includes all family members
    """)
