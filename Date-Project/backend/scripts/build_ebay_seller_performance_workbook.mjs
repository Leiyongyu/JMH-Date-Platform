import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const [inputPath, outputPath, previewDir] = process.argv.slice(2);
if (!inputPath || !outputPath || !previewDir) {
  throw new Error("Usage: node build.mjs <normalized.json> <output.xlsx> <preview-dir>");
}

const data = JSON.parse(await fs.readFile(inputPath, "utf8"));
const workbook = Workbook.create();
const fontFamily = "Arial";
const colors = {
  navy: "#1F4E78",
  blue: "#D9EAF7",
  paleBlue: "#EAF3F8",
  lightGray: "#F3F4F6",
  border: "#D9E1E8",
  text: "#1F2937",
  muted: "#5B6573",
  redFill: "#FCE8E6",
  redText: "#B3261E",
  greenFill: "#E6F4EA",
  greenText: "#137333",
  amberFill: "#FEF3C7",
  amberText: "#92400E",
};

const asDate = (value) => {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
};

const evaluationLabel = (value) => value === "CURRENT" ? "当前正式评估" : value === "PROJECTED" ? "预测评估" : value;

function applyBaseSheetStyle(sheet, usedRange) {
  sheet.showGridLines = false;
  usedRange.format.font = { name: fontFamily, size: 10, color: colors.text };
  usedRange.format.verticalAlignment = "center";
}

function styleTitle(sheet, endColumn) {
  const title = sheet.getRange(`A2:${endColumn}2`);
  title.format.font = { name: fontFamily, size: 14, bold: true, color: colors.navy };
  title.format.borders = { bottom: { style: "thin", color: colors.navy } };
  const context = sheet.getRange(`A3:${endColumn}3`);
  context.format.font = { name: fontFamily, size: 10, italic: true, color: colors.muted };
}

function styleHeader(range) {
  range.format = {
    fill: colors.navy,
    font: { name: fontFamily, size: 10, bold: true, color: "#FFFFFF" },
    horizontalAlignment: "center",
    verticalAlignment: "center",
    wrapText: true,
    borders: { preset: "all", style: "thin", color: "#FFFFFF" },
  };
  range.format.rowHeight = 30;
}

function styleBody(range) {
  range.format.borders = {
    insideHorizontal: { style: "thin", color: colors.border },
    bottom: { style: "thin", color: colors.border },
  };
}

function addTable(sheet, rangeAddress, name) {
  const table = sheet.tables.add(rangeAddress, true, name);
  table.style = "TableStyleMedium2";
  table.showFilterButton = true;
  return table;
}

