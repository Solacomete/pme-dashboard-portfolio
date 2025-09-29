
import os
import pandas as pd
import numpy as np
import plotly.express as px
import streamlit as st
from datetime import datetime

st.set_page_config(page_title="PME Dashboard – Démo", page_icon="📊", layout="wide")

# ========= Auth forte (Google SSO + TOTP) avec fallback mot de passe =========
import requests
from authlib.integrations.requests_client import OAuth2Session
import pyotp, qrcode
from io import BytesIO

def secret_get(key, default=None):
    try:
        return st.secrets.get(key, default)
    except Exception:
        return default

# SECRETS / CONFIG
GOOGLE_CLIENT_ID = secret_get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = secret_get("GOOGLE_CLIENT_SECRET")
OAUTH_REDIRECT_URI = secret_get("OAUTH_REDIRECT_URI")  # ex: https://tonapp.streamlit.app
ALLOWED_EMAILS = [e.strip().lower() for e in str(secret_get("ALLOWED_EMAILS","")).split(",") if e.strip()]
TOTP_ENABLED = str(secret_get("TOTP_ENABLED","false")).lower()=="true"
TOTP_SHARED_SECRET = secret_get("TOTP_SHARED_SECRET")  # ex: JBSWY3DPEHPK3PXP
APP_PASSWORD = secret_get("APP_PASSWORD")  # fallback

def oauth_configured():
    return bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET and OAUTH_REDIRECT_URI)

def require_password_fallback():
    """Fallback si OAuth non configuré : exige APP_PASSWORD."""
    if not APP_PASSWORD:
        st.error("Sécurité non configurée (ni OAuth ni mot de passe). Ajoute au moins APP_PASSWORD dans les Secrets.")
        st.stop()
    with st.sidebar:
        pwd = st.text_input("Mot de passe", type="password")
        if st.button("Se connecter"):
            st.session_state["_PW_OK"] = (pwd == APP_PASSWORD)
    if not st.session_state.get("_PW_OK"):
        st.stop()

def do_google_login():
    """SSO Google + liste blanche d'emails."""
    if st.session_state.get("user_email"):
        return
    # Étape 1 : rediriger vers Google
    if "code" not in st.query_params:
        client = OAuth2Session(
            GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET,
            scope="openid email profile",
            redirect_uri=OAUTH_REDIRECT_URI
        )
        auth_url, state = client.create_authorization_url(
            "https://accounts.google.com/o/oauth2/v2/auth",
            prompt="consent", access_type="offline", include_granted_scopes="true"
        )
        st.session_state["oauth_state"] = state
        st.markdown("### Connexion requise")
        st.link_button("Se connecter avec Google", auth_url, use_container_width=True)
        st.stop()

    # Étape 2 : retour Google → échange du code
    if st.query_params.get("state") != st.session_state.get("oauth_state"):
        st.error("State OAuth invalide. Rafraîchis la page.")
        st.stop()

    client = OAuth2Session(GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, redirect_uri=OAUTH_REDIRECT_URI)
    token = client.fetch_token("https://oauth2.googleapis.com/token", code=st.query_params["code"])

    # Récupérer l'email
    resp = requests.get("https://www.googleapis.com/oauth2/v3/userinfo",
                        headers={"Authorization": f"Bearer {token['access_token']}"}, timeout=10)
    userinfo = resp.json()
    email = (userinfo or {}).get("email")
    if not email:
        st.error("Impossible de récupérer l'email Google.")
        st.stop()

    # Liste blanche
    if ALLOWED_EMAILS and email.lower() not in ALLOWED_EMAILS:
        st.error("Email non autorisé.")
        st.stop()

    st.session_state["user_email"] = email

def do_totp_guard():
    """2e facteur TOTP (Google Authenticator)."""
    if not TOTP_ENABLED:
        return
    if st.session_state.get("totp_ok"):
        return

    st.markdown("### Vérification TOTP (2ᵉ facteur)")
    if not TOTP_SHARED_SECRET:
        st.error("TOTP activé mais TOTP_SHARED_SECRET manquant dans les Secrets.")
        st.stop()

    # QR une seule fois pour provisionner l’app Authenticator
    if not st.session_state.get("totp_qr_shown"):
        try:
            totp = pyotp.TOTP(TOTP_SHARED_SECRET)
            otpauth = totp.provisioning_uri(
                name=st.session_state.get("user_email","user"),
                issuer_name=secret_get("BUSINESS_NAME","PME Dashboard")
            )
            img = qrcode.make(otpauth)
            buf = BytesIO(); img.save(buf, format="PNG")
            st.image(buf.getvalue(), caption="Scanne ce QR dans Google Authenticator", width=200)
            st.session_state["totp_qr_shown"] = True
        except Exception:
            pass

    code = st.text_input("Code à 6 chiffres (Google Authenticator)", max_chars=6)
    if st.button("Vérifier"):
        totp = pyotp.TOTP(TOTP_SHARED_SECRET)
        if totp.verify(code, valid_window=1):
            st.session_state["totp_ok"] = True
            st.experimental_rerun()
        else:
            st.error("Code invalide.")
    st.stop()

