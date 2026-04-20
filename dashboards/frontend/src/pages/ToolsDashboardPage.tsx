import { useRef, useEffect, useState, useCallback, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import Typography from "@mui/material/Typography";
import Box from "@mui/material/Box";
import LinearProgress from "@mui/material/LinearProgress";
import Chip from "@mui/material/Chip";
import IconButton from "@mui/material/IconButton";
import { keyframes } from "@mui/system";
import CalendarTodayIcon from "@mui/icons-material/CalendarToday";
import EventIcon from "@mui/icons-material/Event";
import ArrowBackIosNewIcon from "@mui/icons-material/ArrowBackIosNew";
import ArrowForwardIosIcon from "@mui/icons-material/ArrowForwardIos";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";

import BuildIcon from "@mui/icons-material/Build";
import ReportProblemIcon from "@mui/icons-material/ReportProblem";
import ErrorIcon from "@mui/icons-material/Error";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import ArrowUpwardIcon from "@mui/icons-material/ArrowUpward";
import ArrowDownwardIcon from "@mui/icons-material/ArrowDownward";
import { useToolsToday, useToolsForDate, usePMStatus, usePMStatusAll, useToolsCount } from "@/api";
import type { ToolWithMachines, PMStatusEntry } from "@/api";
import { formatIndianCompact as formatNumber } from "@/utils";

// ── Helpers ────────────────────────────────────────────────────────

function formatDate(d: string): string {
  return new Date(d + "T00:00:00").toLocaleDateString("en-IN", {
    weekday: "long",
    month: "long",
    day: "numeric",
    year: "numeric",
  });
}

function formatShortDate(d: string): string {
  return new Date(d + "T00:00:00").toLocaleDateString("en-IN", {
    weekday: "short",
    month: "short",
    day: "numeric",
  });
}

/** Return YYYY-MM-DD for today + N days */
function dateOffset(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

/** Friendly label for an offset */
function offsetLabel(offset: number): string {
  if (offset === 1) return "Tomorrow";
  if (offset === 2) return "Day After Tomorrow";
  return formatShortDate(dateOffset(offset));
}

// ── Sub-components ─────────────────────────────────────────────────

function StatCardCustom({
  icon,
  label,
  value,
  bgColor,
}: {
  icon: React.ReactNode;
  label: string;
  value: number | string;
  bgColor: string;
}) {
  return (
    <Box
      sx={{
        flex: 1,
        display: "flex",
        alignItems: "center",
        gap: 1.5,
        bgcolor: "#fff",
        borderRadius: 2,
        px: 2,
        py: 1,
        boxShadow: "0 1px 4px rgba(0,0,0,0.06)",
      }}
    >
      <Box
        sx={{
          width: 36,
          height: 36,
          borderRadius: 1.5,
          bgcolor: bgColor,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: "#fff",
          flexShrink: 0,
          "& .MuiSvgIcon-root": { fontSize: 20 },
        }}
      >
        {icon}
      </Box>
      <Typography variant="h6" fontWeight={700} lineHeight={1} sx={{ flexShrink: 0 }}>
        {value}
      </Typography>
      <Typography
        variant="body2"
        color="text.secondary"
        fontWeight={500}
        sx={{ lineHeight: 1.2 }}
      >
        {label}
      </Typography>
    </Box>
  );
}

/** Flat entry: one card per tool × machine schedule */
interface ToolScheduleEntry {
  toolId: number;
  toolNo: string;
  partNo: string;
  partName: string;
  cavity: number;
  machineId: number;
  machineName: string;
  scheduledQty: number;
  scheduledStrokes: number;
}

/** Flatten grouped tool data into one entry per machine schedule */
function flattenTools(tools: ToolWithMachines[]): ToolScheduleEntry[] {
  return tools.flatMap((t) =>
    t.machines.map((m) => ({
      toolId: t.toolId,
      toolNo: t.toolNo,
      partNo: t.partNo,
      partName: t.partName,
      cavity: t.cavity,
      machineId: m.machineId,
      machineName: m.machineName,
      scheduledQty: m.scheduledQty,
      scheduledStrokes: m.scheduledStrokes,
    })),
  );
}

/** Tiny inline progress bar */
function MiniBar({
  value,
  max,
  pct,
  color,
  label,
}: {
  value: number;
  max: number;
  pct: number;
  color: string;
  label: string;
}) {
  return (
    <Box sx={{ flex: 1, minWidth: 0 }}>
      <Box sx={{ display: "flex", justifyContent: "space-between", mb: 0.15 }}>
        <Typography variant="caption" sx={{ fontSize: 9, color: "text.primary", fontWeight: 700, lineHeight: 1 }}>
          {label}
        </Typography>
        <Typography variant="caption" sx={{ fontSize: 9, fontWeight: 700, lineHeight: 1 }}>
          {formatNumber(value)}/{formatNumber(max)} ({pct}%)
        </Typography>
      </Box>
      <Box sx={{ height: 3, borderRadius: 2, bgcolor: "grey.200", overflow: "hidden" }}>
        <Box sx={{ height: "100%", width: `${Math.min(pct, 100)}%`, bgcolor: color, borderRadius: 2 }} />
      </Box>
    </Box>
  );
}

const blinkRed = keyframes`
  0%, 100% { border-color: #d32f2f; }
  50% { border-color: transparent; }
`;

function ToolCard({ entry, pmEntry }: { entry: ToolScheduleEntry; pmEntry?: PMStatusEntry }) {
  const hasPM = !!pmEntry;
  const pmPct = pmEntry?.pmPercentage ?? 0;
  const lifePct = pmEntry
    ? pmEntry.toolLife > 0
      ? Math.min(Math.round((pmEntry.totalLifetimeStrokes / pmEntry.toolLife) * 100), 100)
      : 0
    : 0;

  // Projected PM %: how far (totalStrokes + scheduledQty) is from pmCurrentStroke toward nextStroke
  const pmRange = hasPM ? (pmEntry!.nextStroke - pmEntry!.pmCurrentStroke) : 0;
  const projectedPmPct = hasPM && pmRange > 0
    ? Math.round(((pmEntry!.totalLifetimeStrokes + entry.scheduledStrokes - pmEntry!.pmCurrentStroke) / pmRange) * 100)
    : 0;

  const willCross100 = hasPM && projectedPmPct >= 100;
  const willReach80 = hasPM && projectedPmPct >= 80 && !willCross100;

  const pmBarColor = pmPct >= 80 ? "#d32f2f" : pmPct >= 50 ? "#ed6c02" : "#2e7d32";
  const lifeBarColor = lifePct >= 80 ? "#d32f2f" : lifePct >= 50 ? "#ed6c02" : "#2e7d32";

  return (
    <Box
      sx={{
        border: "2px solid",
        borderColor: willCross100 ? "#d32f2f" : willReach80 ? "#f9a825" : "grey.200",
        borderRadius: 1.5,
        px: 1.5,
        py: 0.75,
        mb: 0.75,
        bgcolor: "#fff",
        ...(willCross100 && {
          animation: `${blinkRed} 1s ease-in-out infinite`,
        }),
      }}
    >
      {/* Row 1: Tool No | Machine | Qty */}
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 0.25 }}>
        <Typography variant="body2" fontWeight={700} noWrap sx={{ fontSize: 13 }}>
          {entry.toolNo}
        </Typography>
        <Box sx={{ flex: 1 }} />
        <Box
          sx={{
            bgcolor: "grey.100",
            borderRadius: 0.75,
            px: 0.75,
            py: 0.15,
            flexShrink: 0,
          }}
        >
          <Typography variant="caption" fontWeight={700} sx={{ fontSize: 10, lineHeight: 1 }}>
            {entry.machineName}
          </Typography>
        </Box>
        <Typography
          variant="caption"
          fontWeight={700}
          color="primary"
          sx={{ flexShrink: 0, fontSize: 12 }}
        >
          {formatNumber(entry.scheduledQty)}
        </Typography>
      </Box>

      {/* Row 2: Part name + part number (full width) */}
      <Typography
        variant="caption"
        fontWeight={700}
        sx={{ fontSize: 10, display: "block", lineHeight: 1.3, mb: 0.4 }}
      >
        {entry.partName}
        <Typography component="span" variant="caption" fontWeight={700} sx={{ fontSize: 10, ml: 0.5 }}>
          ({entry.partNo})
        </Typography>
      </Typography>

      {/* Row 3: PM strokes + Tool life mini bars */}
      {hasPM ? (
        <Box sx={{ display: "flex", gap: 1.5 }}>
          <MiniBar
            label="PM"
            value={pmEntry!.totalLifetimeStrokes - pmEntry!.pmCurrentStroke}
            max={pmEntry!.nextStroke - pmEntry!.pmCurrentStroke}
            pct={pmPct}
            color={pmBarColor}
          />
          <MiniBar
            label="Life"
            value={pmEntry!.totalLifetimeStrokes}
            max={pmEntry!.toolLife}
            pct={lifePct}
            color={lifeBarColor}
          />
        </Box>
      ) : (
        <Box sx={{ display: "flex", gap: 1.5 }}>
          <Box sx={{ flex: 1, display: "flex", alignItems: "center", gap: 0.5 }}>
            <Typography variant="caption" sx={{ fontSize: 9, fontWeight: 700 }}>PM</Typography>
            <Typography variant="caption" sx={{ fontSize: 11, fontWeight: 700 }}>∞</Typography>
          </Box>
          <Box sx={{ flex: 1, display: "flex", alignItems: "center", gap: 0.5 }}>
            <Typography variant="caption" sx={{ fontSize: 9, fontWeight: 700 }}>Life</Typography>
            <Typography variant="caption" sx={{ fontSize: 11, fontWeight: 700 }}>∞</Typography>
          </Box>
        </Box>
      )}
    </Box>
  );
}

