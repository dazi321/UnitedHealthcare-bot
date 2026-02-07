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

**IMPORTANT: READ ALL PAGES OF THE PDF**
This is a United Healthcare invoice with multiple pages:
- Page 1: Cover page
- Pages 2-3: Summary totals
- Pages 4+: DETAILED EMPLOYEE LISTINGS (read ALL remaining pages - there may be many pages of employee details)

Make sure you read the ENTIRE document to find ALL employee names.

**UNDERSTANDING THE CSV STRUCTURE - VERY IMPORTANT**
The CSV lists EVERY person (employees + spouses + children):
- For family coverage, the SAME cost appears multiple times
- Example: "Jason Bull" with "Employee + Family" at $1,170.56 will show:
  - Row 1: Jason Bull (Employee) - $1,170.56
  - Row 2: Jenni Fromm (Spouse) - $1,170.56
  - Row 3: Luca Bull (Child) - $1,170.56
  - Row 4: Maisi Bull (Child) - $1,170.56
  - This is ONE employee with ONE cost of $1,170.56, NOT four separate costs!

**HOW TO CHECK EACH ITEM:**

1. **Invoice Number**: 
   - Find the invoice number on page 1 of the PDF
   - State what it is

2. **Names**: 
   - Read ALL pages starting from page 4 onwards to list ALL employee names from the PDF
   - Count them (should match the "TOTAL" number on page 3)
   - From CSV, list all unique first+last names where Relationship = "Employee"
   - Count them
   - If the counts match AND the names match, say "MATCH"
   - Only flag as discrepancy if: (a) counts are different, OR (b) specific names are missing from one document

3. **Coverage Period**:
   - Find the coverage period on page 1 or 2 of the PDF
   - State what it shows
   - Say "No coverage period in CSV to compare"

4. **Total Amounts**:
   - PDF: Look at page 3 for the "Subtotal" amount (this is the current month's charges BEFORE adjustments)
   - **Note:** There may also be "Current Adjustments" showing retroactive charges - these are separate
   - Example from page 3:
     * Subtotal (current charges): $15,606.16
     * Current Adjustments: $765.20
     * Total Balance Due: $16,371.36
   - CSV: Calculate total by counting each UNIQUE employee's medical cost ONCE:
     * Go through CSV and for each unique employee (where Relationship = "Employee"), take their Medical Plan Cost
     * Add them up ONCE per employee (don't add the spouse/child duplicate costs)
     * Example: Jason Bull's family shows $1,170.56 four times → count it ONCE as $1,170.56
   - **Compare the PDF Subtotal (current charges) with the CSV total**
   - If they match (within $1 due to rounding), say "MATCH"
   - If different, state both amounts: "PDF Current Charges: $X, CSV: $Y"
   - **If there are adjustments:** Add a note: "PDF also shows $Z in retroactive adjustments (see Premium Per Employee for details)"

5. **Employee Count**:
   - PDF: Look at page 3 for the "TOTAL" number next to employee count
   - CSV: Count how many rows have Relationship = "Employee"
   - If the numbers are THE SAME, say "MATCH - Both have X employees"
   - Only flag as discrepancy if the numbers are DIFFERENT

6. **Premium Per Employee**:
   - PDF: Read pages 4+ to see individual employee charges - look at the "Totals" column (far right)
   - **CRITICAL: Check the "Adjustment Detail" column** for retroactive charges
   - Some employees may have adjustment codes like "ADD" (retroactive addition), "CHG" (change), or "TRM" (termination)
   - These adjustments are for previous months being charged now
   - Example: "Covian, Elias" might show:
     * Current charge (Feb): $382.60
     * Adjustment for Dec: $382.60 (ADD code)
     * Adjustment for Jan: $382.60 (ADD code)  
     * **Total: $1,147.80** (not $382.60!)
   - CSV: Each employee row (Relationship = "Employee") shows their Medical Plan Cost (usually just base monthly amount)
   - **Compare each employee's PDF TOTAL (including adjustments) with their CSV cost**
   - If they match, say "MATCH"
   - **FLAG AS DISCREPANCY:** List any employee whose PDF total doesn't match CSV cost
   - Format: "Employee Name: PDF $X (includes $Y adjustments), CSV $Z"

**CRITICAL COMPARISON RULES:**
- If two numbers are the SAME, that's a MATCH - don't flag it as a discrepancy
- Only flag discrepancies when things are actually DIFFERENT
- When calculating CSV total, only count each employee's cost ONCE (not their family members' duplicate costs)
- **IMPORTANT:** Always check the "Adjustment Detail" column in the PDF for retroactive charges
- An employee with adjustments will have a HIGHER PDF total than their CSV cost - this IS a discrepancy
- Be confident: if you counted 27 employees in both documents, that's a MATCH
- Don't assume there's a problem just because you see a lot of data

Provide your response EXACTLY in this format:

**Status:** [MATCH or DISCREPANCY FOUND]

**Results:**
1. Invoice Number: [State the invoice number from PDF]
2. Names: [MATCH or list specific names that are missing - be specific about which document is missing which names]
3. Coverage Period: [State coverage period from PDF, then say "No coverage period in CSV to compare"]
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