const summarySheet = workbook.worksheets.add("卖家绩效总览");
summarySheet.tabColor = colors.navy;
summarySheet.getRange("A2").values = [["eBay 卖家不良交易表现"]];
summarySheet.getRange("A3").values = [[
  `账号：${data.metadata.username || ""}　导出时间（UTC）：${data.metadata.exportedAtUtc || ""}　CURRENT 为最近正式月度评估，PROJECTED 为当前预测。`,
]];
const summaryHeaders = [
  "站点", "评估周期", "项目", "当前值", "单位", "分子", "分母", "同业平均值",
  "高于同业", "eBay 评级/级别", "政策阈值", "数据口径", "评估时间", "统计开始", "统计结束", "数据源",
];
summarySheet.getRange("A5:P5").values = [summaryHeaders];
const summaryRows = data.summaryRows.map((row) => [
  row.marketplaceLabel,
  evaluationLabel(row.evaluationType),
  row.metricLabel,
  row.currentValue,
  row.valueUnit === "PERCENT" ? "%" : "笔",
  row.numerator,
  row.denominator,
  row.peerAverage,
  null,
  row.rating,
  row.policyThreshold,
  row.scopeNote,
  asDate(row.evaluationDate),
  asDate(row.lookbackStartDate),
  asDate(row.lookbackEndDate),
  row.source,
]);
const summaryLastRow = Math.max(6, summaryRows.length + 5);
if (summaryRows.length > 0) {
  summarySheet.getRangeByIndexes(5, 0, summaryRows.length, summaryHeaders.length).values = summaryRows;
  const firstDataRow = 6;
  const lastDataRow = firstDataRow + summaryRows.length - 1;
  for (let rowNumber = firstDataRow; rowNumber <= lastDataRow; rowNumber += 1) {
    summarySheet.getRange(`I${rowNumber}`).formulas = [[`=IF(OR(D${rowNumber}="",H${rowNumber}=""),"",D${rowNumber}-H${rowNumber})`]];
  }
  for (let index = 0; index < data.summaryRows.length; index += 1) {
    const rowNumber = firstDataRow + index;
    const numberFormat = data.summaryRows[index].valueUnit === "PERCENT" ? "0.00%" : "#,##0";
    summarySheet.getRange(`D${rowNumber}:D${rowNumber}`).format.numberFormat = numberFormat;
    summarySheet.getRange(`K${rowNumber}:K${rowNumber}`).format.numberFormat = numberFormat;
  }
  summarySheet.getRange(`H${firstDataRow}:I${lastDataRow}`).format.numberFormat = "0.00%";
  summarySheet.getRange(`F${firstDataRow}:G${lastDataRow}`).format.numberFormat = "#,##0";
  summarySheet.getRange(`M${firstDataRow}:O${lastDataRow}`).format.numberFormat = "yyyy-mm-dd hh:mm";
  summarySheet.getRange(`I${firstDataRow}:I${lastDataRow}`).conditionalFormats.add("cellIs", {
    operator: "greaterThan",
    formula: 0,
    format: { fill: colors.redFill, font: { color: colors.redText, bold: true } },
  });
  summarySheet.getRange(`I${firstDataRow}:I${lastDataRow}`).conditionalFormats.add("cellIs", {
    operator: "lessThanOrEqual",
    formula: 0,
    format: { fill: colors.greenFill, font: { color: colors.greenText } },
  });
  summarySheet.getRange(`J${firstDataRow}:J${lastDataRow}`).conditionalFormats.add("containsText", {
    text: "HIGH",
    format: { fill: colors.redFill, font: { color: colors.redText, bold: true } },
  });
  styleBody(summarySheet.getRange(`A${firstDataRow}:P${lastDataRow}`));
  addTable(summarySheet, `A5:P${lastDataRow}`, "SellerPerformanceSummary");
}
styleTitle(summarySheet, "P");
styleHeader(summarySheet.getRange("A5:P5"));
applyBaseSheetStyle(summarySheet, summarySheet.getRange(`A1:P${summaryLastRow}`));
summarySheet.getRange("A1:P1").format.rowHeight = 8;
summarySheet.getRange("A2:P2").format.rowHeight = 24;
summarySheet.getRange("A3:P3").format.rowHeight = 22;
summarySheet.getRange(`A1:A${summaryLastRow}`).format.columnWidth = 20;
summarySheet.getRange(`B1:B${summaryLastRow}`).format.columnWidth = 16;
summarySheet.getRange(`C1:C${summaryLastRow}`).format.columnWidth = 22;
summarySheet.getRange(`D1:K${summaryLastRow}`).format.columnWidth = 13;
summarySheet.getRange(`L1:L${summaryLastRow}`).format.columnWidth = 34;
summarySheet.getRange(`M1:O${summaryLastRow}`).format.columnWidth = 19;
summarySheet.getRange(`P1:P${summaryLastRow}`).format.columnWidth = 29;
summarySheet.getRange(`L6:L${summaryLastRow}`).format.wrapText = true;
summarySheet.freezePanes.freezeRows(5);

