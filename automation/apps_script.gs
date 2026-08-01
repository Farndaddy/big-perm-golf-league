// ============================================================
// BIG PERM GOLF LEAGUE — Google Apps Script (v2 — Full Rewrite)
// Paste this entire file into Extensions > Apps Script in your sheet.
// Then: Deploy > New Deployment > Web App
//   Execute as: Me
//   Who has access: Anyone
// Copy the new deployment URL into config.json → apps_script_url
// ============================================================

const PLAYERS  = ['Farnia', 'Owens', 'Felter', 'Carter', 'Lorenz'];
const HOLE_HC  = [11,5,9,7,1,17,3,13,15,16,2,4,10,8,12,6,18,14];  // corrected Jul 12 from scorecard
const HOLE_PAR = [4,4,4,4,4,3,5,4,3,3,4,4,4,4,4,5,3,4];          // par 70: H10=3, H11=4

// Month abbreviation to full name  ("Jun" → "June")
const MONTH_FULL = {
  Jan:'January', Feb:'February', Mar:'March',    Apr:'April',
  May:'May',     Jun:'June',     Jul:'July',      Aug:'August',
  Sep:'September', Oct:'October', Nov:'November', Dec:'December'
};

// Month abbreviation to 0-indexed number for JS Date comparison
const MONTH_NUM = {
  Jan:0, Feb:1, Mar:2, Apr:3, May:4,  Jun:5,
  Jul:6, Aug:7, Sep:8, Oct:9, Nov:10, Dec:11
};

// "Jun 14" → "June 14"
function expandDate(d) {
  return d.replace(/^([A-Za-z]+)/, function(m) { return MONTH_FULL[m] || m; });
}

// Check if a cell value matches a target date.
// Handles both Date objects (from Google Sheets date cells) and text strings.
function cellMatchesDate(cellVal, targetMonth, targetDay, longDate) {
  if (!cellVal && cellVal !== 0) return false;
  if (cellVal instanceof Date) {
    return cellVal.getMonth() === targetMonth && cellVal.getDate() === targetDay;
  }
  return cellVal.toString().trim() === longDate;
}


// ── Web App Entry Points ─────────────────────────────────────

