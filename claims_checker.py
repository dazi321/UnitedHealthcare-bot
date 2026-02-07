import streamlit as st
import anthropic
import os
from pathlib import Path
import base64
import tempfile
import pandas as pd

# Page config
st.set_page_config(
    page_title="Insurance Claims Checker",
    page_icon="📋",
    layout="wide"
)

st.title("📋 Insurance Claims Verification")
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

**CRITICAL: READ THE ENTIRE PDF CAREFULLY**
- This PDF likely has multiple pages - read ALL of them
- Employee names are typically listed in detailed tables on later pages, not just the summary page
- Look through the ENTIRE document to find ALL employee names and data
- The first page is usually just a summary/cover page

**CRITICAL: UNDERSTANDING THE PDF TABLE STRUCTURE**
- PDFs often have numbers stacked vertically in columns
- ALWAYS look at the COLUMN HEADER to understand what the numbers mean
- Common patterns:
  * "Premium/Volume" column: TOP number = Premium, BOTTOM number = Volume
  * "Premium/Weekly Benefit Volume": TOP number = Premium, BOTTOM number = Weekly Benefit
  * "Premium/Covered Payroll Volume": TOP number = Premium, BOTTOM number = Covered Payroll
- **NEVER add these stacked numbers together** - they represent different things
- When comparing premiums, ONLY use the premium number (usually the top one)
- Look for a "Total Premium" column - this is the final premium total for that employee

**CRITICAL: EMPLOYEE COUNTING (Only applies to #5 Employee Count check)**
- The CSV has a "Relationship" column that shows "Employee", "Spouse", "Child", etc.
- When COUNTING employees (#5), only count rows where Relationship = "Employee"
- DO NOT count "Spouse", "Child", or other dependent rows when counting employees
- However, when COMPARING NAMES (#2), you should still verify that ALL names match (including spouses and dependents if listed in the PDF)

**IMPORTANT INSTRUCTIONS:**
- INCLUDE handwritten pen marks in your analysis - they may contain adjustments or corrections to amounts
- **Understanding Premium Calculations:**
  - When comparing premiums between PDF and CSV, look at the TOTAL PREMIUM for each employee
  - If the PDF has multiple coverage columns (Dental, Vision, Voluntary, etc.), the Total Premium column shows the sum
  - Don't add "Premium" + "Volume" numbers from the same column - they're different data types
  - If there are handwritten additions, add those to the totals
- Only flag as DISCREPANCY if the final PREMIUM numbers don't match, NOT if they're just presented differently

Compare the PDF invoice with the Excel/CSV data above. Check ONLY these 7 things:

1. **Policy Number** - Does the policy number match in both documents?
2. **Names** - Compare ALL names from BOTH documents (including employees and any dependents listed). List any names that don't match or are missing from one document vs the other. MAKE SURE TO CHECK ALL PAGES OF THE PDF.
3. **Coverage Periods** - Does the coverage period match? If any employee has a different coverage period, list their name
4. **Total Amounts** - Does the total invoice premium match? Do individual employee TOTAL PREMIUMS match? List names where premiums don't match. Remember: compare TOTAL PREMIUM, not individual coverage components.
5. **Employee Count** - Count the number of PRIMARY EMPLOYEES (not dependents). In the PDF, count unique employee names. In the CSV, only count rows where Relationship = "Employee". Does the count match?
6. **Premium Per Employee** - Does each employee's TOTAL PREMIUM match between documents? Look at the "Total Premium" column in the PDF. Include any handwritten adjustments. List names where the TOTAL doesn't match.
7. **Plan Tiers** - Does each employee's plan tier match (e.g., "Employee", "Employee + Family", "Employee + Spouse", "Employee + Children")? List names where the tier doesn't match.

Provide your response EXACTLY in this format:

**Status:** [MATCH or DISCREPANCY FOUND]

**Results:**
1. Policy Number: [MATCH or state the discrepancy]
2. Names: [MATCH or list names that don't match/are missing]
3. Coverage Periods: [MATCH or list employee names with different periods]
4. Total Amounts: [MATCH or state discrepancy and list affected employee names]
5. Employee Count: [MATCH or state the discrepancy]
6. Premium Per Employee: [MATCH or list employee names with mismatched premiums]
7. Plan Tiers: [MATCH or list employee names with mismatched plan tiers]

**Summary:** [One sentence: either "All fields match" or "X discrepancies found"]"""
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