const detailSheet = workbook.worksheets.add("问题细分");
detailSheet.tabColor = "#5B9BD5";
detailSheet.getRange("A2").values = [["物品与描述不符、物品未收到问题细分"]];
detailSheet.getRange("A3").values = [["物品与描述不符按一级品类细分；物品未收到按收货地区细分。原因数量来自 COUNT.distributions；空白表示接口未返回更细原因。"]];
const detailHeaders = [
  "站点", "评估周期", "项目", "细分类型", "细分名称", "细分值", "当前值", "分子", "分母", "同业平均值",
  "高于同业", "eBay 评级", "问题分布口径", "问题代码", "问题细分", "问题数量", "问题占该项目", "基准口径",
  "基准调整", "评估时间", "统计开始", "统计结束", "站点代码", "项目代码",
];
detailSheet.getRange("A5:X5").values = [detailHeaders];
const detailRows = data.detailRows.map((row) => [
  row.marketplaceLabel,
  evaluationLabel(row.evaluationType),
  row.metricLabel,
  row.dimensionKey,
  row.dimensionName,
  row.dimensionValue,
  row.currentRate,
  row.numerator,
  row.denominator,
  row.peerAverage,
  row.peerGap,
  row.rating,
  row.distributionBasis,
  row.issueName,
  row.issueLabel,
  row.issueCount,
  row.issueShare,
  row.benchmarkBasis,
  row.benchmarkAdjustment,
  asDate(row.evaluationDate),
  asDate(row.lookbackStartDate),
  asDate(row.lookbackEndDate),
  row.marketplaceId,
  row.metricType,
]);
const detailLastRow = Math.max(6, detailRows.length + 5);
if (detailRows.length > 0) {
  detailSheet.getRangeByIndexes(5, 0, detailRows.length, detailHeaders.length).values = detailRows;
  const lastDetailRow = detailRows.length + 5;
  detailSheet.getRange(`G6:G${lastDetailRow}`).format.numberFormat = "0.00%";
  detailSheet.getRange(`J6:K${lastDetailRow}`).format.numberFormat = "0.00%";
  detailSheet.getRange(`Q6:Q${lastDetailRow}`).format.numberFormat = "0.0%";
  detailSheet.getRange(`H6:I${lastDetailRow}`).format.numberFormat = "#,##0";
  detailSheet.getRange(`P6:P${lastDetailRow}`).format.numberFormat = "#,##0";
  detailSheet.getRange(`T6:V${lastDetailRow}`).format.numberFormat = "yyyy-mm-dd hh:mm";
  detailSheet.getRange(`K6:K${lastDetailRow}`).conditionalFormats.add("cellIs", {
    operator: "greaterThan",
    formula: 0,
    format: { fill: colors.redFill, font: { color: colors.redText, bold: true } },
  });
  detailSheet.getRange(`K6:K${lastDetailRow}`).conditionalFormats.add("cellIs", {
    operator: "lessThanOrEqual",
    formula: 0,
    format: { fill: colors.greenFill, font: { color: colors.greenText } },
  });
  styleBody(detailSheet.getRange(`A6:X${lastDetailRow}`));
  addTable(detailSheet, `A5:X${lastDetailRow}`, "SellerPerformanceDetails");
}
styleTitle(detailSheet, "X");
styleHeader(detailSheet.getRange("A5:X5"));
applyBaseSheetStyle(detailSheet, detailSheet.getRange(`A1:X${detailLastRow}`));
detailSheet.getRange("A1:X1").format.rowHeight = 8;
detailSheet.getRange("A2:X2").format.rowHeight = 24;
detailSheet.getRange("A3:X3").format.rowHeight = 22;
detailSheet.getRange(`A1:C${detailLastRow}`).format.columnWidth = 18;
detailSheet.getRange(`D1:D${detailLastRow}`).format.columnWidth = 20;
detailSheet.getRange(`E1:E${detailLastRow}`).format.columnWidth = 28;
detailSheet.getRange(`F1:Q${detailLastRow}`).format.columnWidth = 16;
detailSheet.getRange(`R1:S${detailLastRow}`).format.columnWidth = 18;
detailSheet.getRange(`T1:V${detailLastRow}`).format.columnWidth = 19;
detailSheet.getRange(`W1:X${detailLastRow}`).format.columnWidth = 22;
detailSheet.freezePanes.freezeRows(5);
detailSheet.freezePanes.freezeColumns(3);