function MaintenanceCard({ entry }: { entry: PMStatusEntry }) {
  const isCritical = entry.pmPercentage >= 100;
  const barColor = isCritical ? "#d32f2f" : "#ed6c02";
  const lifePercentage =
    entry.toolLife > 0
      ? Math.min(Math.round((entry.totalLifetimeStrokes / entry.toolLife) * 100), 100)
      : 0;
  const lifeBarColor = lifePercentage >= 80 ? "#d32f2f" : lifePercentage >= 50 ? "#ed6c02" : "#2e7d32";

  return (
    <Box
      sx={{
        border: "1px solid",
        borderColor: "grey.200",
        borderRadius: 2,
        p: 2,
        mb: 1.5,
        bgcolor: "#fff",
      }}
    >
      <Box
        sx={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
          mb: 0.5,
        }}
      >
        <Typography variant="subtitle2" fontWeight={700} sx={{ fontSize: 12 }}>
          {entry.toolNo}
        </Typography>
        <Chip
          label={isCritical ? "Critical" : "Warning"}
          size="small"
          sx={{
            height: 22,
            fontSize: 11,
            fontWeight: 600,
            bgcolor: isCritical ? "#fce4ec" : "#fff3e0",
            color: isCritical ? "#d32f2f" : "#e65100",
          }}
        />
      </Box>

      {/* PM Progress (relative from last maintenance to next) */}
      <Box sx={{ mt: 1.5 }}>
        <Box sx={{ display: "flex", justifyContent: "space-between", mb: 0.5 }}>
          <Typography variant="caption" color="text.secondary">
            Next PM
          </Typography>
          <Typography variant="caption" fontWeight={600}>
            {formatNumber(entry.totalLifetimeStrokes - entry.pmCurrentStroke)} / {formatNumber(entry.nextStroke - entry.pmCurrentStroke)} ({entry.pmPercentage}%)
          </Typography>
        </Box>
        <Box sx={{ height: 6, borderRadius: 3, bgcolor: "grey.200", overflow: "hidden" }}>
          <Box
            sx={{
              height: "100%",
              width: `${Math.min(entry.pmPercentage, 100)}%`,
              bgcolor: barColor,
              borderRadius: 3,
            }}
          />
        </Box>
      </Box>

      {/* Tool Life progress */}
      <Box sx={{ mt: 1.5 }}>
        <Box sx={{ display: "flex", justifyContent: "space-between", mb: 0.5 }}>
          <Typography variant="caption" color="text.secondary">
            Tool Life
          </Typography>
          <Typography variant="caption" fontWeight={600}>
            {formatNumber(entry.totalLifetimeStrokes)} / {formatNumber(entry.toolLife)} ({lifePercentage}%)
          </Typography>
        </Box>
        <Box sx={{ height: 6, borderRadius: 3, bgcolor: "grey.200", overflow: "hidden" }}>
          <Box
            sx={{
              height: "100%",
              width: `${lifePercentage}%`,
              bgcolor: lifeBarColor,
              borderRadius: 3,
            }}
          />
        </Box>
      </Box>

      {entry.maintenanceCount > 0 && (
        <Typography variant="caption" color="text.disabled" sx={{ display: "block", mt: 1 }}>
          Maintained {entry.maintenanceCount} time{entry.maintenanceCount > 1 ? "s" : ""}
        </Typography>
      )}
    </Box>
  );
}

