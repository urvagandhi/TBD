# Agent Paperpal — MS Word Add-in

A taskpane sidebar that runs inside Microsoft Word. Format your manuscript to any journal style without leaving Word.

## Quick Start

```bash
cd word-addin
npm install
npm run dev        # Starts HTTPS dev server on https://localhost:3001
```

Make sure the backend is running on `http://localhost:8000`.

## Sideloading the Add-in

### Word Online (Easiest — recommended for demo)
1. Go to https://www.office.com/launch/word and open any document
2. Click **Insert** > **Office Add-ins** > **Upload My Add-in**
3. Browse to `word-addin/manifest.xml` and upload
4. The "Agent Paperpal" taskpane opens in the sidebar

### Windows Desktop
1. Open File Explorer and go to `\\%USERPROFILE%\AppData\Local\Microsoft\Office\16.0\Wef\`
2. Copy `manifest.xml` into that folder
3. Restart Word — find "Agent Paperpal" under **Insert > My Add-ins**

### Mac Desktop
1. Copy `manifest.xml` to `~/Library/Containers/com.microsoft.Word/Data/Documents/wef/`
2. Restart Word — find it under **Insert > My Add-ins**

## HTTPS Certificate

Office Add-ins require HTTPS. Self-signed certs are auto-generated in `certs/`.
If your browser blocks them, visit `https://localhost:3001` directly and accept the certificate.

## How It Works

1. User opens Word document and clicks "Format Paper" in the sidebar
2. Add-in reads the document via Office.js API
3. Sends it to the FastAPI backend (`POST /upload` → `POST /format`)
4. Polls for progress and shows real-time updates
5. Displays compliance score and section breakdown
6. User can "Apply to Document" (replaces content in-place) or "Download DOCX"