const statusSheet = workbook.worksheets.add("接口状态");
statusSheet.tabColor = "#A5A5A5";
statusSheet.getRange("A2").values = [["eBay 接口调用状态"]];
statusSheet.getRange("A3").values = [["HTTP 200 表示接口返回成功；409 通常表示该账号在该站点没有可用的服务指标；400 表示站点不受该资源支持。"]];
const statusHeaders = ["数据源", "站点", "站点代码", "评估周期", "项目", "项目代码", "HTTP 状态", "成功", "细分数量", "错误信息"];
statusSheet.getRange("A5:J5").values = [statusHeaders];
const statusRows = data.statusRows.map((row) => [
  row.source,
  row.marketplaceLabel,
  row.marketplaceId,
  row.evaluationType,
  row.metricLabel,
  row.metricType,
  row.statusCode,
  row.success ? "是" : "否",
  row.dimensionCount,
  row.errorMessage,
]);
const statusLastRow = Math.max(6, statusRows.length + 5);
if (statusRows.length > 0) {
  statusSheet.getRangeByIndexes(5, 0, statusRows.length, statusHeaders.length).values = statusRows;
  const lastStatusRow = statusRows.length + 5;
  statusSheet.getRange(`G6:G${lastStatusRow}`).format.numberFormat = "0";
  statusSheet.getRange(`I6:I${lastStatusRow}`).format.numberFormat = "#,##0";
  statusSheet.getRange(`G6:G${lastStatusRow}`).conditionalFormats.add("cellIs", {
    operator: "notEqual",
    formula: 200,
    format: { fill: colors.redFill, font: { color: colors.redText, bold: true } },
  });
  statusSheet.getRange(`G6:G${lastStatusRow}`).conditionalFormats.add("cellIs", {
    operator: "equal",
    formula: 200,
    format: { fill: colors.greenFill, font: { color: colors.greenText } },
  });
  styleBody(statusSheet.getRange(`A6:J${lastStatusRow}`));
  addTable(statusSheet, `A5:J${lastStatusRow}`, "ApiStatus");
}
styleTitle(statusSheet, "J");
styleHeader(statusSheet.getRange("A5:J5"));
applyBaseSheetStyle(statusSheet, statusSheet.getRange(`A1:J${statusLastRow}`));
statusSheet.getRange("A1:J1").format.rowHeight = 8;
statusSheet.getRange("A2:J2").format.rowHeight = 24;
statusSheet.getRange("A3:J3").format.rowHeight = 22;
statusSheet.getRange(`A1:A${statusLastRow}`).format.columnWidth = 30;
statusSheet.getRange(`B1:F${statusLastRow}`).format.columnWidth = 20;
statusSheet.getRange(`G1:I${statusLastRow}`).format.columnWidth = 12;
statusSheet.getRange(`J1:J${statusLastRow}`).format.columnWidth = 70;
statusSheet.getRange(`J6:J${statusLastRow}`).format.wrapText = true;
statusSheet.freezePanes.freezeRows(5);