// ── Auto-scroll wrapper ────────────────────────────────────────────

function AutoScrollColumn({
  children,
  itemCount,
  reverse = false,
}: {
  children: React.ReactNode;
  itemCount: number;
  reverse?: boolean;
}) {
  const outerRef = useRef<HTMLDivElement>(null);
  const innerRef = useRef<HTMLDivElement>(null);
  const [needsScroll, setNeedsScroll] = useState(false);
  const [isHovered, setIsHovered] = useState(false);
  const [contentHeight, setContentHeight] = useState(0);
  const [duration, setDuration] = useState(20);

  const measure = useCallback(() => {
    const outer = outerRef.current;
    const inner = innerRef.current;
    if (!outer || !inner) return;
    const ch = inner.scrollHeight;
    const oh = outer.clientHeight;
    setContentHeight(ch);
    setNeedsScroll(ch > oh);
    // speed: ~40px/s so more content = longer duration
    setDuration(Math.max(10, ch / 40));
  }, []);

  useEffect(() => {
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [measure, itemCount]);

  // When switching to hover (manual scroll) mode, sync scroll position
  const handleMouseEnter = useCallback(() => {
    setIsHovered(true);
  }, []);

  const handleMouseLeave = useCallback(() => {
    setIsHovered(false);
  }, []);

  const scrollAnim = needsScroll && !isHovered
    ? reverse
      ? keyframes`
          0%   { transform: translateY(-${contentHeight}px); }
          100% { transform: translateY(0); }
        `
      : keyframes`
          0%   { transform: translateY(0); }
          100% { transform: translateY(-${contentHeight}px); }
        `
    : undefined;

  // When hovered, show as a normal scrollable list
  if (isHovered && needsScroll) {
    return (
      <Box
        ref={outerRef}
        onMouseLeave={handleMouseLeave}
        sx={{
          flex: 1,
          overflowY: "auto",
          p: 1.5,
          position: "relative",
          "&::-webkit-scrollbar": { width: 6 },
          "&::-webkit-scrollbar-thumb": {
            bgcolor: "rgba(0,0,0,0.2)",
            borderRadius: 3,
          },
          "&::-webkit-scrollbar-track": { bgcolor: "transparent" },
        }}
      >
        <Box ref={innerRef}>{children}</Box>
      </Box>
    );
  }

  return (
    <Box
      ref={outerRef}
      onMouseEnter={handleMouseEnter}
      sx={{
        flex: 1,
        overflow: "hidden",
        p: 1.5,
        position: "relative",
        /* fade-out masks at top & bottom so cards don't clip harshly */
        ...(needsScroll && {
          maskImage:
            "linear-gradient(to bottom, transparent 0%, black 4%, black 96%, transparent 100%)",
          WebkitMaskImage:
            "linear-gradient(to bottom, transparent 0%, black 4%, black 96%, transparent 100%)",
        }),
      }}
    >
      {needsScroll ? (
        <Box
          className="scroll-track"
          sx={{
            display: "flex",
            flexDirection: "column",
            animation: `${scrollAnim} ${duration}s linear infinite`,
          }}
        >
          {/* Original */}
          <Box ref={innerRef}>{children}</Box>
          {/* Duplicate for seamless loop */}
          <Box aria-hidden>{children}</Box>
        </Box>
      ) : (
        <Box ref={innerRef}>{children}</Box>
      )}
    </Box>
  );
}

// ── Main Component ─────────────────────────────────────────────────

export default function ToolsDashboardPage() {
  const [futureOffset, setFutureOffset] = useState(1); // 1 = tomorrow

  const futureDate = useMemo(() => dateOffset(futureOffset), [futureOffset]);

  const { data: todayData, isLoading: todayLoading } = useToolsToday();
  const { data: futureData, isLoading: futureLoading } =
    useToolsForDate(futureDate);
  const { data: pmStatus = [], isLoading: pmLoading } = usePMStatus();
  const { data: pmAll = [], isLoading: pmAllLoading } = usePMStatusAll();
  const { data: toolsCountData, isLoading: toolsCountLoading } = useToolsCount();
  const navigate = useNavigate();

  const [todayReverse, setTodayReverse] = useState(false);
  const [futureReverse, setFutureReverse] = useState(false);

  const isLoading = todayLoading || futureLoading || pmLoading || pmAllLoading || toolsCountLoading;

  // Build a lookup map: toolNo → PMStatusEntry
  const pmByToolNo = useMemo(() => {
    const map = new Map<string, PMStatusEntry>();
    for (const entry of pmAll) map.set(entry.toolNo, entry);
    return map;
  }, [pmAll]);

  // Compute life-span bands using distinct tools only.
  const totalTools = toolsCountData?.total ?? 0;
  const distinctPmAll = useMemo(() => {
    const uniqueByToolId = new Map<number, PMStatusEntry>();
    for (const entry of pmAll) {
      if (!uniqueByToolId.has(entry.toolId)) {
        uniqueByToolId.set(entry.toolId, entry);
      }
    }
    return Array.from(uniqueByToolId.values());
  }, [pmAll]);

  const allLifeTools = distinctPmAll.length;
  const warningTools = distinctPmAll.filter((t) => {
    const lifePct = t.toolLife > 0 ? (t.totalLifetimeStrokes / t.toolLife) * 100 : 0;
    return lifePct >= 50 && lifePct < 80;
  }).length;
  const criticalTools = distinctPmAll.filter((t) => {
    const lifePct = t.toolLife > 0 ? (t.totalLifetimeStrokes / t.toolLife) * 100 : 0;
    return lifePct >= 80;
  }).length;

  return (
    <Box
      sx={{
        display: "flex",
        flexDirection: "column",
        height: "100vh",
        overflow: "hidden",
        p: 3,
      }}
    >
      {/* ── Header ────────────────────────────────────────────── */}
      <Box
        sx={{
          flexShrink: 0,
          mb: 2,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <Box sx={{ flexShrink: 0 }}>
          <Typography variant="h5" fontWeight={700}>
            Tool Management Dashboard
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {todayData?.date
              ? formatDate(todayData.date)
              : formatDate(new Date().toISOString().slice(0, 10))}
          </Typography>
        </Box>

        {/* PM summary badges */}
        <Box sx={{ display: "flex", gap: 2, alignItems: "center", flex: 1, justifyContent: "flex-end", ml: 3 }}>
          {/* Total PM Tools */}
          <Box
            sx={{
              flex: 1,
              display: "flex",
              alignItems: "center",
              gap: 1.5,
              bgcolor: "#e3f2fd",
              borderRadius: 2,
              px: 2.5,
              py: 1.5,
            }}
          >
            <BuildIcon sx={{ fontSize: 22, color: "#1565c0" }} />
            <Box>
              <Typography
                variant="caption"
                sx={{ fontSize: 11, fontWeight: 600, color: "text.secondary", textTransform: "uppercase", letterSpacing: 0.5, lineHeight: 1 }}
              >
                Distinct Tools
              </Typography>
              <Typography variant="h6" fontWeight={700} lineHeight={1.2}>
                {totalTools}
              </Typography>
            </Box>
          </Box>

          {/* All Life */}
          <Box
            onClick={() => navigate("/life-report")}
            sx={{
              flex: 1,
              display: "flex",
              alignItems: "center",
              gap: 1.5,
              bgcolor: "#e0f2f1",
              borderRadius: 2,
              px: 2.5,
              py: 1.5,
              border: "1px solid #00897b",
              cursor: "pointer",
              transition: "box-shadow 0.2s",
              "&:hover": { boxShadow: "0 2px 8px rgba(0,137,123,0.3)" },
            }}
          >
            <CheckCircleIcon sx={{ fontSize: 22, color: "#00897b" }} />
            <Box>
              <Typography
                variant="caption"
                sx={{ fontSize: 11, fontWeight: 600, color: "text.secondary", textTransform: "uppercase", letterSpacing: 0.5, lineHeight: 1 }}
              >
                All Life
              </Typography>
              <Typography variant="h6" fontWeight={700} lineHeight={1.2} color="#00897b">
                {allLifeTools}
              </Typography>
            </Box>
          </Box>

          {/* 50-80% warning band */}
          <Box
            onClick={() => navigate("/life-report?filter=warning")}
            sx={{
              flex: 1,
              display: "flex",
              alignItems: "center",
              gap: 1.5,
              bgcolor: "#fff8e1",
              borderRadius: 2,
              px: 2.5,
              py: 1.5,
              border: "1px solid #f9a825",
              cursor: "pointer",
              transition: "box-shadow 0.2s",
              "&:hover": { boxShadow: "0 2px 8px rgba(249,168,37,0.3)" },
            }}
          >
            <ReportProblemIcon sx={{ fontSize: 22, color: "#f9a825" }} />
            <Box>
              <Typography
                variant="caption"
                sx={{ fontSize: 11, fontWeight: 600, color: "text.secondary", textTransform: "uppercase", letterSpacing: 0.5, lineHeight: 1 }}
              >
                Life 50–80%
              </Typography>
              <Typography variant="h6" fontWeight={700} lineHeight={1.2} color="#f9a825">
                {warningTools}
              </Typography>
            </Box>
          </Box>

          {/* ≥80% critical band */}
          <Box
            onClick={() => navigate("/life-report?filter=critical")}
            sx={{
              flex: 1,
              display: "flex",
              alignItems: "center",
              gap: 1.5,
              bgcolor: "#fce4ec",
              borderRadius: 2,
              px: 2.5,
              py: 1.5,
              border: "1px solid #d32f2f",
              cursor: "pointer",
              transition: "box-shadow 0.2s",
              "&:hover": { boxShadow: "0 2px 8px rgba(211,47,47,0.3)" },
            }}
          >
            <ErrorIcon sx={{ fontSize: 22, color: "#d32f2f" }} />
            <Box>
              <Typography
                variant="caption"
                sx={{ fontSize: 11, fontWeight: 600, color: "text.secondary", textTransform: "uppercase", letterSpacing: 0.5, lineHeight: 1 }}
              >
                Life ≥80% (Alert)
              </Typography>
              <Typography variant="h6" fontWeight={700} lineHeight={1.2} color="#d32f2f">
                {criticalTools}
              </Typography>
            </Box>
          </Box>
        </Box>
      </Box>

      {isLoading && (
        <LinearProgress sx={{ flexShrink: 0, mb: 1, borderRadius: 1 }} />
      )}

      {/* ── Stat Cards Row ────────────────────────────────────── */}
      <Box
        sx={{
          display: "flex",
          gap: 2,
          mb: 2,
          flexShrink: 0,
        }}
      >
        <StatCardCustom
          icon={<CalendarTodayIcon fontSize="small" />}
          label="Today's Tools"
          value={todayData?.count ?? "—"}
          bgColor="#1565c0"
        />
        <StatCardCustom
          icon={<EventIcon fontSize="small" />}
          label="Tomorrow's Tools"
          value={futureData?.count ?? "—"}
          bgColor="#2e7d32"
        />
        <StatCardCustom
          icon={<WarningAmberIcon fontSize="small" />}
          label="Maintenance"
          value={pmStatus.length}
          bgColor="#e65100"
        />
      </Box>

      {/* ── 3-Column Section ──────────────────────────────────── */}
      <Box
        sx={{
          display: "flex",
          gap: 2,
          flex: 1,
          minHeight: 0, // critical for nested scroll to work
        }}
      >
        {/* TODAY column */}
        <Box
          sx={{
            flex: 1,
            display: "flex",
            flexDirection: "column",
            borderRadius: 2,
            overflow: "hidden",
            bgcolor: "#f5f7fa",
          }}
        >
          <Box
            sx={{
              px: 2.5,
              py: 1.5,
              bgcolor: "#1565c0",
              flexShrink: 0,
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
            }}
          >
            <Typography
              variant="subtitle1"
              fontWeight={700}
              color="#fff"
              sx={{ textTransform: "uppercase", letterSpacing: 1 }}
            >
              Today
            </Typography>
            <IconButton
              size="small"
              onClick={() => setTodayReverse((r) => !r)}
              sx={{ color: "#fff", p: 0.5 }}
              title={todayReverse ? "Scroll down" : "Scroll up"}
            >
              {todayReverse ? <ArrowDownwardIcon sx={{ fontSize: 18 }} /> : <ArrowUpwardIcon sx={{ fontSize: 18 }} />}
            </IconButton>
          </Box>
          <AutoScrollColumn reverse={todayReverse} itemCount={todayData?.tools ? flattenTools(todayData.tools).length : 0}>
            {!todayData?.tools?.length && !isLoading && (
              <Typography
                variant="body2"
                color="text.secondary"
                textAlign="center"
                py={4}
              >
                No tools scheduled for today.
              </Typography>
            )}
            {todayData?.tools && flattenTools(todayData.tools).map((entry) => (
              <ToolCard key={`${entry.toolId}-${entry.machineId}`} entry={entry} pmEntry={pmByToolNo.get(entry.toolNo)} />
            ))}
          </AutoScrollColumn>
        </Box>

        {/* TOMORROW / FUTURE column */}
        <Box
          sx={{
            flex: 1,
            display: "flex",
            flexDirection: "column",
            borderRadius: 2,
            overflow: "hidden",
            bgcolor: "#f5f7fa",
          }}
        >
          <Box
            sx={{
              px: 1.5,
              py: 1,
              bgcolor: "#2e7d32",
              flexShrink: 0,
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
            }}
          >
            <IconButton
              size="small"
              onClick={() => setFutureOffset((o) => Math.max(1, o - 1))}
              disabled={futureOffset <= 1}
              sx={{ color: "#fff", opacity: futureOffset <= 1 ? 0.3 : 1, p: 0.5 }}
            >
              <ArrowBackIosNewIcon sx={{ fontSize: 16 }} />
            </IconButton>
            <Box sx={{ textAlign: "center", minWidth: 0 }}>
              <Typography
                variant="subtitle2"
                fontWeight={700}
                color="#fff"
                sx={{ textTransform: "uppercase", letterSpacing: 1, lineHeight: 1.2 }}
              >
                {offsetLabel(futureOffset)}
              </Typography>
              {futureData?.date && (
                <Typography variant="caption" sx={{ color: "rgba(255,255,255,0.75)", fontSize: 10 }}>
                  {formatShortDate(futureData.date)}
                </Typography>
              )}
            </Box>
            <IconButton
              size="small"
              onClick={() => setFutureOffset((o) => o + 1)}
              sx={{ color: "#fff", p: 0.5 }}
            >
              <ArrowForwardIosIcon sx={{ fontSize: 16 }} />
            </IconButton>
            <IconButton
              size="small"
              onClick={() => setFutureReverse((r) => !r)}
              sx={{ color: "#fff", p: 0.5, ml: 0.5 }}
              title={futureReverse ? "Scroll down" : "Scroll up"}
            >
              {futureReverse ? <ArrowDownwardIcon sx={{ fontSize: 18 }} /> : <ArrowUpwardIcon sx={{ fontSize: 18 }} />}
            </IconButton>
          </Box>
          <AutoScrollColumn reverse={futureReverse} itemCount={futureData?.tools ? flattenTools(futureData.tools).length : 0}>
            {!futureData?.tools?.length && !isLoading && (
              <Typography
                variant="body2"
                color="text.secondary"
                textAlign="center"
                py={4}
              >
                No tools scheduled for {offsetLabel(futureOffset).toLowerCase()}.
              </Typography>
            )}
            {futureData?.tools && flattenTools(futureData.tools).map((entry) => (
              <ToolCard key={`${entry.toolId}-${entry.machineId}`} entry={entry} pmEntry={pmByToolNo.get(entry.toolNo)} />
            ))}
          </AutoScrollColumn>
        </Box>

        {/* MAINTENANCE ALERT column */}
        <Box
          sx={{
            flex: 1,
            display: "flex",
            flexDirection: "column",
            borderRadius: 2,
            overflow: "hidden",
            bgcolor: "#fffbf5",
          }}
        >
          <Box
            sx={{
              px: 2.5,
              py: 1.5,
              bgcolor: "#e65100",
              flexShrink: 0,
            }}
          >
            <Typography
              variant="subtitle1"
              fontWeight={700}
              color="#fff"
              sx={{ textTransform: "uppercase", letterSpacing: 1 }}
            >
              Maintenance Alert
            </Typography>
          </Box>
          <AutoScrollColumn itemCount={pmStatus.length}>
            {pmStatus.length === 0 && !isLoading && (
              <Typography
                variant="body2"
                color="text.secondary"
                textAlign="center"
                py={4}
              >
                No tools require maintenance.
              </Typography>
            )}
            {pmStatus.map((entry) => (
              <MaintenanceCard key={entry.toolId} entry={entry} />
            ))}
          </AutoScrollColumn>
        </Box>
      </Box>
    </Box>
  );
}