def secure_gate():
    # Bouton déconnexion optionnel
    with st.sidebar:
        if st.button("Se déconnecter"):
            st.session_state.clear()
            st.experimental_rerun()

    # Si OAuth configuré → SSO Google + TOTP
    if oauth_configured():
        do_google_login()
        do_totp_guard()
    else:
        # Sinon → fallback mot de passe
        require_password_fallback()

# <<< APPEL PORTE SÉCURISÉE AVANT TOUT LE RESTE >>>
secure_gate()
# ============================================================================


# -------------------
# Helpers / Secrets
# -------------------
def secret_get(key, default=None):
    try:
        return st.secrets.get(key, default)
    except Exception:
        return default

DEMO_MODE    = str(secret_get("DEMO_MODE", "false")).lower() == "true"
BUSINESS_NAME= secret_get("BUSINESS_NAME", "Boulangerie Démo")
APP_PASSWORD = secret_get("APP_PASSWORD", None)

# -------------------
# Auth minimal via secrets
# -------------------
def check_auth():
    required = APP_PASSWORD
    if not required:
        return True  # no password set -> public demo
    with st.sidebar:
        pwd = st.text_input("Mot de passe", type="password", help="Défini dans st.secrets['APP_PASSWORD']")
        if st.button("Se connecter"):
            st.session_state["_OK"] = (pwd == required)
        if st.session_state.get("_OK", False):
            return True
        else:
            st.stop()

# -------------------
# Utils
# -------------------
@st.cache_data
def load_csv(path):
    return pd.read_csv(path)

def load_data():
    base = os.path.join(os.path.dirname(__file__), "data")
    products  = load_csv(os.path.join(base, "products.csv"))
    customers = load_csv(os.path.join(base, "customers.csv"))
    sales     = load_csv(os.path.join(base, "sales.csv"))
    inventory = load_csv(os.path.join(base, "inventory_movements.csv"))
    expenses  = load_csv(os.path.join(base, "expenses.csv"))
    # parse dates
    sales["date"]     = pd.to_datetime(sales["date"])
    inventory["date"] = pd.to_datetime(inventory["date"])
    expenses["date"]  = pd.to_datetime(expenses["date"])
    return products, customers, sales, inventory, expenses

def compute_stock(products, inventory):
    init   = products[["product_id","initial_stock"]].copy()
    in_qty = inventory[inventory["type"]=="in"].groupby("product_id")["quantity"].sum().rename("in_qty")
    out_qty= inventory[inventory["type"]=="out"].groupby("product_id")["quantity"].sum().rename("out_qty")
    stock  = init.merge(in_qty, how="left", on="product_id").merge(out_qty, how="left", on="product_id").fillna(0)
    stock["current_stock"] = stock["initial_stock"] + stock["in_qty"] - stock["out_qty"]
    # return products + current_stock only (min_stock/name/category stay from products)
    return products.merge(stock[["product_id","current_stock"]], on="product_id", how="left")

def kpi_card(label, value, delta=None, help_txt=None):
    c = st.container()
    with c:
        st.metric(label, value, delta=delta, help=help_txt)
    return c

# -------------------
# App
# -------------------
check_auth()

st.title(f"📊 {BUSINESS_NAME} – Dashboard")
# Logo (optionnel)
logo_path = os.path.join(os.path.dirname(__file__), "assets", "logo.png")
if os.path.exists(logo_path):
    st.image("assets/logo.png", width=72)

products, customers, sales, inventory, expenses = load_data()

# Sidebar filters
with st.sidebar:
    st.header("Filtres")
    min_d, max_d = sales["date"].min().date(), sales["date"].max().date()
    d1, d2 = st.date_input("Période", (min_d, max_d))
    cats = ["(Tous)"] + sorted(products["category"].unique().tolist())
    cat = st.selectbox("Catégorie produit", cats)
    pm = ["(Tous)"] + sorted(sales["payment_method"].unique().tolist())
    pay = st.selectbox("Moyen de paiement", pm)
    if DEMO_MODE:
        st.info("Mode démo : export CSV désactivé.")

# Filter base
mask = (sales["date"].dt.date >= d1) & (sales["date"].dt.date <= d2)
sales_f = sales.loc[mask].copy()
if pay != "(Tous)":
    sales_f = sales_f[sales_f["payment_method"] == pay]

# Merge product fields (one time)
sales_f = sales_f.merge(
    products[["product_id","name","category","unit_price","cost_price","tax_rate"]],
    on="product_id",
    how="left",
    suffixes=("", "_prod")
)

# Harmonize columns
if "unit_price_prod" in sales_f.columns:
    if "unit_price" not in sales_f.columns:
        sales_f["unit_price"] = sales_f["unit_price_prod"]
    else:
        sales_f["unit_price"] = sales_f["unit_price"].fillna(sales_f["unit_price_prod"])

