# Insurance Claims Checker

A simple Streamlit app to verify insurance claim data between PDF invoices and Excel spreadsheets.

## Features

- Upload multiple PDF and Excel file pairs
- Automatically compare data fields (policy numbers, names, addresses, dates, amounts)
- Flag discrepancies clearly
- Download comprehensive report
- Handles scanned PDFs and handwritten notes

## Quick Start (Local Testing)

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Run the app:
```bash
streamlit run claims_checker.py
```

3. Open your browser to `http://localhost:8501`

## Deployment to Streamlit Cloud (FREE)

### Step 1: Prepare Your Code

1. Create a GitHub account if you don't have one
2. Create a new repository (e.g., "insurance-claims-checker")
3. Upload these files:
   - `claims_checker.py`
   - `requirements.txt`
   - `README.md`

### Step 2: Deploy to Streamlit Cloud

1. Go to https://share.streamlit.io/
2. Click "New app"
3. Connect your GitHub repository
4. Select your repository and main file (`claims_checker.py`)
5. Click "Deploy"

Your app will be live at: `https://[your-app-name].streamlit.app`

### Step 3: Add API Key (Secure Method)

Instead of entering the API key each time, you can store it securely:

1. In Streamlit Cloud dashboard, go to your app settings
2. Click "Secrets"
3. Add:
```toml
ANTHROPIC_API_KEY = "your-api-key-here"
```

4. Update the code to use secrets (optional):
```python
# Replace the text_input line with:
api_key = st.secrets.get("ANTHROPIC_API_KEY", "")
if not api_key:
    api_key = st.text_input("Enter your Claude API key:", type="password")
```

## Usage

1. **Get a Claude API Key**
   - Go to https://console.anthropic.com/
   - Create an API key
   - Copy it

2. **Upload Files**
   - Upload all PDFs in the left column
   - Upload matching Excel files in the right column
   - **Important:** Upload files in matching order

3. **Process**
   - Click "Check for Discrepancies"
   - Wait for processing (5-10 minutes for 130 pairs)
   - Review results

4. **Download Report**
   - Click "Download Full Report" to get a text file with all results

## File Pairing

Files are automatically matched by name:
- `claim_001.pdf` ↔ `claim_001.xlsx`
- `invoice_123.pdf` ↔ `invoice_123.csv`
- `policy 456.pdf` ↔ `policy 456.xlsx`

**Upload order doesn't matter!** You can:
- Select all 130 PDFs at once
- Select all 130 Excel files at once
- The app will automatically pair them by matching names

**Naming tips:**
- Use consistent prefixes (claim_, invoice_, policy_)
- Use numbers or IDs in filenames
- Avoid special characters

## Cost Estimate

- **Streamlit Cloud:** Free tier (sufficient for this use case)
- **Claude API:** ~$0.25-0.50 per claim pair = $30-65 per month for 130 claims
- **Total:** ~$30-65/month

## Troubleshooting

**"Mismatch" error:** You uploaded different numbers of PDFs and Excel files. Make sure you upload the same count of each.

**Slow processing:** Processing 130 pairs takes about 5-10 minutes. This is normal.

**API errors:** Check that your API key is correct and has sufficient credits.

## Future Improvements

- Auto-pair files by name matching
- Better error handling for corrupt files
- Export to Excel instead of text
- Email notifications when processing completes
- Support for batch scheduling

## Support

For issues or questions, contact [your contact info]
