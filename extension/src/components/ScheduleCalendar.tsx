import React from "react";

/**
 * AI가 출력하는 ```schedule 코드블록 포맷:
 *
 * HEADER: 월(06/02),화(06/03),수(06/04),목(06/05),금(06/06)
 * 09:00: 가능,회의,가능,가능,가능
 * 09:30: 가능,회의,가능,가능,가능
 * 10:00: 회의,회의,가능,특강:AI개론,가능
 * ...
 *
 * 각 셀 값: "가능", "회의", "불가", "특강:제목", "멘토링:제목", 또는 빈 문자열
 */

type CellType = "available" | "meeting" | "unavailable" | "lecture" | "mentoring";

interface Cell {
  type: CellType;
  label: string;
  tooltipTitle: string;
  tooltipBody: string;
}

interface ParsedSchedule {
  headers: string[];
  timeSlots: { time: string; cells: Cell[] }[];
}

function parseCellValue(raw: string): Cell {
  const [displayRaw, detailRaw] = raw.split("||");
  const v = displayRaw.trim();
  const detail = (detailRaw || "").trim();
  if (!v || v === "-") {
    return {
      type: "available",
      label: "",
      tooltipTitle: "가능",
      tooltipBody: "이 시간대는 비어 있습니다.",
    };
  }
  if (v === "가능") {
    return {
      type: "available",
      label: "",
      tooltipTitle: "가능",
      tooltipBody: "이 시간대는 비어 있습니다.",
    };
  }
  if (v === "회의" || v.startsWith("회의:")) {
    const title = v.startsWith("회의:") ? v.slice(3).trim() : "회의";
    return {
      type: "meeting",
      label: title,
      tooltipTitle: "회의 불가",
      tooltipBody: detail || (title ? `회의 "${title}"이(가) 배치된 시간대입니다.` : "팀 회의 또는 조율 불가 시간대입니다."),
    };
  }
  if (v === "불가" || v.startsWith("불가:")) {
    const title = v.startsWith("불가:") ? v.slice(3).trim() : "불가";
    return {
      type: "unavailable",
      label: title,
      tooltipTitle: "불가",
      tooltipBody: detail || "다른 개인 일정이 겹치는 시간대입니다.",
    };
  }
  if (v.startsWith("특강:")) {
    const title = v.slice(3).trim();
    return {
      type: "lecture",
      label: title,
      tooltipTitle: "특강",
      tooltipBody: detail || (title ? `특강 "${title}"이(가) 배치된 시간대입니다.` : "특강이 배치된 시간대입니다."),
    };
  }
  if (v.startsWith("멘토링:")) {
    const title = v.slice(4).trim();
    return {
      type: "mentoring",
      label: title,
      tooltipTitle: "멘토링",
      tooltipBody: detail || (title ? `멘토링 "${title}"이(가) 배치된 시간대입니다.` : "멘토링이 배치된 시간대입니다."),
    };
  }
  // fallback: treat unknown as unavailable with label
  return {
    type: "unavailable",
    label: v,
    tooltipTitle: "상세 정보",
    tooltipBody: detail || v,
  };
}

function parseScheduleBlock(raw: string): ParsedSchedule | null {
  const lines = raw.trim().split("\n").filter((l) => l.trim());
  if (lines.length < 2) return null;

  const headerLine = lines.find((l) => l.startsWith("HEADER:"));
  if (!headerLine) return null;

  const headers = headerLine
    .replace("HEADER:", "")
    .split(",")
    .map((h) => h.trim());

  const timeSlots: ParsedSchedule["timeSlots"] = [];
  for (const line of lines) {
    if (line.startsWith("HEADER:")) continue;
    const colonIdx = line.indexOf(":");
    if (colonIdx === -1) continue;

    // Handle time format like "09:00:" or "09:30:"
    const timeMatch = line.match(/^(\d{1,2}:\d{2}):\s*(.*)/);
    if (!timeMatch) continue;

    const time = timeMatch[1];
    const cellValues = timeMatch[2].split(",").map((v) => parseCellValue(v));

    // Pad or trim to match header length
    while (cellValues.length < headers.length) {
      cellValues.push({
        type: "available",
        label: "",
        tooltipTitle: "가능",
        tooltipBody: "이 시간대는 비어 있습니다.",
      });
    }

    timeSlots.push({ time, cells: cellValues.slice(0, headers.length) });
  }

  if (timeSlots.length === 0) return null;
  return { headers, timeSlots };
}

const CELL_STYLES: Record<CellType, React.CSSProperties> = {
  available: {
    background: "linear-gradient(135deg, #d1fae5, #a7f3d0)",
    color: "#065f46",
  },
  meeting: {
    background: "linear-gradient(135deg, #fecaca, #fca5a5)",
    color: "#991b1b",
  },
  unavailable: {
    background: "linear-gradient(135deg, #e2e8f0, #cbd5e1)",
    color: "#475569",
  },
  lecture: {
    background: "linear-gradient(135deg, #fef08a, #fde047)",
    color: "#854d0e",
  },
  mentoring: {
    background: "linear-gradient(135deg, #c4b5fd, #a78bfa)",
    color: "#4c1d95",
  },
};

interface ScheduleCalendarProps {
  content: string;
}

export const ScheduleCalendar: React.FC<ScheduleCalendarProps> = ({ content }) => {
  const parsed = parseScheduleBlock(content);
  if (!parsed) return <pre className="schedule-fallback">{content}</pre>;

  return (
    <div className="schedule-calendar-wrapper">
      <div className="schedule-calendar">
        <table>
          <thead>
            <tr>
              <th className="time-header">시간</th>
              {parsed.headers.map((h, i) => (
                <th key={i} className="day-header">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {parsed.timeSlots.map((slot, ri) => (
              <tr key={ri}>
                <td className="time-cell">{slot.time}</td>
                {slot.cells.map((cell, ci) => (
                  <td
                    key={ci}
                    className={`schedule-cell schedule-cell--${cell.type}`}
                    style={CELL_STYLES[cell.type]}
                    title={`${parsed.headers[ci] ?? ""} · ${slot.time}\n${cell.tooltipTitle}\n${cell.tooltipBody}`}
                  >
                    <span className="cell-label">
                      {cell.label || (cell.type === "available" ? "가능" : "")}
                    </span>
                    <div className="schedule-tooltip" role="tooltip" aria-hidden="true">
                      <div className="schedule-tooltip__header">{cell.tooltipTitle}</div>
                      <div className="schedule-tooltip__meta">
                        {parsed.headers[ci]} · {slot.time}
                      </div>
                      <div className="schedule-tooltip__body">{cell.tooltipBody}</div>
                    </div>
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="schedule-legend">
        <span className="legend-item">
          <span className="legend-swatch" style={{ background: "#a7f3d0" }} />
          가능
        </span>
        <span className="legend-item">
          <span className="legend-swatch" style={{ background: "#fca5a5" }} />
          회의
        </span>
        <span className="legend-item">
          <span className="legend-swatch" style={{ background: "#fde047" }} />
          특강
        </span>
        <span className="legend-item">
          <span className="legend-swatch" style={{ background: "#a78bfa" }} />
          멘토링
        </span>
        <span className="legend-item">
          <span className="legend-swatch" style={{ background: "#cbd5e1" }} />
          불가
        </span>
      </div>
    </div>
  );
};
