"""V11 operational reporting helpers."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

import pandas as pd

def case_pdf(case_id: str, process: str, row, saved: dict, comments: pd.DataFrame, organization: str) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
    regular=Path(r"C:\Windows\Fonts\arial.ttf");bold=Path(r"C:\Windows\Fonts\arialbd.ttf");font="Helvetica";font_bold="Helvetica-Bold"
    if regular.exists():pdfmetrics.registerFont(TTFont("RiskArial",str(regular)));font="RiskArial"
    if bold.exists():pdfmetrics.registerFont(TTFont("RiskArialBold",str(bold)));font_bold="RiskArialBold"
    out=BytesIO();doc=SimpleDocTemplate(out,pagesize=A4,rightMargin=18*mm,leftMargin=18*mm,topMargin=17*mm,bottomMargin=17*mm,title=f"Vaka Raporu - {case_id}",author=organization)
    styles=getSampleStyleSheet();title=ParagraphStyle("title",parent=styles["Title"],fontName=font_bold,fontSize=19,textColor=colors.HexColor("#101828"),alignment=TA_CENTER,spaceAfter=12);h=ParagraphStyle("h",parent=styles["Heading2"],fontName=font_bold,fontSize=12,textColor=colors.HexColor("#175CD3"),spaceBefore=10,spaceAfter=6);body=ParagraphStyle("body",parent=styles["BodyText"],fontName=font,fontSize=9.2,leading=13,textColor=colors.HexColor("#344054"));small=ParagraphStyle("small",parent=body,fontSize=8,textColor=colors.HexColor("#667085"))
    story=[Paragraph(escape(organization),small),Paragraph("İç Kontrol Vaka Raporu",title)]
    status_labels={"Inceleniyor":"İnceleniyor","Musteri teyidi bekleniyor":"Müşteri teyidi bekleniyor","Risk dogrulandi":"Risk doğrulandı","Yanlis alarm":"Yanlış alarm","Kapatildi":"Kapatıldı"};risk_labels={"YUKSEK":"YÜKSEK","DUSUK":"DÜŞÜK","ORTA":"ORTA"}
    info=[["Vaka numarası",saved.get("case_number") or case_id],["Kayıt numarası",case_id],["Süreç",process],["Risk seviyesi",risk_labels.get(str(row.get("risk_level","-")),str(row.get("risk_level","-")))],["Risk skoru",f"{int(row.get('risk_score',0))}/100"],["Vaka durumu",status_labels.get(saved.get("status","Yeni"),saved.get("status","Yeni"))],["Öncelik",saved.get("priority") or "Orta"],["Son tamamlanma tarihi",saved.get("due_date") or "Belirlenmedi"],["İnceleyen",saved.get("analyst","") or "Atanmamış"],["Onaylayan",saved.get("reviewer","") or "Atanmamış"],["Atanan ekip",saved.get("assigned_team","") or saved.get("responsible_unit","") or "Atanmamış"]]
    table=Table(info,colWidths=[48*mm,112*mm]);table.setStyle(TableStyle([("BACKGROUND",(0,0),(0,-1),colors.HexColor("#EEF4FF")),("TEXTCOLOR",(0,0),(0,-1),colors.HexColor("#1849A9")),("FONTNAME",(0,0),(0,-1),font_bold),("FONTNAME",(1,0),(1,-1),font),("FONTSIZE",(0,0),(-1,-1),9),("GRID",(0,0),(-1,-1),.4,colors.HexColor("#D0D5DD")),("VALIGN",(0,0),(-1,-1),"TOP"),("LEFTPADDING",(0,0),(-1,-1),7),("TOPPADDING",(0,0),(-1,-1),6),("BOTTOMPADDING",(0,0),(-1,-1),6)]));story += [table,Spacer(1,7*mm)]
    sections=[("Risk gerekçeleri",row.get("risk_reasons","-")),("Önerilen kontrol aksiyonları",row.get("recommended_actions","-")),("İnceleme notu",saved.get("review_note","") or "Henüz inceleme notu girilmedi."),("Alınan aksiyon",saved.get("action_taken","") or "Henüz aksiyon kaydedilmedi."),("Kanıt açıklaması",saved.get("evidence_note","") or "Henüz kanıt açıklaması girilmedi.")]
    for label,value in sections:story.extend([Paragraph(escape(label),h),Paragraph(escape(str(value)).replace(" | ","<br/>"),body)])
    story.append(Paragraph("Yorum geçmişi",h))
    if comments.empty:story.append(Paragraph("Henüz yorum bulunmuyor.",body))
    else:
        for _,item in comments.sort_values("created_at").iterrows():story.append(Paragraph(f"<b>{escape(str(item['created_by']))}</b> · {escape(str(item['created_at']))}<br/>{escape(str(item['comment']))}",body));story.append(Spacer(1,3*mm))
    def footer(canvas,document):
        canvas.saveState();canvas.setFont(font,8);canvas.setFillColor(colors.HexColor("#667085"));canvas.drawString(18*mm,9*mm,"Yetkili kontrol personeli tarafından doğrulanmalıdır.");canvas.drawRightString(192*mm,9*mm,f"Sayfa {document.page}");canvas.restoreState()
    doc.build(story,onFirstPage=footer,onLaterPages=footer);return out.getvalue()

def sla_notifications(data: pd.DataFrame, date_col: str, rules: dict) -> pd.DataFrame:
    if data.empty:return pd.DataFrame()
    now=pd.Timestamp.now();dates=pd.to_datetime(data[date_col],errors="coerce");age=(now-dates).dt.total_seconds()/3600;limit=data.risk_level.map({"YUKSEK":rules["high_sla_hours"],"ORTA":rules["medium_sla_hours"]}).fillna(999999);remaining=limit-age
    if "due_date" in data:
        due=pd.to_datetime(data["due_date"],errors="coerce")+pd.Timedelta(hours=23,minutes=59);due_remaining=(due-now).dt.total_seconds()/3600;remaining=due_remaining.where(due.notna(),remaining)
    open_mask=~data.case_status.isin(["Kapatildi","Yanlis alarm","Risk dogrulandi"])
    alert_mask = open_mask & remaining.le(12)
    fields = [c for c in ["risk_level", "risk_score", "case_status"] if c in data]
    result = data.loc[alert_mask, fields].copy()
    hours = remaining.loc[alert_mask]
    result["Kalan saat"] = hours
    result["Bildirim"] = hours.map(lambda value: "SLA aşıldı" if value < 0 else "SLA yaklaşıyor")
    return result
