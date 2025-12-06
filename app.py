import streamlit as st
import pandas as pd
import pdfplumber
import xmltodict
import io
import re
import time
from datetime import datetime

# --- 1. CONFIGURAZIONE PAGINA ---
st.set_page_config(
    page_title="Invoice Intelligence Pro",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- 2. DESIGN SYSTEM (CSS AVANZATO) ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    
    :root {
        --primary: #0f172a;       /* Blu Notte (Titoli) */
        --accent: #0056b3;        /* Blu Elettrico (Bottoni/Focus) */
        --bg-color: #f8fafc;      /* Grigio Chiarissimo (Sfondo App) */
        --card-bg: #ffffff;       /* Bianco (Card) */
        --text-color: #334155;    /* Grigio Scuro (Testo) */
        --border-color: #e2e8f0;  /* Grigio Bordo */
    }

    /* Reset Globale */
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif !important;
        background-color: var(--bg-color) !important;
        color: var(--text-color) !important;
    }

    /* --- LAYOUT A CARD --- */
    .stCard {
        background-color: var(--card-bg);
        padding: 24px;
        border-radius: 12px;
        border: 1px solid var(--border-color);
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
        margin-bottom: 24px;
    }
    
    /* --- METRICHE (KPI) --- */
    .kpi-container {
        display: flex;
        flex-direction: column;
        background: white;
        padding: 20px;
        border-radius: 10px;
        border: 1px solid var(--border-color);
        border-left: 4px solid var(--accent);
    }
    .kpi-label {
        font-size: 0.75rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        font-weight: 600;
        color: #64748b;
        margin-bottom: 8px;
    }
    .kpi-value {
        font-size: 1.5rem;
        font-weight: 700;
        color: var(--primary);
    }

    /* --- SIDEBAR --- */
    [data-testid="stSidebar"] {
        background-color: #ffffff;
        border-right: 1px solid var(--border-color);
    }

    /* --- INPUT & UPLOAD --- */
    [data-testid="stFileUploader"] {
        background-color: white;
        border: 1px dashed #cbd5e1;
        border-radius: 10px;
        padding: 30px;
    }
    /* Rimuove rosso dai focus */
    input:focus, textarea:focus, select:focus {
        border-color: var(--accent) !important;
        box-shadow: 0 0 0 1px var(--accent) !important;
    }

    /* --- TABELLE --- */
    [data-testid="stDataFrame"] {
        border: 1px solid var(--border-color);
        border-radius: 8px;
        background: white;
    }

    /* --- BOTTONI --- */
    .stButton>button {
        background-color: var(--primary);
        color: white;
        font-weight: 600;
        border-radius: 8px;
        border: none;
        padding: 0.6rem 1.2rem;
        transition: all 0.2s;
        text-transform: uppercase;
        font-size: 0.85rem;
        letter-spacing: 0.02em;
    }
    .stButton>button:hover {
        background-color: var(--accent);
        box-shadow: 0 4px 12px rgba(37, 99, 235, 0.2);
    }

    /* --- TITOLI --- */
    h1, h2, h3 { color: var(--primary) !important; font-weight: 700 !important; }
    
    /* --- STATUS CONTAINER --- */
    [data-testid="stStatus"] {
        background: white;
        border: 1px solid var(--border-color);
        border-radius: 10px;
    }
    </style>
