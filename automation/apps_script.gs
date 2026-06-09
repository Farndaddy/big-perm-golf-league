// ============================================================
// BIG PERM GOLF LEAGUE — Google Apps Script
// Paste this entire file into Tools > Apps Script in your sheet.
// Then deploy as a Web App (see SETUP.md for instructions).
// ============================================================

// ── Sheet & Player Config ────────────────────────────────────
const PLAYERS = ['Farnia', 'Owens', 'Felter', 'Carter', 'Lorenz'];

// Playing handicaps — update these when CDGA handicaps change
const PLAYING_HC = {
  Farnia: 19,
  Owens:  12,
  Felter: 18,
  Carter: 16,
  Lorenz: 14
};

// Hole handicap difficulty ratings (1=hardest, 18=easiest)
const HOLE_HC = [11,7,9,3,5,17,1,13,15,16,2,10,12,6,14,4,18,8];

// Par per hole
const HOLE_PAR = [4,4,4,4,4,3,5,4,3,4,3,4,4,4,4,5,3,4];


// ── Web App Entry Point ──────────────────────────────────────
// This is called by the Python script via HTTP POST.
function doPost(e) {
  try {
    const data = JSON.parse(e.postData.contents);
    const result = processRoundData(data);
    return ContentService
      .createTextOutput(JSON.stringify({ success: true, message: result }))
      .setMimeType(ContentService.MimeType.JSON);
  } catch (err) {
    return ContentService
      .createTextOutput(JSON.stringify({ success: false, error: err.toString() }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}

// ── Main processing function ─────────────────────────────────
// Call this manually from the Apps Script editor to test:
// processRoundData({ date: "May 31", scores: { Farnia: [4,5,...], Owens: [3,4,...], ... } })
function processRoundData(data) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const date = data.date;              // e.g. "May 31"
  const scores = data.scores;          // { Farnia: [h1,h2,...,h18], Owens: [...], ... }
  const hcOverrides = data.playing_hc || {};  // playing (course) handicaps from GHIN screenshot
  const hcIndices   = data.hc_index   || {};  // CDGA handicap indices (for reference)

  const log = [];

  // Calculate net scores for each player
  const netScores = {};
  PLAYERS.forEach(player => {
    if (!scores[player]) return;
    const hc = hcOverrides[player] || PLAYING_HC[player];
    const grossHoles = scores[player];
    const netHoles = calcNetHoles(grossHoles, hc);
    const grossTotal = grossHoles.reduce((a, b) => a + b, 0);
    const netTotal = netHoles.reduce((a, b) => a + b, 0);
    netScores[player] = {
      grossHoles,
      netHoles,
      grossTotal,
      netTotal,
      hc
    };
  });

  // Update each tab
  log.push(updateLeaderboard(ss, date, netScores));
  log.push(updateWeeklyScorecard(ss, date, netScores, hcOverrides));
  log.push(updateScheduleTracker(ss, date, scores));

  return log.join(' | ');
}

// ── Net score calculator ─────────────────────────────────────
function calcNetHoles(grossHoles, hc) {
  const strokes = new Array(18).fill(0);
  // First pass: 1 stroke on holes ranked 1..min(hc,18)
  for (let i = 0; i < 18; i++) {
    if (HOLE_HC[i] <= Math.min(hc, 18)) strokes[i]++;
  }
  // Second pass: extra stroke if hc > 18 (on hole ranked 1)
  if (hc > 18) {
    const extraHoles = hc - 18;
    for (let i = 0; i < 18; i++) {
      if (HOLE_HC[i] <= extraHoles) strokes[i]++;
    }
  }
  return grossHoles.map((g, i) => g - strokes[i]);
}

// ── Update Leaderboard tab ───────────────────────────────────
function updateLeaderboard(ss, date, netScores) {
  const sheet = ss.getSheetByName('Leaderboard');
  if (!sheet) return 'Leaderboard tab not found';

  // Find header row to determine player column order
  const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  const playerCols = {};
  headers.forEach((h, i) => {
    const name = h.toString().trim();
    if (PLAYERS.includes(name)) playerCols[name] = i + 1; // 1-indexed
  });

  // Find next empty row (after header rows)
  const lastRow = sheet.getLastRow();
  const newRow = lastRow + 1;

  // Write date in column A
  sheet.getRange(newRow, 1).setValue(date);

  // Write net scores for each player
  PLAYERS.forEach(player => {
    if (!playerCols[player]) return;
    const col = playerCols[player];
    if (netScores[player]) {
      sheet.getRange(newRow, col).setValue(netScores[player].netTotal);
    } else {
      sheet.getRange(newRow, col).setValue('---');
    }
  });

  return `Leaderboard: wrote row ${newRow} for ${date}`;
}

// ── Update Weekly Scorecard tab ──────────────────────────────
// hcOverrides = playing handicaps from GHIN screenshot (course handicap)
function updateWeeklyScorecard(ss, date, netScores, hcOverrides) {
  const sheet = ss.getSheetByName('Weekly Scorecard');
  if (!sheet) return 'Weekly Scorecard tab not found';

  // Use live GHIN playing HC if provided, otherwise fall back to hardcoded values
  const getPlayingHC = (player) => hcOverrides[player] ?? PLAYING_HC[player];

  let nextRow = sheet.getLastRow() + 1;

  PLAYERS.forEach(player => {
    const playingHC = getPlayingHC(player);
    if (!netScores[player]) {
      // Player did not play — write DNS row with their current playing HC
      const row = [date, player, ...new Array(18).fill('---'), '---', playingHC, '---'];
      sheet.getRange(nextRow, 1, 1, row.length).setValues([row]);
    } else {
      const { grossHoles, grossTotal, netTotal } = netScores[player];
      // Column V = playing (course) handicap from GHIN — this is the correct value
      const row = [date, player, ...grossHoles, grossTotal, playingHC, netTotal];
      sheet.getRange(nextRow, 1, 1, row.length).setValues([row]);
    }
    nextRow++;
  });

  return `Weekly Scorecard: wrote ${PLAYERS.length} rows for ${date}`;
}

// ── Update Schedule Tracker tab ──────────────────────────────
function updateScheduleTracker(ss, date, scores) {
  const sheet = ss.getSheetByName('Schedule Tracker');
  if (!sheet) return 'Schedule Tracker tab not found (skipped)';

  // Find the row for this date
  const col1 = sheet.getRange('A:A').getValues();
  let targetRow = -1;
  for (let i = 0; i < col1.length; i++) {
    const cellVal = col1[i][0].toString().trim();
    if (cellVal === date || cellVal.includes(date)) {
      targetRow = i + 1;
      break;
    }
  }
  if (targetRow === -1) return `Schedule Tracker: no row found for date "${date}" (skipped)`;

  // Find player columns from row 3 (header)
  const headers = sheet.getRange(3, 1, 1, sheet.getLastColumn()).getValues()[0];
  const playerCols = {};
  headers.forEach((h, i) => {
    const name = h.toString().trim();
    if (PLAYERS.includes(name)) playerCols[name] = i + 1;
  });

  PLAYERS.forEach(player => {
    if (!playerCols[player]) return;
    const status = scores[player] ? 'IN' : 'OUT';
    sheet.getRange(targetRow, playerCols[player]).setValue(status);
  });

  return `Schedule Tracker: updated row ${targetRow} for ${date}`;
}

// ── Manual test function ─────────────────────────────────────
// Run this from the Apps Script editor to test with fake data
function testWithSampleData() {
  const sampleData = {
    date: "May 31",
    scores: {
      Farnia: [5,6,5,5,5,4,7,4,4,4,5,4,5,4,4,6,4,5],
      Owens:  [4,4,6,6,5,3,5,4,3,4,5,5,4,4,5,5,3,4],
      Felter: [4,5,5,5,4,4,5,4,4,4,6,6,4,5,5,5,3,4],
      Carter: [4,5,4,5,6,4,6,5,5,3,6,4,5,6,4,5,5,4]
      // Lorenz: not included = DNS
    }
  };
  Logger.log(processRoundData(sampleData));
}
