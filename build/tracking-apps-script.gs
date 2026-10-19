// Google Apps Script for the share-tracking sheet.
// Setup: script.google.com → New project → paste this → Deploy → New deployment →
// type "Web app", Execute as "Me", Who has access "Anyone" → copy the Web app URL into track.js.
// Write-only: there is no doGet, so the sheet's contents are not readable through the URL.

const SHEET_ID = '1-dRZvxqxwDJO-QNSoYtDoEm6Ep7SqK7RZkIBxYWLdoY'; // Drive: "שליחות StoliSki"
const COLUMNS = ['זמן', 'אירוע', 'דירה', 'נציג', 'מזהה קישור', 'עמוד', 'מכשיר'];

function doPost(e) {
  const sheet = SpreadsheetApp.openById(SHEET_ID).getSheets()[0];
  if (sheet.getLastRow() === 0) sheet.appendRow(COLUMNS);
  let d = {};
  try { d = JSON.parse(e.postData.contents); } catch (err) { return ContentService.createTextOutput('bad'); }
  const clip = v => String(v == null ? '' : v).slice(0, 60);
  sheet.appendRow([new Date(), clip(d.event), clip(d.apt), clip(d.agent), clip(d.s), clip(d.page), clip(d.device)]);
  return ContentService.createTextOutput('ok');
}
