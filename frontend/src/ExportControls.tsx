import { useEffect, useId, useRef, useState } from "react";
import { messageOf } from "./api";
import { ErrorNotice } from "./components";
import { fetchExport, saveExport } from "./exports";
import type { ExportDataset, ExportFormat, ExportOptions } from "./exports";

interface Props { dataset: ExportDataset; filters?: Omit<ExportOptions, "format" | "date_from" | "date_to" | "include_contacts">; title?: string }

export function ExportControls({ dataset, filters = {}, title = "Выгрузка для аналитики" }: Props) {
  const id = useId();
  const [format, setFormat] = useState<ExportFormat>("xlsx");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [contacts, setContacts] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);
  const download = async () => {
    if (controller.current) return;
    setError(""); setSuccess("");
    if (from && to && from > to) { setError("Начало периода должно быть не позже окончания."); return; }
    const request = new AbortController();
    controller.current = request; setBusy(true);
    try {
      const file = await fetchExport(dataset, { ...filters, format, date_from: from, date_to: to, include_contacts: contacts }, request.signal);
      if (request.signal.aborted) return;
      saveExport(file.blob, file.filename);
      setSuccess(`Файл «${file.filename}» готов к скачиванию.`);
    } catch (problem) { if (!request.signal.aborted) setError(messageOf(problem)); }
    finally { if (!request.signal.aborted) setBusy(false); controller.current = null; }
  };
  const allowContacts = ["orders", "users", "all"].includes(dataset);
  return <section className="admin-export" aria-labelledby={`${id}-title`} aria-busy={busy}>
    <div className="admin-export-heading"><div><h2 id={`${id}-title`}>{title}</h2><p className="form-note">Все записи по текущим фильтрам, со всех страниц.{allowContacts && !contacts ? " Без контактов покупателей." : ""}</p></div><button type="button" className="button outline" disabled={busy} onClick={() => void download()}>{busy ? "Готовим файл…" : dataset === "all" ? "Скачать все данные" : "Скачать файл"}</button></div>
    <details className="admin-export-options"><summary>Параметры выгрузки · {format === "xlsx" ? "Excel" : "CSV"}{from || to ? " · период задан" : " · весь период"}{contacts ? " · с контактами" : ""}</summary>
    <div className="admin-export-fields">
      <label className="field"><span>Формат</span><select value={format} disabled={busy} onChange={(event) => setFormat(event.target.value as ExportFormat)}><option value="xlsx">Excel (.xlsx)</option><option value="csv">{["orders", "all"].includes(dataset) ? "CSV в ZIP" : "CSV"}</option></select></label>
      <label className="field"><span>С даты</span><input type="date" value={from} max={to || undefined} disabled={busy} onChange={(event) => setFrom(event.target.value)} /></label>
      <label className="field"><span>По дату включительно</span><input type="date" value={to} min={from || undefined} disabled={busy} onChange={(event) => setTo(event.target.value)} /></label>
    </div>
    {allowContacts && <label className="admin-checkbox admin-export-contacts"><input type="checkbox" checked={contacts} disabled={busy} onChange={(event) => setContacts(event.target.checked)} /> Включить контакты покупателей</label>}
    {allowContacts && contacts && <p className="form-note" id={`${id}-contacts-note`}>Файл будет содержать персональные данные покупателей. Храните его с ограниченным доступом и передавайте только для заявленной цели.</p>}
    </details>
    <ErrorNotice message={error} />{success && <p className="form-note" role="status">{success}</p>}
  </section>;
}