// GET: return schedule attendance data as JSON
// Usage: fetch(APPS_SCRIPT_URL + '?action=schedule')
function doGet(e) {
  try {
    var action = (e && e.parameter && e.parameter.action) ? e.parameter.action : 'schedule';
    if (action === 'schedule') {
      var ss = SpreadsheetApp.getActiveSpreadsheet();
      var ws = ss.getSheetByName('Schedule Tracker');
      if (!ws) throw new Error('Schedule Tracker tab not found');
      var lastRow = ws.getLastRow();
      // Column order in sheet: Date(1), Count(2), Farnia(3), Owens(4), Carter(5), Felter(6), Lorenz(7), Extras(8)
      var data = ws.getRange(3, 1, lastRow - 2, 8).getValues();
      var rows = [];
      for (var i = 0; i < data.length; i++) {
        var row = data[i];
        var dateVal = row[0];
        if (!dateVal || !(dateVal instanceof Date)) continue;
        var m = dateVal.getMonth(); // 0-indexed
        var d = dateVal.getDate();
        var MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
        var dateStr = MONTHS[m] + ' ' + d;
        var farnia = row[2] ? row[2].toString() : null;
        var owens  = row[3] ? row[3].toString() : null;
        var carter = row[4] ? row[4].toString() : null;
        var felter = row[5] ? row[5].toString() : null;
        var lorenz = row[6] ? row[6].toString() : null;
        var extras = row[7] ? row[7].toString() : '';
        // Infer 'Avail' from Extras column when attendance is null
        if (!farnia && extras.toLowerCase().indexOf('farn') >= 0) farnia = 'Avail';
        if (!owens  && extras.toLowerCase().indexOf('owens') >= 0) owens = 'Avail';
        if (!felter && extras.toLowerCase().indexOf('felter') >= 0) felter = 'Avail';
        if (!carter && extras.toLowerCase().indexOf('carter') >= 0) carter = 'Avail';
        if (!lorenz && extras.toLowerCase().indexOf('lorenz') >= 0) lorenz = 'Avail';
        // Site order: Farnia, Owens, Felter, Carter, Lorenz
        rows.push({
          date: dateStr,
          att: [farnia || 'TBD', owens || 'TBD', felter || 'TBD', carter || 'TBD', lorenz || 'TBD']
        });
      }
      return ContentService
        .createTextOutput(JSON.stringify({ success: true, schedule: rows }))
        .setMimeType(ContentService.MimeType.JSON);
    }
    return ContentService
      .createTextOutput(JSON.stringify({ success: false, error: 'Unknown action' }))
      .setMimeType(ContentService.MimeType.JSON);
  } catch (err) {
    return ContentService
      .createTextOutput(JSON.stringify({ success: false, error: err.toString() }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}

function doPost(e) {
  try {
    var data   = JSON.parse(e.postData.contents);
    var result = processRoundData(data);
    return ContentService
      .createTextOutput(JSON.stringify({ success: true, message: result }))
      .setMimeType(ContentService.MimeType.JSON);
  } catch (err) {
    return ContentService
      .createTextOutput(JSON.stringify({ success: false, error: err.toString() }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}


// ── Main Processing ──────────────────────────────────────────
function processRoundData(data) {
  var ss         = SpreadsheetApp.getActiveSpreadsheet();
  var rawDate    = data.date;           // "Jun 14"
  var scores     = data.scores;         // { Farnia: [h1..h18], ... }
  var hcOverride = data.playing_hc || {};
  var hcIndex    = data.hc_index   || {};

  // Fallback playing HC — updated to Jul 12 2026 values
  var FALLBACK_HC = { Farnia:16, Owens:12, Felter:18, Carter:13, Lorenz:13 };
  function getHC(p) { return hcOverride[p] || FALLBACK_HC[p] || 16; }

  // Calculate gross + net per player
  var calc = {};
  PLAYERS.forEach(function(player) {
    if (!scores[player]) return;
    var hc    = getHC(player);
    var gross = scores[player];
    var net   = calcNetHoles(gross, hc);
    calc[player] = {
      gross:      gross,
      net:        net,
      grossTotal: gross.reduce(function(a,b){return a+b;}, 0),
      netTotal:   net.reduce(function(a,b){return a+b;}, 0),
      hc:         hc
    };
  });

  var log = [];
  log.push(updateLeaderboard(ss, rawDate, calc));
  log.push(updateWeeklyScorecard(ss, rawDate, calc));
  log.push(updateScheduleTracker(ss, rawDate, scores));
  PLAYERS.forEach(function(player) {
    try {
      log.push(updatePlayerTab(ss, player, rawDate, calc[player] || null));
    } catch(err) {
      log.push(player + ' tab error: ' + err.toString());
    }
  });

  return log.join(' | ');
}


// ── Net Score Calculator ─────────────────────────────────────
function calcNetHoles(gross, hc) {
  var s = new Array(18).fill(0);
  for (var i = 0; i < 18; i++) if (HOLE_HC[i] <= Math.min(hc, 18)) s[i]++;
  if (hc > 18) for (var i = 0; i < 18; i++) if (HOLE_HC[i] <= hc - 18) s[i]++;
  return gross.map(function(g, i) { return g - s[i]; });
}


// ── 1. LEADERBOARD TAB ───────────────────────────────────────
// Row 2  = header:  blank | Farnia | Felter | Owens | Carter | Lorenz
// Rows 3-22 = pre-built date rows: "April 26", "May 3", ...
// DO NOT touch rows 23+ (Total, Top 8 Avg, etc.)
// Action: find the row whose col A = date, write each player's net total
function updateLeaderboard(ss, rawDate, calc) {
  var sheet = ss.getSheetByName('Leaderboard');
  if (!sheet) return 'Leaderboard: tab not found';

  var longDate    = expandDate(rawDate);
  var parts       = rawDate.split(' ');
  var targetMonth = MONTH_NUM[parts[0]];
  var targetDay   = parseInt(parts[1]);

  // Read player columns from header row 2
  var headers    = sheet.getRange(2, 1, 1, sheet.getLastColumn()).getValues()[0];
  var playerCols = {};
  headers.forEach(function(h, i) {
    var n = h.toString().trim();
    if (PLAYERS.indexOf(n) >= 0) playerCols[n] = i + 1;
  });

  // Find date row in rows 3-22
  var colA      = sheet.getRange(3, 1, 20, 1).getValues();
  var targetRow = -1;
  for (var i = 0; i < colA.length; i++) {
    if (cellMatchesDate(colA[i][0], targetMonth, targetDay, longDate)) {
      targetRow = i + 3;
      break;
    }
  }
  if (targetRow === -1) return 'Leaderboard: no row found for "' + longDate + '"';

  // Write net totals
  PLAYERS.forEach(function(player) {
    if (!playerCols[player]) return;
    if (calc[player]) {
      sheet.getRange(targetRow, playerCols[player]).setValue(calc[player].netTotal);
    }
    // DNS: leave blank
  });

  return 'Leaderboard: row ' + targetRow + ' updated (' + longDate + ')';
}


// ── 2. WEEKLY SCORECARD TAB ───────────────────────────────────
// Row 5 = header: Date | Player/Hole | 1 | 2 | ... | 18 | Total | HC | Net
// Pre-built rows (5 players per date + 1 blank spacer):
//   Col A = date text only on the first player's row ("June 14")
//   Col B = player name
//   Cols C-T (3-20) = H1-H18 gross
//   Col U  (21)     = gross total
//   Col V  (22)     = playing HC
//   Col W  (23)     = net total
// Action: find each player's row by date+name, fill in scores
function updateWeeklyScorecard(ss, rawDate, calc) {
  var sheet = ss.getSheetByName('Weekly Scorecard');
  if (!sheet) return 'Weekly Scorecard: tab not found';

  var longDate    = expandDate(rawDate);
  var parts       = rawDate.split(' ');
  var targetMonth = MONTH_NUM[parts[0]];
  var targetDay   = parseInt(parts[1]);

  var lastRow = sheet.getLastRow();
  var abCols  = sheet.getRange(1, 1, lastRow, 2).getValues();

  // Find the block start: first row where col A matches our date
  var blockStart = -1;
  for (var i = 0; i < abCols.length; i++) {
    if (cellMatchesDate(abCols[i][0], targetMonth, targetDay, longDate)) {
      blockStart = i;
      break;
    }
  }
  if (blockStart === -1) return 'Weekly Scorecard: no block found for "' + longDate + '"';

  // Scan rows in this date block — stop at blank spacer row or new date
  var written = 0;
  for (var i = blockStart; i < abCols.length; i++) {
    var colAVal    = abCols[i][0] ? abCols[i][0].toString().trim() : '';
    var playerName = abCols[i][1] ? abCols[i][1].toString().trim() : '';

    // A new date appeared in col A — we've crossed into the next block
    if (i > blockStart && colAVal) break;
    // Col B is empty — blank spacer row, end of this date's block
    if (i > blockStart && !playerName) break;

    if (PLAYERS.indexOf(playerName) < 0) continue;
    if (!calc[playerName]) continue; // DNS — leave blank

    var c      = calc[playerName];
    var rowNum = i + 1; // 1-indexed

    sheet.getRange(rowNum, 3, 1, 18).setValues([c.gross]); // H1-H18
    sheet.getRange(rowNum, 21).setValue(c.grossTotal);      // Total
    sheet.getRange(rowNum, 22).setValue(c.hc);              // HC
    sheet.getRange(rowNum, 23).setValue(c.netTotal);        // Net
    written++;
  }

  return 'Weekly Scorecard: ' + written + ' players written for ' + longDate;
}


// ── 3. SCHEDULE TRACKER TAB ───────────────────────────────────
// Row 3 = header: Date | Confirmed Players | Farnia | Owens | Carter | Felter | Lorenz | Extras
// Rows 4-23 = date rows (col A stores actual Date values, displayed as m/d)
// Action: find the date row, write IN/OUT for each player
function updateScheduleTracker(ss, rawDate, scores) {
  var sheet = ss.getSheetByName('Schedule Tracker');
  if (!sheet) return 'Schedule Tracker: tab not found';

  var parts       = rawDate.split(' ');
  var targetMonth = MONTH_NUM[parts[0]];
  var targetDay   = parseInt(parts[1]);
  var longDate    = expandDate(rawDate);

  // Read player columns from header row 3
  var headers    = sheet.getRange(3, 1, 1, sheet.getLastColumn()).getValues()[0];
  var playerCols = {};
  headers.forEach(function(h, i) {
    var n = h.toString().trim();
    if (PLAYERS.indexOf(n) >= 0) playerCols[n] = i + 1;
  });

  // Find date row in rows 4-23
  var colA      = sheet.getRange(4, 1, 20, 1).getValues();
  var targetRow = -1;
  for (var i = 0; i < colA.length; i++) {
    if (cellMatchesDate(colA[i][0], targetMonth, targetDay, longDate)) {
      targetRow = i + 4;
      break;
    }
  }
  if (targetRow === -1) return 'Schedule Tracker: no row found for ' + rawDate;

  PLAYERS.forEach(function(player) {
    if (!playerCols[player]) return;
    var status = scores[player] ? 'IN' : 'OUT';
    sheet.getRange(targetRow, playerCols[player]).setValue(status);
  });

  return 'Schedule Tracker: row ' + targetRow + ' updated';
}


// ── 4. INDIVIDUAL PLAYER TABS ─────────────────────────────────
// Tab names: "Farnia", "Owens", "Felter", "Carter", "Lorenz"
// Structure:
//   Rows 1-6:  summary headers
//   Row 7:     gross header: Date | Player/Hole | 1–18 | Total
//   Rows 8-27: gross rows (one per round date)
//              Col A = date ("April 26" or Date object)
//              Col B = player name
//              Cols C-T (3-20) = H1-H18 gross scores
//              Col U  (21)     = gross total
//   Rows 28+:  stats + "Net Score w/Handicap" section
//              Header row contains "Net Score w/Handicap" in col A
//              Net rows below that header mirror the same dates as gross rows
//              Cols C-T (3-20) = per-hole net scores
//              Col U  (21)     = net total
// Action: find the gross row + net row for this date, fill in all values
function updatePlayerTab(ss, player, rawDate, c) {
  var sheet = ss.getSheetByName(player);
  if (!sheet) return player + ' tab: not found (skipped)';

  var longDate    = expandDate(rawDate);
  var parts       = rawDate.split(' ');
  var targetMonth = MONTH_NUM[parts[0]];
  var targetDay   = parseInt(parts[1]);

  // ── GROSS SECTION: scan rows 8-27 for the date in col A ─────
  var scanData  = sheet.getRange(8, 1, 20, 1).getValues();
  var grossRow  = -1;
  for (var i = 0; i < scanData.length; i++) {
    if (cellMatchesDate(scanData[i][0], targetMonth, targetDay, longDate)) {
      grossRow = i + 8;
      break;
    }
  }
  if (grossRow === -1) return player + ' tab: no gross row found for ' + longDate;
  if (!c) return player + ' tab: DNS — gross row ' + grossRow + ' left blank';

  // Write H1-H18 gross in cols C-T (3-20), total in col U (21)
  sheet.getRange(grossRow, 3, 1, 18).setValues([c.gross]);
  sheet.getRange(grossRow, 21).setValue(c.grossTotal);

  // ── NET SECTION: find "Net Score w/Handicap" header row ──────
  // Search from row 28 onward for the net section header
  var lastRow   = sheet.getLastRow();
  var searchLen = Math.min(lastRow - 27, 50);
  if (searchLen < 1) {
    return player + ' tab: gross row ' + grossRow + ' written (no net section found)';
  }
  var colAData     = sheet.getRange(28, 1, searchLen, 1).getValues();
  var netHeaderRow = -1;
  for (var i = 0; i < colAData.length; i++) {
    var v = colAData[i][0];
    if (v && v.toString().indexOf('Net Score') >= 0) {
      netHeaderRow = i + 28;
      break;
    }
  }
  if (netHeaderRow === -1) {
    return player + ' tab: gross row ' + grossRow + ' written (net header not found)';
  }

  // Search up to 25 rows below the header for the matching date
  var netScanLen  = Math.min(lastRow - netHeaderRow, 25);
  var netScanData = sheet.getRange(netHeaderRow + 1, 1, netScanLen, 1).getValues();
  var netRow      = -1;
  for (var i = 0; i < netScanData.length; i++) {
    if (cellMatchesDate(netScanData[i][0], targetMonth, targetDay, longDate)) {
      netRow = netHeaderRow + 1 + i;
      break;
    }
  }
  if (netRow === -1) {
    return player + ' tab: gross row ' + grossRow + ' written (net date row not found)';
  }

  // Write per-hole net scores (cols C-T) and net total (col U)
  sheet.getRange(netRow, 3, 1, 18).setValues([c.net]);
  sheet.getRange(netRow, 21).setValue(c.netTotal);

  return (player + ' tab: gross row ' + grossRow +
          ' + net row ' + netRow + ' written (' + longDate + ')');
}


// ── Manual Test ──────────────────────────────────────────────
// Run this from the Apps Script editor to verify all tabs update correctly.
// Go to Run menu → Run → testWithTodaysData
// Then check the Execution Log (View → Logs) for results.
function testWithTodaysData() {
  var data = {
    date: "Jun 14",
    playing_hc: { Farnia:18, Owens:13, Felter:19, Carter:16, Lorenz:15 },
    scores: {
      // Actual scores from 06-14-26 scorecards
      Farnia: [5,6,6,6,3,6,3,5,6, 4,5,7,5,5,5,2,6,5],  // gross 90, net 72
      Owens:  [5,6,5,5,5,4,6,4,3, 3,6,5,4,4,4,5,3,5],  // gross 82, net 69
      Felter: [5,6,5,6,7,4,5,4,4, 4,6,6,3,6,5,5,4,4],  // gross 89, net 70
      Lorenz: [3,6,7,6,5,4,6,4,3, 4,7,5,7,6,7,7,4,5]   // gross 96, net 81
      // Carter: DNS
    }
  };
  var result = processRoundData(data);
  Logger.log(result);
  console.log(result);
}

// ── Jul 5 Test ───────────────────────────────────────────────
// Run this to push Jul 5, 2026 scores directly into the sheet.
// Select "testJul5Data" from the function dropdown, then click Run.
// Check the Execution log below for success/error messages.
function testJul5Data() {
  var data = {
    date: "Jul 5",
    playing_hc: { Farnia:18, Felter:17, Lorenz:15 },
    hc_index:   { Farnia:16.2, Felter:15.9, Lorenz:13.0 },
    scores: {
      Farnia: [5,4,5,6,4,4,7,4,4, 4,5,5,5,5,4,7,5,6],  // gross 89, net 71
      Felter: [4,6,3,4,6,4,6,5,4, 4,5,5,6,5,4,6,4,6],  // gross 87, net 70
      Lorenz: [4,7,6,5,6,5,6,4,5, 4,5,4,5,5,7,6,3,4]   // gross 91, net 76
      // Carter, Owens: DNS
    }
  };
  var result = processRoundData(data);
  Logger.log(result);
  console.log(result);
  return result;
}

// ── Jul 12 Test (R12) ────────────────────────────────────────
// Run this to push Jul 12, 2026 scores directly into the sheet.
// Select "testJul12Data" from the function dropdown, then click Run.
// Check the Execution log below for success/error messages.
function testJul12Data() {
  var data = {
    date: "Jul 12",
    playing_hc: { Owens:14, Carter:15, Felter:17 },
    hc_index:   { Farnia:16.0, Owens:12.1, Felter:15.3, Carter:13.1, Lorenz:13.0 },
    scores: {
      Owens:  [4,5,6,5,4,3,7,5,3, 5,6,5,6,4,4,6,4,5],  // gross 87, net 73
      Carter: [5,5,5,5,4,4,6,5,3, 5,5,7,5,3,6,6,5,4],  // gross 88, net 73 (birdie H14)
      Felter: [5,7,6,6,4,5,6,4,3, 4,7,4,5,4,7,6,6,5]   // gross 94, net 77
      // Farnia, Lorenz: DNS
    }
  };
  var result = processRoundData(data);
  Logger.log(result);
  console.log(result);
  return result;
}

// ── Jul 19 Test (R13) ────────────────────────────────────────
// Run this to push Jul 19, 2026 scores directly into the sheet.
// Select "testJul19Data" from the function dropdown, then click Run.
// Check the Execution log below for success/error messages.
function testJul19Data() {
  var data = {
    date: "Jul 19",
    playing_hc: { Farnia:18, Carter:15 },
    hc_index:   { Farnia:16.0, Owens:12.1, Felter:15.6, Carter:13.1, Lorenz:13.0 },
    scores: {
      Farnia: [6,5,6,6,6,5,8,4,4,4,5,5,6,4,4,5,3,6],  // gross 92, net 74
      Carter: [4,5,5,6,5,3,5,5,3,4,5,6,5,5,5,6,4,4]   // gross 85, net 70
      // Owens, Felter, Lorenz: DNS
    }
  };
  var result = processRoundData(data);
  Logger.log(result);
  console.log(result);
  return result;
}

// ── Jul 26 Test (R14) ────────────────────────────────────────
// Run this to push Jul 26, 2026 scores directly into the sheet.
// Select "testJul26Data" from the function dropdown, then click Run.
// Check the Execution log below for success/error messages.
function testJul26Data() {
  var data = {
    date: "Jul 26",
    playing_hc: { Owens:14, Carter:15, Felter:18 },
    hc_index:   { Farnia:16.0, Owens:12.2, Felter:15.6, Carter:13.1, Lorenz:13.0 },
    scores: {
      Owens:  [6,5,5,5,4,4,7,5,4,3,6,4,5,5,5,6,4,5],  // gross 88, net 74
      Carter: [5,5,5,5,4,3,6,4,4,5,5,5,5,4,4,6,4,6],  // gross 85, net 70
      Felter: [6,5,5,7,5,4,4,5,5,5,7,5,5,6,6,7,3,5]   // gross 95, net 77
      // Farnia, Lorenz: DNS
    }
  };
  var result = processRoundData(data);
  Logger.log(result);
  console.log(result);
  return result;
}
