"""Tema visual leve e centralizado da aplicação Streamlit."""

from __future__ import annotations

import streamlit as st


APP_CSS = """
<style>
:root {
  --iica-blue: #1677ff;
  --iica-cyan: #0ea5c6;
  --iica-ink: #172033;
  --iica-muted: #617089;
  --iica-border: #dfe6f0;
  --iica-surface: #ffffff;
  --iica-soft: #f5f7fb;
  --iica-shadow: 0 10px 28px rgba(28, 55, 90, 0.055);
}

[data-testid="stAppViewContainer"] {
  background:
    radial-gradient(circle at 88% 0%, rgba(22, 119, 255, 0.055), transparent 24rem),
    var(--iica-soft);
}

[data-testid="stHeader"] { background: rgba(245, 247, 251, 0.86); }

[data-testid="stMainBlockContainer"] {
  max-width: 1180px;
  padding-top: 2.2rem;
  padding-bottom: 5.5rem;
}

.iica-hero {
  border-bottom: 1px solid var(--iica-border);
  margin-bottom: 2rem;
  padding: 0.25rem 0 1.65rem;
}

.iica-brand-row { display: flex; align-items: center; gap: 0.8rem; }
.iica-brand-mark {
  align-items: center;
  background: linear-gradient(135deg, var(--iica-blue), var(--iica-cyan));
  border-radius: 0.85rem;
  box-shadow: 0 7px 18px rgba(22, 119, 255, 0.18);
  color: white;
  display: inline-flex;
  font-size: 1.18rem;
  height: 2.65rem;
  justify-content: center;
  width: 2.65rem;
}

.iica-brand-title {
  color: var(--iica-ink);
  font-size: clamp(1.75rem, 3vw, 2.35rem);
  font-weight: 760;
  letter-spacing: -0.04em;
  line-height: 1;
}

.iica-brand-kicker {
  color: var(--iica-blue);
  font-size: 0.72rem;
  font-weight: 750;
  letter-spacing: 0.13em;
  margin-top: 0.36rem;
  text-transform: uppercase;
}

.iica-hero-copy {
  color: var(--iica-muted);
  font-size: 1rem;
  line-height: 1.65;
  margin: 1rem 0 0;
  max-width: 720px;
}

.iica-section-label {
  color: var(--iica-blue);
  font-size: 0.72rem;
  font-weight: 760;
  letter-spacing: 0.12em;
  margin-bottom: 0.35rem;
  text-transform: uppercase;
}

.iica-answer-label {
  color: var(--iica-muted);
  font-size: 0.68rem;
  font-weight: 760;
  letter-spacing: 0.12em;
  margin-bottom: 0.35rem;
  text-transform: uppercase;
}

.iica-source {
  background: #f6f9fd;
  border: 1px solid #e3eaf4;
  border-radius: 0.65rem;
  color: #53627a;
  font-size: 0.82rem;
  line-height: 1.55;
  margin: 0.75rem 0 0.85rem;
  padding: 0.65rem 0.8rem;
}

.iica-source strong { color: #26344a; }

.st-key-upload_card,
.st-key-summary_card,
.st-key-query_card,
[class*="st-key-evidence_card_"] {
  background: rgba(255, 255, 255, 0.96);
  border-color: var(--iica-border) !important;
  border-radius: 0.9rem !important;
  box-shadow: var(--iica-shadow);
  padding: 0.35rem;
}

[data-testid="stFileUploaderDropzone"] {
  background: #f8fbff;
  border-color: #b9cee9;
  border-radius: 0.8rem;
  padding: 1.1rem;
  transition: border-color 150ms ease, box-shadow 150ms ease, background 150ms ease;
}

[data-testid="stFileUploaderDropzone"]:hover {
  background: #f3f8ff;
  border-color: var(--iica-blue);
  box-shadow: 0 0 0 3px rgba(22, 119, 255, 0.08);
}

[data-testid="stBaseButton-primary"],
[data-testid="stBaseButton-secondary"] {
  font-weight: 680;
  transition: transform 130ms ease, box-shadow 130ms ease, border-color 130ms ease;
}

[data-testid="stBaseButton-primary"]:hover {
  box-shadow: 0 7px 16px rgba(22, 119, 255, 0.17);
  transform: translateY(-1px);
}

[data-testid="stBaseButton-secondary"]:hover {
  border-color: #a9bad0;
  transform: translateY(-1px);
}

[data-testid="stMetric"] {
  background: var(--iica-surface);
  border: 1px solid var(--iica-border);
  border-radius: 0.78rem;
  box-shadow: 0 5px 16px rgba(28, 55, 90, 0.035);
  min-height: 7rem;
  padding: 0.85rem 1rem;
}

[data-testid="stMetricLabel"] { color: var(--iica-muted); }
[data-testid="stMetricValue"] { color: var(--iica-ink); }

[data-testid="stChatMessage"] {
  background: rgba(255, 255, 255, 0.94);
  border: 1px solid #e4eaf2;
  border-radius: 0.85rem;
  box-shadow: 0 4px 14px rgba(28, 55, 90, 0.035);
  margin-bottom: 0.75rem;
  padding: 0.55rem 0.7rem;
}

[data-testid="stChatInput"] {
  background: white;
  border-color: #cdd9e8;
  box-shadow: 0 8px 24px rgba(28, 55, 90, 0.08);
}

[data-testid="stAlert"], [data-testid="stStatusWidget"] {
  border-radius: 0.72rem;
  box-shadow: 0 4px 14px rgba(28, 55, 90, 0.03);
}

[data-testid="stDataFrame"], [data-testid="stPlotlyChart"] {
  border-radius: 0.72rem;
  overflow: hidden;
}

[data-testid="stExpander"] {
  background: white;
  border-color: var(--iica-border);
  border-radius: 0.72rem;
}

hr { border-color: var(--iica-border) !important; margin: 2.4rem 0 !important; }

@media (max-width: 760px) {
  [data-testid="stMainBlockContainer"] { padding: 1.25rem 1rem 5rem; }
  .iica-hero { margin-bottom: 1.35rem; }
  .iica-brand-title { font-size: 1.7rem; }
  .iica-brand-mark { height: 2.35rem; width: 2.35rem; }
  [data-testid="stMetric"] { min-height: 5.8rem; }
}

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { scroll-behavior: auto !important; transition: none !important; }
}
</style>
"""


def apply_app_styles() -> None:
    """Aplica CSS estático; nenhum dado do usuário é interpolado como HTML."""

    st.markdown(APP_CSS, unsafe_allow_html=True)


__all__ = ["APP_CSS", "apply_app_styles"]