if "cost_price" not in sales_f.columns and "cost_price_prod" in sales_f.columns:
    sales_f["cost_price"] = sales_f["cost_price_prod"]
if "tax_rate" not in sales_f.columns and "tax_rate_prod" in sales_f.columns:
    sales_f["tax_rate"] = sales_f["tax_rate_prod"]
if "name" not in sales_f.columns and "name_prod" in sales_f.columns:
    sales_f["name"] = sales_f["name_prod"]
if "category" not in sales_f.columns and "category_prod" in sales_f.columns:
    sales_f["category"] = sales_f["category_prod"]

# Category filter (after merge)
if cat != "(Tous)":
    sales_f = sales_f[sales_f["category"] == cat]

# Computed fields
sales_f["discount"]   = sales_f.get("discount", 0.0).fillna(0.0)
sales_f["quantity"]   = sales_f["quantity"].fillna(0).astype(float)
sales_f["unit_price"] = sales_f["unit_price"].fillna(0.0).astype(float)
sales_f["cost_price"] = sales_f["cost_price"].fillna(0.0).astype(float)

sales_f["line_price"] = sales_f["unit_price"] * sales_f["quantity"] - sales_f["discount"]
sales_f["cogs"]       = sales_f["cost_price"] * sales_f["quantity"]
sales_f["margin"]     = sales_f["line_price"] - sales_f["cogs"]

# KPIs
rev        = float(sales_f["line_price"].sum())
cogs_total = float(sales_f["cogs"].sum())
gm         = rev - cogs_total
orders     = int(sales_f["sale_id"].nunique())
avg_ticket = (rev / orders) if orders else 0.0

col1, col2, col3, col4 = st.columns(4)
kpi_card("Chiffre d'affaires", f"{rev:,.0f} €".replace(",", " "), None, "Total des ventes (net de remise)")
kpi_card("Marge brute",        f"{gm:,.0f} €".replace(",", " "),  None, "Ventes - Coût des marchandises vendues")
kpi_card("Nb. tickets",        f"{orders:,}".replace(",", " "),   None, "Nombre de ventes")
kpi_card("Panier moyen",       f"{avg_ticket:,.2f} €".replace(",", " "), None, "CA / ticket")

# Evolution
st.subheader("Évolution")
by_day = sales_f.groupby(sales_f["date"].dt.date)["line_price"].sum().reset_index(name="CA")
fig = px.line(by_day, x="date", y="CA", title="CA par jour")
st.plotly_chart(fig, use_container_width=True)

# Top produits & Paiements
colA, colB = st.columns(2)
with colA:
    st.subheader("Top produits")
    top_p = (sales_f.groupby(["product_id","name"])["line_price"]
             .sum().reset_index().sort_values("line_price", ascending=False).head(10))
    fig2 = px.bar(top_p, x="name", y="line_price", title="Top 10 produits", labels={"line_price":"CA"})
    st.plotly_chart(fig2, use_container_width=True)
with colB:
    st.subheader("Moyens de paiement")
    pay_split = sales_f.groupby("payment_method")["line_price"].sum().reset_index()
    fig3 = px.pie(pay_split, names="payment_method", values="line_price", title="Répartition CA par paiement")
    st.plotly_chart(fig3, use_container_width=True)

# Résultat approximatif
st.subheader("Résultat (approx.)")
exp_f = expenses[(expenses["date"].dt.date >= d1) & (expenses["date"].dt.date <= d2)].copy()
total_exp = float(exp_f["amount"].sum())
profit = gm - total_exp

colE1, colE2, colE3 = st.columns(3)
kpi_card("Dépenses",         f"{total_exp:,.0f} €".replace(",", " "))
kpi_card("Résultat estimé",  f"{profit:,.0f} €".replace(",", " "))
by_cat = exp_f.groupby("category")["amount"].sum().reset_index()
fig4 = px.bar(by_cat, x="category", y="amount", title="Dépenses par catégorie")
st.plotly_chart(fig4, use_container_width=True)

# Stocks
st.subheader("Stocks")
stock = compute_stock(products, inventory)

# Ensure we have columns
if not set(["name","category","min_stock"]).issubset(stock.columns):
    stock = stock.merge(products[["product_id","name","category","min_stock"]], on="product_id", how="left")

low = stock.loc[stock["current_stock"] <= stock["min_stock"], ["product_id","name","category","current_stock","min_stock"]]

st.dataframe(
    low.rename(columns={
        "product_id":"ID",
        "name":"Produit",
        "category":"Catégorie",
        "current_stock":"Stock actuel",
        "min_stock":"Seuil"
    })
)

# Export
if DEMO_MODE:
    st.info("Mode démo activé : export désactivé pour cette instance publique.")
else:
    st.download_button(
        "Exporter les ventes filtrées (CSV)",
        data=sales_f.to_csv(index=False).encode("utf-8"),
        file_name="ventes_filtrees.csv"
    )

st.caption("Démo – Construite pour artisans / TPE. © 2025")
