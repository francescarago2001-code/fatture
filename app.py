import streamlit as st
import pandas as pd
import pdfplumber
import xmltodict
import io
import re
from datetime import datetime

# --- 1. CONFIGURAZIONE PAGINA ---
st.set_page_config(
    page_title="Invoice Intelligence Pro",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- 2. CSS PROFESSIONAL BLUE ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600&display=swap');
    
    :root {
        --primary-blue: #0f172a;
        --accent-blue: #2563eb;
        --bg-color: #f8fafc;
        --text-color: #334155;
    }

    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
        color: var(--text-color);
        background-color: white;
    }

    /* Sidebar */
    [data-testid="stSidebar"] {
        background-color: var(--bg-color);
        border-right: 1px solid #e2e8f0;
    }

    /* Cards */
    .metric-card {
        background-color: white;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 20px;
        text-align: center;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    .metric-value {
        font-size: 24px;
        font-weight: 700;
        color: var(--primary-blue);
    }
    .metric-label {
        font-size: 14px;
        color: #64748b;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }

    /* Buttons */
    .stButton>button {
        background-color: var(--primary-blue);
        color: white;
        border-radius: 6px;
        border: none;
        padding: 0.6rem 1.2rem;
        font-weight: 600;
        transition: all 0.2s;
        width: 100%;
    }
    .stButton>button:hover {
        background-color: var(--accent-blue);
        box-shadow: 0 4px 6px -1px rgba(37, 99, 235, 0.2);
    }

    /* Tables */
    [data-testid="stDataFrame"] {
        border: 1px solid #e2e8f0;
        border-radius: 6px;
    }

    /* Headers */
    h1, h2, h3 {
        color: var(--primary-blue) !important;
        font-weight: 700;
    }
    
    /* Upload Area */
    [data-testid="stFileUploader"] {
        border: 1px dashed #cbd5e1;
        border-radius: 8px;
        padding: 20px;
        background-color: #f8fafc;
    }
    </style>
""", unsafe_allow_html=True)

# --- 3. MOTORE DI ESTRAZIONE (CORE) ---

def categorize_expense(description, supplier):
    """
    Motore 'Intelligente' per categorizzare le spese basandosi su keyword.
    In un sistema reale, questo potrebbe essere sostituito da un modello ML o API GPT.
    """
    text = (str(description) + " " + str(supplier)).lower()
    
    categories = {
        "Utenze & Energia": ["enel", "eni", "luce", "gas", "energia", "a2a", "edison"],
        "Hardware & IT": ["apple", "dell", "lenovo", "server", "hosting", "software", "mouse", "pc", "aws", "google"],
        "Consulenza & Servizi": ["avvocato", "commercialista", "notai", "consulenza", "fee"],
        "Logistica & Trasporti": ["dhl", "fedex", "poste", "bartolini", "gls", "spedizione", "carburante"],
        "Ristorazione & Viaggi": ["ristorante", "hotel", "treno", "volo", "airbnb", "uber", "pranzo"],
        "Marketing": ["facebook", "ads", "linkedin", "google ads", "stampa", "brochure"],
        "Cancelleria": ["carta", "penne", "ufficio", "toner"]
    }
    
    for category, keywords in categories.items():
        if any(k in text for k in keywords):
            return category
    return "Altro / Generale"

def parse_xml_invoice(file_content):
    """Estrae dati da Fattura Elettronica (XML Italiano Standard)"""
    try:
        doc = xmltodict.parse(file_content)
        header = doc.get('p:FatturaElettronica', {}).get('FatturaElettronicaHeader', {})
        body = doc.get('p:FatturaElettronica', {}).get('FatturaElettronicaBody', {})
        
        # Gestione liste (a volte il body è una lista se ci sono più documenti)
        if isinstance(body, list): body = body[0]
        
        # Dati Fornitore
        supplier = header.get('CedentePrestatore', {}).get('DatiAnagrafici', {}).get('Anagrafica', {}).get('Denominazione')
        if not supplier:
            nome = header.get('CedentePrestatore', {}).get('DatiAnagrafici', {}).get('Anagrafica', {}).get('Nome', '')
            cognome = header.get('CedentePrestatore', {}).get('DatiAnagrafici', {}).get('Anagrafica', {}).get('Cognome', '')
            supplier = f"{nome} {cognome}"

        # Dati Documento
        gen_data = body.get('DatiGenerali', {}).get('DatiGeneraliDocumento', {})
        date_str = gen_data.get('Data', '')
        number = gen_data.get('Numero', '')
        amount = body.get('DatiGenerali', {}).get('DatiGeneraliDocumento', {}).get('ImportoTotaleDocumento', 0.0)
        
        # Descrizione per categoria (prima riga di dettaglio)
        details = body.get('DatiBeniServizi', {}).get('DettaglioLinee', [])
        description = ""
        if isinstance(details, list) and len(details) > 0:
            description = details[0].get('Descrizione', '')
        elif isinstance(details, dict):
            description = details.get('Descrizione', '')

        return {
            "Tipo": "XML (E-Fattura)",
            "Data": date_str,
            "Fornitore": supplier,
            "Numero": number,
            "Descrizione": description,
            "Totale (€)": float(amount) if amount else 0.0,
            "Categoria": categorize_expense(description, supplier)
        }
    except Exception as e:
        return {"Tipo": "XML Error", "Fornitore": "Errore lettura XML", "Totale (€)": 0.0, "Note": str(e)}

def parse_pdf_invoice(file_bytes):
    """
    Estrae dati da PDF usando euristiche posizionali e Regex.
    Nota: I PDF sono complessi, questo è un estrattore generico "Best Effort".
    """
    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            text = ""
            for page in pdf.pages:
                text += page.extract_text() or ""
        
        # Euristiche Regex base
        # 1. Cerca date (DD/MM/YYYY o YYYY-MM-DD)
        date_match = re.search(r'\d{2}/\d{2}/\d{4}|\d{4}-\d{2}-\d{2}', text)
        invoice_date = date_match.group(0) if date_match else "N/D"
        
        # 2. Cerca Totali (Cerca parole chiave come Totale, Importo, Total)
        # Cerca un numero con virgola o punto vicino alla parola Totale
        amount_match = re.search(r'(?i)(?:totale|importo|total|amount)[\s:]+.*?(\d+[.,]\d{2})', text)
        amount = 0.0
        if amount_match:
            amount_str = amount_match.group(1).replace('.','').replace(',','.') # Normalizza
            try: amount = float(amount_str)
            except: pass
            
        # 3. Fornitore (Euristica: prime righe o parole chiave)
        lines = text.split('\n')
        # Prendiamo la prima riga non vuota che non sia "Fattura" come probabile fornitore
        supplier = "Sconosciuto"
        for line in lines[:10]:
            clean_line = line.strip()
            if len(clean_line) > 3 and "fattura" not in clean_line.lower() and "spett" not in clean_line.lower():
                supplier = clean_line
                break
                
        return {
            "Tipo": "PDF",
            "Data": invoice_date,
            "Fornitore": supplier,
            "Numero": "N/D (Vedi PDF)",
            "Descrizione": "Estrazione da PDF",
            "Totale (€)": amount,
            "Categoria": categorize_expense("", supplier) # Categorizza in base al nome fornitore
        }
    except Exception as e:
        return {"Tipo": "PDF Error", "Fornitore": "Errore lettura PDF", "Totale (€)": 0.0, "Note": str(e)}

# --- 4. INTERFACCIA UTENTE ---

st.title("Invoice Intelligence Pro")
st.markdown("Sistema di estrazione automatica e categorizzazione costi da documenti passivi.")

col1, col2 = st.columns([1, 3])

with col1:
    st.markdown("### Pannello Controllo")
    st.info("Carica XML (Fattura Elettronica) o PDF. Il sistema estrarrà i metadati e creerà il file Excel.")
    uploaded_files = st.file_uploader("Trascina qui le fatture", type=['xml', 'pdf'], accept_multiple_files=True)
    
    if st.button("🔄 Resetta Analisi"):
        st.experimental_rerun()

with col2:
    if uploaded_files:
        st.subheader(f"Analisi in corso di {len(uploaded_files)} documenti...")
        
        all_data = []
        progress_bar = st.progress(0)
        
        for i, file in enumerate(uploaded_files):
            file_bytes = file.read()
            filename = file.name
            ext = filename.split('.')[-1].lower()
            
            data = {}
            if ext == 'xml':
                data = parse_xml_invoice(file_bytes)
            elif ext == 'pdf':
                data = parse_pdf_invoice(file_bytes)
            else:
                data = {"Tipo": "Non supportato", "Fornitore": filename}
            
            # Aggiunge nome file originale
            data["Nome File"] = filename
            all_data.append(data)
            
            # Aggiorna barra
            progress_bar.progress((i + 1) / len(uploaded_files))
            
        # Creazione DataFrame
        df = pd.DataFrame(all_data)
        
        # --- DASHBOARD DEI RISULTATI ---
        st.markdown("---")
        
        # 1. KPI Cards
        kpi1, kpi2, kpi3 = st.columns(3)
        total_spent = df['Totale (€)'].sum()
        top_supplier = df['Fornitore'].mode()[0] if not df.empty else "-"
        top_category = df['Categoria'].mode()[0] if not df.empty else "-"
        
        kpi1.markdown(f"<div class='metric-card'><div class='metric-label'>Totale Spesa Rilevata</div><div class='metric-value'>€ {total_spent:,.2f}</div></div>", unsafe_allow_html=True)
        kpi2.markdown(f"<div class='metric-card'><div class='metric-label'>Fornitore Principale</div><div class='metric-value'>{top_supplier}</div></div>", unsafe_allow_html=True)
        kpi3.markdown(f"<div class='metric-card'><div class='metric-label'>Categoria Top</div><div class='metric-value'>{top_category}</div></div>", unsafe_allow_html=True)
        
        st.markdown("### Dettaglio Estrazioni")
        
        # 2. Tabella Interattiva (Editabile per correzioni manuali)
        edited_df = st.data_editor(
            df,
            column_config={
                "Totale (€)": st.column_config.NumberColumn(format="€ %.2f"),
                "Data": st.column_config.TextColumn(),
                "Categoria": st.column_config.SelectboxColumn(
                    options=["Utenze & Energia", "Hardware & IT", "Consulenza & Servizi", 
                             "Logistica & Trasporti", "Ristorazione & Viaggi", 
                             "Marketing", "Cancelleria", "Altro / Generale"],
                    required=True
                )
            },
            use_container_width=True,
            num_rows="dynamic"
        )
        
        # 3. Export Excel
        st.markdown("### Esportazione")
        
        # Generazione file Excel in memoria
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            edited_df.to_excel(writer, index=False, sheet_name='Fatture')
            
        st.download_button(
            label="📥 Scarica Report Excel (.xlsx)",
            data=buffer.getvalue(),
            file_name=f"Report_Fatture_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        
    else:
        # Stato Iniziale (Empty State)
        st.markdown("""
        <div style='text-align: center; padding: 50px; color: #94a3b8;'>
            <h3>In attesa di documenti...</h3>
            <p>Carica i file XML o PDF dal menu a sinistra per vedere l'intelligenza artificiale in azione.</p>
        </div>
        """, unsafe_allow_html=True)