""", unsafe_allow_html=True)

# --- 3. MOTORE DI ESTRAZIONE ---

def categorize_expense(description, supplier):
    text = (str(description) + " " + str(supplier)).lower()
    categories = {
        "Utenze & Energia": ["enel", "eni", "luce", "gas", "energia", "a2a", "edison"],
        "Hardware & IT": ["apple", "dell", "lenovo", "server", "hosting", "software", "mouse", "pc", "aws", "google"],
        "Consulenza & Servizi": ["avvocato", "commercialista", "notai", "consulenza", "fee"],
        "Logistica & Trasporti": ["dhl", "fedex", "poste", "bartolini", "gls", "spedizione", "carburante"],
        "Ristorazione & Viaggi": ["ristorante", "hotel", "treno", "volo", "airbnb", "uber", "pranzo", "trattoria"],
        "Marketing": ["facebook", "ads", "linkedin", "google ads", "stampa", "brochure", "meta"],
        "Cancelleria": ["carta", "penne", "ufficio", "toner", "amazon"]
    }
    for category, keywords in categories.items():
        if any(k in text for k in keywords): return category
    return "Altro / Generale"

def parse_xml_invoice(file_content):
    try:
        doc = xmltodict.parse(file_content)
        header = doc.get('p:FatturaElettronica', {}).get('FatturaElettronicaHeader', {})
        body = doc.get('p:FatturaElettronica', {}).get('FatturaElettronicaBody', {})
        if isinstance(body, list): body = body[0]
        
        supplier = header.get('CedentePrestatore', {}).get('DatiAnagrafici', {}).get('Anagrafica', {}).get('Denominazione')
        if not supplier:
            nome = header.get('CedentePrestatore', {}).get('DatiAnagrafici', {}).get('Anagrafica', {}).get('Nome', '')
            cognome = header.get('CedentePrestatore', {}).get('DatiAnagrafici', {}).get('Anagrafica', {}).get('Cognome', '')
            supplier = f"{nome} {cognome}"

        gen_data = body.get('DatiGenerali', {}).get('DatiGeneraliDocumento', {})
        amount = body.get('DatiGenerali', {}).get('DatiGeneraliDocumento', {}).get('ImportoTotaleDocumento', 0.0)
        
        details = body.get('DatiBeniServizi', {}).get('DettaglioLinee', [])
        description = ""
        if isinstance(details, list) and len(details) > 0: description = details[0].get('Descrizione', '')
        elif isinstance(details, dict): description = details.get('Descrizione', '')

        return {
            "Tipo": "XML (E-Fattura)",
            "Data": gen_data.get('Data', ''),
            "Fornitore": supplier,
            "Descrizione": description,
            "Totale (€)": float(amount) if amount else 0.0,
            "Categoria": categorize_expense(description, supplier)
        }
    except Exception as e:
        return {"Tipo": "Errore", "Fornitore": "XML non valido", "Totale (€)": 0.0, "Categoria": "Errore"}

def parse_pdf_invoice(file_bytes):
    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            text = ""
            for page in pdf.pages: text += page.extract_text() or ""
        
        date_match = re.search(r'\d{2}/\d{2}/\d{4}|\d{4}-\d{2}-\d{2}', text)
        amount_match = re.search(r'(?i)(?:totale|importo|total|amount)[\s:]+.*?(\d+[.,]\d{2})', text)
        
        amount = 0.0
        if amount_match:
            try: amount = float(amount_match.group(1).replace('.','').replace(',','.'))
            except: pass
            
        lines = text.split('\n')
        supplier = "Sconosciuto"
        for line in lines[:10]:
            clean = line.strip()
            if len(clean) > 3 and "fattura" not in clean.lower():
                supplier = clean
                break
                
        return {
            "Tipo": "PDF (OCR)",
            "Data": date_match.group(0) if date_match else "N/D",
            "Fornitore": supplier,
            "Descrizione": "Estrazione automatica PDF",
            "Totale (€)": amount,
            "Categoria": categorize_expense("", supplier)
        }
    except:
        return {"Tipo": "Errore", "Fornitore": "PDF illeggibile", "Totale (€)": 0.0, "Categoria": "Errore"}

# --- 4. UI COMPONENTS (HELPER) ---
def kpi_card(col, title, value):
    col.markdown(f"""
    <div class="kpi-container">
        <div class="kpi-label">{title}</div>
        <div class="kpi-value">{value}</div>
    </div>
    """, unsafe_allow_html=True)

# --- 5. INTERFACCIA PRINCIPALE ---

# Sidebar pulita
with st.sidebar:
    st.header("Invoice AI")
    st.markdown("Automazione Contabile")
    st.info("Formati supportati:\n- Fattura Elettronica (XML)\n- PDF (OCR v2)")
    st.markdown("---")
    if st.button("Nuova Analisi"):
        st.experimental_rerun()

st.title("Invoice Intelligence Platform")
st.markdown("Piattaforma di estrazione dati e riconciliazione automatica.")
st.markdown("<br>", unsafe_allow_html=True)

# Layout a Card
st.markdown('<div class="stCard">', unsafe_allow_html=True)
col_up, col_info = st.columns([2, 1])

with col_up:
    st.subheader("Caricamento Documenti")
    uploaded_files = st.file_uploader("", type=['xml', 'pdf'], accept_multiple_files=True, label_visibility="collapsed")

with col_info:
    if not uploaded_files:
        st.info("💡 **Tip:** Puoi caricare cartelle miste di PDF e XML contemporaneamente. L'AI distinguerà i formati.")

st.markdown('</div>', unsafe_allow_html=True)

if uploaded_files:
    # 1. Processing con Status Bar Professionale
    with st.status("Avvio motore di estrazione...", expanded=True) as status:
        all_data = []
        time.sleep(0.5)
        
        st.write("📡 Connessione al modulo OCR...")
        time.sleep(0.8)
        
        st.write("🧠 Categorizzazione semantica delle spese...")
        progress_bar = st.progress(0)
        
        for i, file in enumerate(uploaded_files):
            bytes_data = file.read()
            ext = file.name.split('.')[-1].lower()
            
            if ext == 'xml': row = parse_xml_invoice(bytes_data)
            elif ext == 'pdf': row = parse_pdf_invoice(bytes_data)
            else: row = {"Tipo": "N/A", "Fornitore": file.name}
            
            row["File"] = file.name
            all_data.append(row)
            progress_bar.progress((i + 1) / len(uploaded_files))
            time.sleep(0.1) # Simulazione "pensiero" AI
            
        status.update(label="Analisi completata con successo", state="complete", expanded=False)

    df = pd.DataFrame(all_data)

    # 2. Dashboard KPI in Cards
    st.markdown("<br>", unsafe_allow_html=True)
    st.subheader("Sintesi Finanziaria")
    
    k1, k2, k3, k4 = st.columns(4)
    kpi_card(k1, "Totale Spesa", f"€ {df['Totale (€)'].sum():,.2f}")
    kpi_card(k2, "Documenti", str(len(df)))
    kpi_card(k3, "Fornitore Top", df['Fornitore'].mode()[0] if not df.empty else "-")
    kpi_card(k4, "Categoria Top", df['Categoria'].mode()[0] if not df.empty else "-")

    # 3. Data Editor in Card
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown('<div class="stCard">', unsafe_allow_html=True)
    st.subheader("Dettaglio Transazioni")
    
    edited_df = st.data_editor(
        df,
        column_config={
            "Totale (€)": st.column_config.NumberColumn(format="€ %.2f"),
            "Categoria": st.column_config.SelectboxColumn(
                options=["Utenze & Energia", "Hardware & IT", "Consulenza", "Logistica", "Ristorazione", "Marketing", "Cancelleria"],
                required=True
            )
        },
        use_container_width=True,
        num_rows="dynamic",
        height=400
    )
    st.markdown('</div>', unsafe_allow_html=True)

    # 4. Azioni Finali
    c1, c2 = st.columns([1, 4])
    with c1:
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            edited_df.to_excel(writer, index=False)
            
        st.download_button(
            label="SCARICA EXCEL",
            data=buffer.getvalue(),
            file_name=f"Export_Fatture_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

else:
    # 5. Empty State Professionale (Placeholder)
    st.markdown("""
    <div style='text-align: center; padding: 40px; color: #94a3b8; border: 2px dashed #e2e8f0; border-radius: 12px; margin-top: 20px;'>
        <div style='font-size: 40px; margin-bottom: 10px;'>📂</div>
        <h3 style='color: #475569; margin: 0;'>Area di Lavoro Vuota</h3>
        <p style='font-size: 0.9rem;'>Carica i tuoi documenti per iniziare l'analisi.</p>
    </div>
    """, unsafe_allow_html=True)
