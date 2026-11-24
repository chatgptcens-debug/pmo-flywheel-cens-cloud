"""Apariencia Paso 2 inspirada en prototipo HTML de usuario; sin lógica de datos.

Conserva los componentes nativos de Streamlit para formularios y accesibilidad.
No inyecta controles HTML simulados ni indicadores ficticios.
"""
from __future__ import annotations
import streamlit as st

STYLES = r"""
<style>
:root{--p2-navy:#10374B;--p2-teal:#0B9A9F;--p2-orange:#ED9250;
      --p2-ink:#203648;--p2-muted:#718497;--p2-line:#E1E8EF;--p2-bg:#F4F7FA}
/* App Streamlit framed as the supplied PMO CENS HTML */
.stApp{background:var(--p2-bg)!important}
[data-testid="stAppDeployButton"],button[title="Deploy"],
[data-testid="stToolbar"] button[title="Deploy"]{display:none!important}
.block-container{max-width:1660px!important;padding:1.15rem 2.15rem 3.25rem!important}
.pmo-topbar{margin-bottom:20px!important;min-height:54px;border-radius:10px!important}
.pmo-eyebrow{margin-bottom:7px!important}
.pmo-title{font-size:27px!important;letter-spacing:-.8px!important}
.pmo-subtitle{margin-bottom:19px!important;font-size:12.5px!important}
/* Sidebar: smaller, cleaner and closer to the HTML prototype */
[data-testid="stSidebar"]{min-width:250px!important;max-width:250px!important}
[data-testid="stSidebar"] [role="radiogroup"]>label{
  min-height:38px!important;padding:7px 9px!important;margin:2px 0!important;
  font-size:12px!important;line-height:1.35!important;
}
[data-testid="stSidebar"] [data-testid="stRadio"]>div[role="radiogroup"]{gap:2px!important}
[data-testid="stSidebar"] [role="radiogroup"]>label:has(input:checked){background:#ffffff22!important}
.pmo-side-step{padding:11px 12px!important;margin-bottom:12px!important}
.pmo-sidebar-bottom{margin-top:20px!important}
/* Main panels and controls */
[data-testid="stVerticalBlockBorderWrapper"]>div{
  border:1px solid var(--p2-line)!important;border-radius:15px!important;
  box-shadow:0 8px 24px rgba(20,50,71,.045)!important;
}
.stTabs [data-baseweb="tab-list"]{gap:4px!important;background:#EDF3F6!important;
  border-radius:11px!important;padding:5px!important;border:0!important}
.stTabs button[data-baseweb="tab"]{border-radius:8px!important;font-size:12px!important;
  padding:8px 13px!important;color:#657D8C!important;border-bottom:0!important}
.stTabs button[aria-selected="true"]{background:#fff!important;color:#10374B!important;
  box-shadow:0 1px 7px #10374b17!important;font-weight:750!important}
.stTabs [data-baseweb="tab-highlight"],.stTabs [data-baseweb="tab-border"]{display:none!important}
[data-testid="stFileUploader"]{border:1px dashed #BFD5DE;border-radius:14px;background:#F9FCFD;padding:9px 15px}
[data-testid="stDataFrame"]{border-radius:12px!important;overflow:hidden!important}
[data-testid="stWidgetLabel"] label{font-size:12px!important;color:#506779!important}
/* Intro */
.p2-welcome{position:relative;overflow:hidden;border-radius:16px;
  padding:28px 31px;margin-bottom:17px;color:#fff;
  background:linear-gradient(110deg,#123F54 0%,#1C6870 98%)}
.p2-welcome:before{content:'';position:absolute;width:220px;height:220px;
  border-radius:100%;border:2px solid #ffffff20;right:-70px;top:-95px;pointer-events:none}
.p2-welcome:after{content:'';position:absolute;width:140px;height:140px;
  border-radius:100%;border:2px solid #ffffff12;right:30px;bottom:-94px;pointer-events:none}
.p2-welcome-kicker{font-size:10px;font-weight:850;letter-spacing:1.3px;
  color:#9BE1D8;margin-bottom:10px}
.p2-welcome-title{font-size:24px;font-weight:820;color:white;letter-spacing:-.5px;
  line-height:1.26;max-width:620px;margin-bottom:10px}
.p2-welcome-desc{font-size:12.5px;line-height:1.7;color:#D4E8EA;max-width:650px}
.p2-welcome-tags{display:flex;flex-wrap:wrap;gap:7px;margin-top:18px}
.p2-welcome-tags span{padding:6px 10px;border:1px solid #ffffff32;
  border-radius:15px;background:#ffffff15;font-size:10px;color:#E6F9F7;font-weight:750}
.p2-panel-label{font-size:10px;text-transform:uppercase;letter-spacing:1.2px;
  color:#117E85;font-weight:850;margin:2px 0 7px}
/* Selected diagnosis context: compact, no giant opening form */
.p2-context{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:0;
  background:#fff;border:1px solid #E1E8EF;border-radius:13px;
  margin:10px 0 9px;padding:13px 12px;box-shadow:0 5px 14px #10374b06}
.p2-context-item{padding:2px 17px;border-right:1px solid #EAF0F3;
  min-width:0;display:flex;flex-direction:column;gap:5px}
.p2-context-item:last-child{border-right:0}
.p2-context-item span{color:#8095A4;font-size:10px;font-weight:700;letter-spacing:.2px}
.p2-context-item strong{font-size:12px;color:#203648;font-weight:770;
  text-overflow:ellipsis;overflow:hidden;white-space:nowrap}
.p2-flow{display:flex;justify-content:space-between;align-items:center;gap:6px;
  border:1px solid #DFEDED;background:#F1F9F9;border-radius:11px;
  padding:10px 18px;margin:0 0 20px}
.p2-flow span{font-size:10px;font-weight:850;letter-spacing:.5px;color:#087B82}
.p2-flow b{font-size:14px;font-weight:600;color:#8FBDC0}
/* Original HTML-like pain/gain and outcome cards */
.p2-outcome-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin:8px 0 12px}
.p2-outcome-card{padding:12px;border-radius:10px;border:1px solid #E1E8EF;background:#fff;
  min-height:80px}
.p2-outcome-id{font-size:10px;color:#8C9EA9;font-weight:820;margin-bottom:6px}
.p2-outcome-name{font-size:11.2px;line-height:1.4;color:#2C4556;font-weight:740}
.p2-pain,.p2-gain{border-radius:11px;padding:15px 17px;font-size:12px;line-height:1.7;min-height:116px}
.p2-pain{background:#FFF7F1;border:1px solid #FBE3D1;color:#7B573A}
.p2-gain{background:#EDFAF6;border:1px solid #D2EFE7;color:#27685B}
.p2-panel-cap{font-size:10px;letter-spacing:.8px;font-weight:800;margin:0 0 8px}
.p2-pain .p2-panel-cap{color:#BB8356}
.p2-gain .p2-panel-cap{color:#2B957A}
.p2-mini-guide{display:flex;gap:9px;justify-content:space-between;align-items:center;
  margin:0 0 17px;background:white;border:1px solid #E1E8EF;
  border-radius:12px;padding:13px 15px;flex-wrap:wrap}
.p2-mini-guide span{font-size:10px;color:#608091;font-weight:800}
.p2-mini-guide i{font-size:12px;color:#8AB9BA;font-style:normal}
.p2-section-label{display:flex;align-items:center;gap:8px;color:#758D9E;
  font-weight:800;letter-spacing:1px;font-size:10.5px;text-transform:uppercase;margin:17px 0 11px}
.p2-section-label::before{content:'';height:7px;width:7px;background:#ED9250;border-radius:50%}
.p2-kpi-caption{font-size:10.4px;color:#8095A4;margin-top:6px}
@media(max-width:1080px){.p2-context{grid-template-columns:repeat(2,minmax(0,1fr));row-gap:12px}.p2-context-item:nth-child(2){border-right:0}
.p2-outcome-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:720px){.block-container{padding-left:14px!important;padding-right:14px!important}
.p2-welcome{padding:20px 18px}.p2-welcome-title{font-size:21px}
.p2-context{grid-template-columns:1fr}.p2-context-item{border-right:0;padding:8px 10px;border-bottom:1px solid #EAF0F3}
.p2-context-item:last-child{border-bottom:0}.p2-flow{overflow:auto;white-space:nowrap}
.p2-outcome-grid{grid-template-columns:1fr}}

/* V0.8 — Correspondencia de composición con 12 pantallas del HTML */
[data-testid="stSidebar"]{min-width:254px!important;max-width:254px!important}
[data-testid="stSidebar"] [role="radiogroup"]>label{min-height:35px!important;padding:6px 8px!important;
 font-size:11.2px!important;margin:1px 0!important;white-space:normal!important}
[data-testid="stSidebar"] [role="radiogroup"]>label [data-testid="stMarkdownContainer"] p{
 font-size:11.2px!important;line-height:1.38!important;font-weight:600!important}
.pmo-side-label{margin:14px 9px 7px!important}
.pmo-side-step{margin-bottom:7px!important}
.block-container{max-width:1600px!important;padding-top:.8rem!important}
.pmo-topbar{border-radius:0!important;margin-bottom:18px!important;box-shadow:none!important;
 border:0!important;border-bottom:1px solid #E1E8EF!important}
.pmo-title{font-size:25px!important}
.pmo-subtitle{margin-bottom:12px!important}
.p2-ref-heading{font-size:13.3px;color:#203648;font-weight:800;margin:2px 0 4px;line-height:1.5}
.p2-ref-caption{font-size:10.8px;color:#8397A5;margin-bottom:14px}
.p2-ref-bars{display:grid;gap:12px;margin:8px 0 17px}
.p2-ref-bar-row{display:grid;grid-template-columns:minmax(125px,1.35fr) minmax(85px,2fr) 47px;gap:11px;
 align-items:center;color:#39556B;font-size:10.7px}
.p2-ref-bar-row>div:first-child{line-height:1.35}
.p2-ref-bar-row strong{text-align:right;font-weight:850;white-space:nowrap;color:#244357}
.p2-ref-track{height:8px;background:#EAF0F3;border-radius:15px;overflow:hidden}
.p2-ref-track i{background:#0B9A9F;display:block;height:100%;border-radius:15px}
.p2-ref-pair{border-bottom:1px solid #EDF1F4;padding:11px 0;display:flex;gap:9px;
 align-items:flex-start;justify-content:space-between;font-size:11.5px}
.p2-ref-pair span{color:#758C9F;max-width:55%}
.p2-ref-pair b{text-align:right;color:#294557;font-size:11.3px;max-width:65%;overflow-wrap:anywhere}
.p2-ref-note{padding:13px 16px;border-radius:10px;border:1px solid #E5EFF3;background:#F7FAFC;
 font-size:11px;color:#516B7D;margin-top:20px}
.p2-ref-note strong{display:block;color:#233E50;margin-bottom:5px;font-size:11px}
.p2-ref-causal{display:grid;gap:10px}
.p2-ref-causal>div{display:flex;align-items:flex-start;gap:11px;padding:12px;
 border:1px solid #E2EAEE;background:#fff;border-radius:10px}
.p2-ref-causal b{width:27px;height:27px;border-radius:8px;background:#E4F6F3;
 color:#087B82;display:grid;place-items:center;font-size:10px}
.p2-ref-causal span{display:flex;flex-direction:column;gap:5px}
.p2-ref-causal strong{font-size:11px;color:#264354}
.p2-ref-causal small{font-size:10px;color:#859BA8}
.p2-ref-route{display:grid;gap:6px;margin:2px 0}
.p2-ref-route-row{display:flex;align-items:flex-start;gap:12px;border:1px solid #E3EBF0;
 border-radius:10px;background:white;padding:10px 12px;margin:5px 0}
.p2-ref-route-row b{width:28px;height:28px;flex:0 0 28px;display:grid;place-items:center;
 color:#0B8F94;background:#E6F7F5;border-radius:9px;font-size:10px}
.p2-ref-route-row div{display:flex;flex-direction:column;gap:4px}
.p2-ref-route-row strong{font-size:11.3px;color:#29485B}
.p2-ref-route-row small{font-size:10px;color:#8596A2}
.p2-ref-progress-title{font-size:10.6px;font-weight:750;color:#647C8C;margin:14px 0 7px}
.p2-ref-need-card{border:1px solid #E2EAEF;border-radius:12px;background:#fff;
 min-height:205px;padding:13px;margin-bottom:12px;font-size:10.8px;color:#28495B}
.p2-ref-need-title{display:flex;justify-content:space-between;align-items:center;
 border-bottom:1px solid #ECF1F4;margin:-3px 0 9px;padding-bottom:9px}
.p2-ref-need-title span{background:#E9F7F3;border-radius:20px;padding:4px 7px;color:#187D75;font-size:9.4px}
.p2-ref-pain,.p2-ref-gain{margin:9px 0;border-radius:8px;padding:10px;font-size:10.5px;line-height:1.5}
.p2-ref-pain{background:#FFF7F1;border:1px solid #F9E2CD;color:#77533D}
.p2-ref-gain{background:#EDFAF6;border:1px solid #D4EFE7;color:#275F52}
.p2-ref-pain small,.p2-ref-gain small{display:block;font-size:9px;letter-spacing:.7px;
 font-weight:850;margin-bottom:5px;color:inherit}
.p2-ref-need-footer{font-size:10px;color:#8B9AA6;margin-top:8px}
.p2-ref-steps{display:grid;gap:7px;margin:6px 0 10px}
.p2-ref-steps span{border:1px solid #E6EEF2;background:#FAFCFD;border-radius:8px;padding:9px 13px;
 color:#476779;font-size:11px;font-weight:750}
.p2-ref-engine-steps{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:12px;
 margin:9px 0 20px}
.p2-ref-engine-steps>div{display:flex;flex-direction:column;align-items:center;gap:6px;
 color:#728A9B;font-size:10px}
.p2-ref-engine-steps b{height:38px;width:38px;display:grid;place-items:center;
 background:#F1FAF8;border:1px solid #C8EBE5;color:#0E8586;border-radius:10px}
.p2-ref-engine-steps small{font-size:10px;text-align:center}
.p2-ref-table-scroll{overflow:auto;border:1px solid #E4ECF1;border-radius:11px;margin:10px 0 16px}
.p2-ref-table{width:100%;border-collapse:collapse;font-size:10.4px;white-space:nowrap}
.p2-ref-table td,.p2-ref-table th{border:1px solid #E4EDF1;padding:10px;text-align:center}
.p2-ref-table th{background:#F5F8FA;color:#597385;font-weight:800}
.p2-ref-table th small{display:block;color:#8199A7;margin-top:3px;white-space:normal;max-width:175px}
.p2-ref-table th:first-child{text-align:left}
.p2-ref-footer{margin:18px 0;border-radius:13px;background:linear-gradient(110deg,#123F54,#226E76);
 padding:20px 24px;color:white}
.p2-ref-footer small{color:#8CE0D9;letter-spacing:1.2px;font-weight:850}
.p2-ref-footer h3{color:white;margin:6px 0 8px;font-size:17px}
.p2-ref-footer p{color:#DBF0EE;font-size:11.4px;line-height:1.6}
@media(max-width:1000px){.p2-ref-engine-steps{grid-template-columns:repeat(3,minmax(0,1fr))}}
@media(max-width:640px){.p2-ref-bar-row{grid-template-columns:minmax(90px,1.4fr) minmax(60px,1fr) 45px;gap:6px}
.p2-ref-engine-steps{grid-template-columns:repeat(3,minmax(0,1fr))}}

.p2-ref-ranked{display:flex;gap:9px;align-items:center;padding:7px 3px;color:#29495B}
.p2-ref-ranked>b{height:27px;flex:0 0 27px;width:27px;background:#DFF3F2;color:#087D83;
 display:grid;place-items:center;border-radius:8px;font-size:11px}
.p2-ref-ranked span{font-size:10.5px;font-weight:750;line-height:1.3;overflow-wrap:anywhere}
.p2-ref-ranked small{display:block;color:#92A2AC;font-size:9.5px;font-weight:500;margin-top:4px}
</style>
"""


def apply_step2_theme():
    st.markdown(STYLES, unsafe_allow_html=True)
    # The legacy V0.8 sheet loads first; visual V0.9 tokens always win.
    from .design_system import apply_corporate_theme
    apply_corporate_theme()
