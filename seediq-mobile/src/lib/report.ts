// Android-compatible AI report generation — mirrors the web ReportModal/PDF
// feature using expo-print (HTML → PDF) + the native Android share sheet
// (view / share / save to Drive or Files). All content comes from real backend
// responses — nothing is fabricated here.

import { Platform } from "react-native";
import * as Print from "expo-print";
import * as Sharing from "expo-sharing";
import { getActiveLanguage, translate, type LanguageCode } from "../i18n";

// Locale used for the report timestamp, following the selected language.
const REPORT_LOCALES: Record<LanguageCode, string> = {
  en: "en-IN",
  kn: "kn-IN",
  hi: "hi-IN",
};

export interface ReportParameter {
  label: string;
  value: string;
  status?: "ok" | "warning" | "danger";
}

export interface ReportModelResult {
  model: string;
  prediction: string;
  note?: string;
}

export interface ReportAdvisory {
  title: string;
  desc: string;
  priority?: string;
}

export interface ReportData {
  title: string;
  domain: string;
  primaryResult: {
    label: string;
    value: string;
    subtext?: string;
  };
  parameters?: ReportParameter[];
  models?: ReportModelResult[];
  advisories?: ReportAdvisory[];
  summaryNotes?: string;
}

function esc(v: unknown): string {
  return String(v ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// Client brand palette (FOREST / PINE / TEAL / SAGE / MINT).
const GREEN = "#235347";
const DARK = "#0B2B26";
const MUTED = "#4C7A69";
const BORDER = "#B4D9C0";
const WARN = "#8A6A12";
const DANGER = "#A33A22";

function statusColor(status?: ReportParameter["status"]): string {
  if (status === "danger") return DANGER;
  if (status === "warning") return WARN;
  if (status === "ok") return GREEN;
  return DARK;
}

export function renderReportHtml(report: ReportData, operator?: string): string {
  const locale = REPORT_LOCALES[getActiveLanguage()] ?? "en-IN";
  const generatedAt = new Date().toLocaleString(locale, { dateStyle: "full", timeStyle: "medium" });
  // The report ID prefix stays ASCII regardless of the display language.
  const domainCode = report.domain.replace(/[^A-Za-z]/g, "").toUpperCase().slice(0, 6) || "GEN";
  const reportId = `SIQ-${domainCode}-${Date.now().toString(36).toUpperCase()}`;

  const paramRows = (report.parameters || [])
    .map(
      (p) => `<tr>
        <td class="lbl">${esc(p.label)}</td>
        <td class="val" style="color:${statusColor(p.status)}">${esc(p.value)}</td>
      </tr>`
    )
    .join("");

  const modelRows = (report.models || [])
    .map(
      (m) => `<tr>
        <td class="lbl">${esc(m.model)}${m.note ? `<div class="note">${esc(m.note)}</div>` : ""}</td>
        <td class="val">${esc(m.prediction)}</td>
      </tr>`
    )
    .join("");

  const advisories = (report.advisories || [])
    .map(
      (a) => `<div class="advisory">
        <div class="advisory-head">
          <span class="advisory-title">${esc(a.title)}</span>
          ${a.priority ? `<span class="advisory-priority">${esc(a.priority)}</span>` : ""}
        </div>
        <div class="advisory-desc">${esc(a.desc)}</div>
      </div>`
    )
    .join("");

  return `<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, "Roboto", "Helvetica Neue", Arial, sans-serif;
    background: #DAF1DE; color: ${DARK}; padding: 40px 32px; line-height: 1.5;
  }
  .brand { display: flex; align-items: baseline; gap: 10px; border-bottom: 3px solid ${GREEN}; padding-bottom: 14px; }
  .brand-name { font-size: 24px; font-weight: 800; color: ${GREEN}; letter-spacing: -0.5px; }
  .brand-tag { font-size: 12px; color: ${MUTED}; }
  .meta { display: flex; flex-wrap: wrap; gap: 6px 24px; margin: 14px 0 26px; font-size: 11px; color: ${MUTED}; }
  h1 { font-size: 19px; font-weight: 700; margin-bottom: 4px; }
  .domain { font-size: 12px; text-transform: uppercase; letter-spacing: 1.5px; color: ${GREEN}; font-weight: 700; margin-bottom: 18px; }
  .primary {
    border: 1px solid ${BORDER}; border-left: 4px solid ${GREEN}; border-radius: 8px;
    padding: 20px; margin-bottom: 26px; background: #C8E6D1;
  }
  .primary .plabel { font-size: 11px; text-transform: uppercase; letter-spacing: 1px; color: ${MUTED}; }
  .primary .pvalue { font-size: 30px; font-weight: 800; color: ${GREEN}; margin-top: 2px; }
  .primary .psub { font-size: 12px; color: ${MUTED}; margin-top: 4px; }
  h2 { font-size: 13px; text-transform: uppercase; letter-spacing: 1px; color: ${DARK}; margin: 24px 0 10px; }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  td { padding: 8px 6px; border-bottom: 1px solid ${BORDER}; vertical-align: top; }
  .lbl { color: ${MUTED}; }
  .val { text-align: right; font-weight: 700; white-space: pre-wrap; }
  .note { font-weight: 400; font-size: 11px; color: ${MUTED}; }
  .advisory { border: 1px solid ${BORDER}; border-radius: 8px; padding: 12px 14px; margin-bottom: 10px; }
  .advisory-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }
  .advisory-title { font-weight: 700; font-size: 13px; }
  .advisory-priority { font-size: 10px; font-weight: 700; text-transform: uppercase; color: ${GREEN}; border: 1px solid ${GREEN}; border-radius: 999px; padding: 2px 8px; }
  .advisory-desc { font-size: 12px; color: ${MUTED}; }
  .notes { font-size: 12px; color: ${MUTED}; margin-top: 18px; }
  .footer { margin-top: 34px; border-top: 1px solid ${BORDER}; padding-top: 12px; font-size: 10px; color: ${MUTED}; }
  @media print { body { padding: 0; } }
</style>
</head>
<body>
  <div class="brand">
    <span class="brand-name">SeedIQ</span>
    <span class="brand-tag">${esc(translate("app.operatingTagline"))}</span>
  </div>
  <div class="meta">
    <span>${esc(translate("report.reportId", { value: reportId }))}</span>
    <span>${esc(translate("report.generated", { value: generatedAt }))}</span>
    ${operator ? `<span>${esc(translate("report.operator", { value: operator }))}</span>` : ""}
  </div>

  <div class="domain">${esc(report.domain)}</div>
  <h1>${esc(report.title)}</h1>

  <div class="primary">
    <div class="plabel">${esc(report.primaryResult.label)}</div>
    <div class="pvalue">${esc(report.primaryResult.value)}</div>
    ${report.primaryResult.subtext ? `<div class="psub">${esc(report.primaryResult.subtext)}</div>` : ""}
  </div>

  ${report.parameters?.length ? `<h2>${esc(translate("report.inputParameters"))}</h2><table>${paramRows}</table>` : ""}
  ${report.models?.length ? `<h2>${esc(translate("report.modelPredictions"))}</h2><table>${modelRows}</table>` : ""}
  ${report.advisories?.length ? `<h2>${esc(translate("report.advisories"))}</h2>${advisories}` : ""}
  ${report.summaryNotes ? `<div class="notes">${esc(report.summaryNotes)}</div>` : ""}

  <div class="footer">
    ${esc(translate("report.footer"))}
  </div>
</body>
</html>`;
}

export type ReportShareOutcome = "shared" | "printed" | "unavailable";

/**
 * Render the report to PDF and open the Android share sheet
 * (view / share / save to Drive, Files, printer…). Falls back to the
 * system print dialog if no share target is available.
 */
export async function shareReportPdf(report: ReportData, operator?: string): Promise<ReportShareOutcome> {
  const html = renderReportHtml(report, operator);
  const { uri } = await Print.printToFileAsync({ html, base64: false });

  if (await Sharing.isAvailableAsync()) {
    await Sharing.shareAsync(uri, {
      mimeType: "application/pdf",
      dialogTitle: report.title,
      UTI: "com.adobe.pdf",
    });
    return "shared";
  }

  if (Platform.OS === "android" || Platform.OS === "ios") {
    await Print.printAsync({ html });
    return "printed";
  }
  return "unavailable";
}