const notesSheet = workbook.worksheets.add("导出说明");
notesSheet.tabColor = "#7F8C8D";
notesSheet.getRange("A2").values = [["导出说明与指标覆盖"]];
notesSheet.getRange("A3").values = [["所有数值均来自本次 eBay 正式接口响应；未返回的指标标记为缺口，不从截图推断。"]];
notesSheet.getRange("A5:D5").values = [["目标项目", "可用性", "数据源", "说明"]];
const coverageRows = data.coverageRows.map((row) => [row.requestedMetric, row.availability, row.source, row.note]);
if (coverageRows.length > 0) {
  notesSheet.getRangeByIndexes(5, 0, coverageRows.length, 4).values = coverageRows;
  const lastCoverageRow = coverageRows.length + 5;
  styleBody(notesSheet.getRange(`A6:D${lastCoverageRow}`));
  addTable(notesSheet, `A5:D${lastCoverageRow}`, "MetricCoverage");
  notesSheet.getRange(`B6:B${lastCoverageRow}`).conditionalFormats.add("containsText", {
    text: "未返回",
    format: { fill: colors.amberFill, font: { color: colors.amberText, bold: true } },
  });
  notesSheet.getRange(`B6:B${lastCoverageRow}`).conditionalFormats.add("containsText", {
    text: "无完全同名",
    format: { fill: colors.amberFill, font: { color: colors.amberText, bold: true } },
  });
}
const sourceStart = 15;
notesSheet.getRange(`A${sourceStart}:D${sourceStart}`).values = [["接口", "用途", "关键字段", "备注"]];
notesSheet.getRange(`A${sourceStart + 1}:D${sourceStart + 2}`).values = [
  ["/sell/analytics/v1/customer_service_metric/...", "物品与描述不符、物品未收到", "RATE / COUNT / TRANSACTION_COUNT / benchmark", "按站点、当前/预测周期读取"],
  ["/sell/analytics/v1/seller_standards_profile", "不良交易、未经卖家解决的纠纷、延迟发货", "metricKey / value / numerator / denominator / threshold", "卖家标准接口不提供同业平均"],
];
styleHeader(notesSheet.getRange("A5:D5"));
styleHeader(notesSheet.getRange(`A${sourceStart}:D${sourceStart}`));
styleBody(notesSheet.getRange(`A${sourceStart + 1}:D${sourceStart + 2}`));
styleTitle(notesSheet, "D");
applyBaseSheetStyle(notesSheet, notesSheet.getRange(`A1:D${sourceStart + 2}`));
notesSheet.getRange("A1:D1").format.rowHeight = 8;
notesSheet.getRange("A2:D2").format.rowHeight = 24;
notesSheet.getRange("A3:D3").format.rowHeight = 22;
notesSheet.getRange(`A1:A${sourceStart + 2}`).format.columnWidth = 28;
notesSheet.getRange(`B1:B${sourceStart + 2}`).format.columnWidth = 24;
notesSheet.getRange(`C1:C${sourceStart + 2}`).format.columnWidth = 40;
notesSheet.getRange(`D1:D${sourceStart + 2}`).format.columnWidth = 68;
notesSheet.getRange(`A6:D${sourceStart + 2}`).format.wrapText = true;

workbook.recalculate();

const inspectParts = [];
inspectParts.push((await workbook.inspect({
  kind: "table",
  range: `卖家绩效总览!A1:P${Math.min(summaryRows.length + 5, 30)}`,
  include: "values,formulas",
  tableMaxRows: 30,
  tableMaxCols: 16,
})).ndjson);
inspectParts.push((await workbook.inspect({
  kind: "table",
  range: `问题细分!A1:X${Math.min(detailRows.length + 5, 30)}`,
  include: "values,formulas",
  tableMaxRows: 30,
  tableMaxCols: 24,
})).ndjson);
inspectParts.push((await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!",
  options: { useRegex: true, maxResults: 300 },
  summary: "final formula error scan",
})).ndjson);

await fs.mkdir(path.dirname(outputPath), { recursive: true });
await fs.mkdir(previewDir, { recursive: true });
for (const sheetName of ["卖家绩效总览", "问题细分", "接口状态", "导出说明"]) {
  const preview = await workbook.render({ sheetName, autoCrop: "all", scale: 1, format: "png" });
  await fs.writeFile(path.join(previewDir, `${sheetName}.png`), new Uint8Array(await preview.arrayBuffer()));
}
const xlsx = await SpreadsheetFile.exportXlsx(workbook);
await xlsx.save(outputPath);
await fs.writeFile(`${outputPath}.inspect.ndjson`, inspectParts.filter(Boolean).join("\n"), "utf8");

console.log(JSON.stringify({
  outputPath,
  summaryRows: summaryRows.length,
  detailRows: detailRows.length,
  statusRows: statusRows.length,
  sheets: ["卖家绩效总览", "问题细分", "接口状态", "导出说明"],
}, null, 2));
