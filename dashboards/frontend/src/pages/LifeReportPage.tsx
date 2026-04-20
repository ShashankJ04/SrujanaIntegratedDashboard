import { useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import Typography from "@mui/material/Typography";
import Box from "@mui/material/Box";
import LinearProgress from "@mui/material/LinearProgress";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Paper from "@mui/material/Paper";
import Chip from "@mui/material/Chip";
import { usePMStatusAll } from "@/api";
import type { PMStatusEntry } from "@/api";
import { formatIndianCompact as formatNumber } from "@/utils";

function lifePercentage(entry: PMStatusEntry): number {
  if (entry.toolLife <= 0) return 0;
  return Math.min(Math.round((entry.totalLifetimeStrokes / entry.toolLife) * 100), 100);
}

function lifeColor(pct: number): string {
  if (pct >= 80) return "#d32f2f";
  if (pct >= 50) return "#ed6c02";
  return "#2e7d32";
}

function pmProgress(entry: PMStatusEntry): number {
  const range = entry.nextStroke - entry.pmCurrentStroke;
  if (range <= 0) return 0;
  return Math.round(((entry.totalLifetimeStrokes - entry.pmCurrentStroke) / range) * 100);
}

export default function LifeReportPage() {
  const { data: pmAll = [], isLoading } = usePMStatusAll();
  const [searchParams, setSearchParams] = useSearchParams();
  const filter = searchParams.get("filter"); // "warning" | "critical" | null

  const sorted = useMemo(() => {
    let list = [...pmAll];
    if (filter === "warning") {
      list = list.filter((t) => {
        const p = lifePercentage(t);
        return p >= 50 && p < 80;
      });
    } else if (filter === "critical") {
      list = list.filter((t) => lifePercentage(t) >= 80);
    }
    return list.sort((a, b) => lifePercentage(b) - lifePercentage(a));
  }, [pmAll, filter]);

  const clearFilter = () => {
    setSearchParams({});
  };

  const filterLabel =
    filter === "warning" ? "Life 50–80%" : filter === "critical" ? "Life ≥80%" : null;

  return (
    <Box
      sx={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        overflow: "hidden",
        p: 3,
      }}
    >
      {/* Header */}
      <Box sx={{ flexShrink: 0, mb: 2, display: "flex", alignItems: "center", gap: 2 }}>
        <Box>
          <Typography variant="h5" fontWeight={700}>
            Tool Life Report
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {filterLabel
              ? `Showing tools with ${filterLabel}`
              : "Current lifetime strokes for all tools"}
          </Typography>
        </Box>
        {filterLabel && (
          <Chip
            label={`Filter: ${filterLabel}`}
            onDelete={clearFilter}
            color={filter === "critical" ? "error" : "warning"}
            size="small"
          />
        )}
      </Box>

      {isLoading && <LinearProgress sx={{ flexShrink: 0, mb: 1, borderRadius: 1 }} />}

      {/* Summary cards — always based on all tools, not the filtered list */}
      <Box sx={{ display: "flex", gap: 2, mb: 2, flexShrink: 0 }}>
        <SummaryCard label="Total Tools" value={pmAll.length} color="#1565c0" bg="#e3f2fd" />
        <SummaryCard
          label="Life 50–80%"
          value={pmAll.filter((t) => { const p = lifePercentage(t); return p >= 50 && p < 80; }).length}
          color="#f9a825"
          bg="#fff8e1"
        />
        <SummaryCard
          label="Life ≥80%"
          value={pmAll.filter((t) => lifePercentage(t) >= 80).length}
          color="#d32f2f"
          bg="#fce4ec"
        />
      </Box>

      {/* Table */}
      <TableContainer
        component={Paper}
        sx={{
          flex: 1,
          overflow: "auto",
          borderRadius: 2,
          boxShadow: "0 1px 4px rgba(0,0,0,0.08)",
        }}
      >
        <Table stickyHeader size="small">
          <TableHead>
            <TableRow>
              <TableCell sx={{ fontWeight: 700, bgcolor: "#f5f5f5" }}>#</TableCell>
              <TableCell sx={{ fontWeight: 700, bgcolor: "#f5f5f5" }}>Tool No</TableCell>
              <TableCell sx={{ fontWeight: 700, bgcolor: "#f5f5f5" }} align="right">
                Tool Life
              </TableCell>
              <TableCell sx={{ fontWeight: 700, bgcolor: "#f5f5f5" }} align="right">
                Lifetime Strokes
              </TableCell>
              <TableCell sx={{ fontWeight: 700, bgcolor: "#f5f5f5", minWidth: 200 }}>
                Life Used
              </TableCell>
              <TableCell sx={{ fontWeight: 700, bgcolor: "#f5f5f5" }} align="right">
                %
              </TableCell>
              <TableCell sx={{ fontWeight: 700, bgcolor: "#f5f5f5", minWidth: 180 }}>
                PM Progress
              </TableCell>
              <TableCell sx={{ fontWeight: 700, bgcolor: "#f5f5f5" }} align="right">
                PM %
              </TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {sorted.map((entry, idx) => {
              const pct = lifePercentage(entry);
              const color = lifeColor(pct);
              const pmPct = pmProgress(entry);
              const pmColor = lifeColor(pmPct);
              const pmRange = entry.nextStroke - entry.pmCurrentStroke;
              return (
                <TableRow key={entry.toolId} hover>
                  <TableCell>{idx + 1}</TableCell>
                  <TableCell>
                    <Typography variant="body2" fontWeight={600}>
                      {entry.toolNo}
                    </Typography>
                  </TableCell>
                  <TableCell align="right">{formatNumber(entry.toolLife)}</TableCell>
                  <TableCell align="right">{formatNumber(entry.totalLifetimeStrokes)}</TableCell>
                  <TableCell>
                    <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                      <Box sx={{ flex: 1, bgcolor: "#eee", borderRadius: 1, height: 10, overflow: "hidden" }}>
                        <Box
                          sx={{
                            width: `${pct}%`,
                            height: "100%",
                            bgcolor: color,
                            borderRadius: 1,
                            transition: "width 0.4s ease",
                          }}
                        />
                      </Box>
                    </Box>
                  </TableCell>
                  <TableCell align="right">
                    <Typography variant="body2" fontWeight={700} sx={{ color }}>
                      {pct}%
                    </Typography>
                  </TableCell>
                  <TableCell>
                    {pmRange > 0 ? (
                      <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                        <Box sx={{ flex: 1, bgcolor: "#eee", borderRadius: 1, height: 10, overflow: "hidden" }}>
                          <Box
                            sx={{
                              width: `${Math.min(pmPct, 100)}%`,
                              height: "100%",
                              bgcolor: pmColor,
                              borderRadius: 1,
                              transition: "width 0.4s ease",
                            }}
                          />
                        </Box>
                        <Typography variant="caption" sx={{ fontSize: 10, whiteSpace: "nowrap" }}>
                          {formatNumber(entry.totalLifetimeStrokes - entry.pmCurrentStroke)}/{formatNumber(pmRange)}
                        </Typography>
                      </Box>
                    ) : (
                      <Typography variant="caption" color="text.disabled">—</Typography>
                    )}
                  </TableCell>
                  <TableCell align="right">
                    {pmRange > 0 ? (
                      <Typography variant="body2" fontWeight={700} sx={{ color: pmColor }}>
                        {pmPct}%
                      </Typography>
                    ) : (
                      <Typography variant="body2" color="text.disabled">—</Typography>
                    )}
                  </TableCell>
                </TableRow>
              );
            })}
            {!isLoading && sorted.length === 0 && (
              <TableRow>
                <TableCell colSpan={8} align="center" sx={{ py: 4 }}>
                  <Typography color="text.secondary">No tools found</Typography>
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>
    </Box>
  );
}

/* Small summary card used at the top */
function SummaryCard({ label, value, color, bg }: { label: string; value: number; color: string; bg: string }) {
  return (
    <Box
      sx={{
        flex: 1,
        bgcolor: bg,
        borderRadius: 2,
        px: 2.5,
        py: 1.5,
        display: "flex",
        flexDirection: "column",
      }}
    >
      <Typography
        variant="caption"
        sx={{ fontSize: 11, fontWeight: 600, color: "text.secondary", textTransform: "uppercase", letterSpacing: 0.5, lineHeight: 1 }}
      >
        {label}
      </Typography>
      <Typography variant="h5" fontWeight={700} sx={{ color, lineHeight: 1.3 }}>
        {value}
      </Typography>
    </Box>
  );
}
