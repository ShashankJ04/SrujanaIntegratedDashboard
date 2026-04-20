import { useState, useMemo } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import TextField from "@mui/material/TextField";
import Button from "@mui/material/Button";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Paper from "@mui/material/Paper";
import CircularProgress from "@mui/material/CircularProgress";
import Alert from "@mui/material/Alert";
import Chip from "@mui/material/Chip";
import MenuItem from "@mui/material/MenuItem";
import SearchIcon from "@mui/icons-material/Search";
import TrendingUpIcon from "@mui/icons-material/TrendingUp";
import TrendingDownIcon from "@mui/icons-material/TrendingDown";
import CompareArrowsIcon from "@mui/icons-material/CompareArrows";
import { useRMVariance } from "@/api";
import type { RMVarianceEntry } from "@/api";
import { formatIndianNumber } from "@/utils";

// ── Helpers ────────────────────────────────────────────────────────

const MONTHS = [
  { value: 1, label: "January" },
  { value: 2, label: "February" },
  { value: 3, label: "March" },
  { value: 4, label: "April" },
  { value: 5, label: "May" },
  { value: 6, label: "June" },
  { value: 7, label: "July" },
  { value: 8, label: "August" },
  { value: 9, label: "September" },
  { value: 10, label: "October" },
  { value: 11, label: "November" },
  { value: 12, label: "December" },
];

// ── Variance chip ──────────────────────────────────────────────────

function VarianceChip({ value }: { value: number }) {
  const rounded = Math.round(value * 100) / 100;
  if (rounded === 0) {
    return <Chip label="0" size="small" sx={{ fontWeight: 600, fontSize: 12 }} />;
  }
  const isPositive = rounded > 0;
  return (
    <Chip
      icon={isPositive ? <TrendingUpIcon /> : <TrendingDownIcon />}
      label={Math.abs(rounded).toFixed(2)}
      size="small"
      color={isPositive ? "error" : "success"}
      variant="outlined"
      sx={{ fontWeight: 600, fontSize: 12 }}
    />
  );
}

// ── Column config ──────────────────────────────────────────────────

interface Column {
  key: keyof RMVarianceEntry;
  label: string;
  align?: "left" | "right" | "center";
  format?: (v: any, row: RMVarianceEntry) => React.ReactNode;
  width?: number;
}

const columns: Column[] = [
  { key: "partno", label: "Part No", width: 100 },
  { key: "rm", label: "RM", width: 100 },
  { key: "tool", label: "Tool", width: 90 },
  {
    key: "custReqQty",
    label: "Cust Req Qty",
    align: "right",
    width: 80,
    format: (v: number) => formatIndianNumber(v),
  },
  {
    key: "schQty",
    label: "Sch Qty",
    align: "right",
    width: 70,
    format: (v: number) => formatIndianNumber(v),
  },
  {
    key: "schKg",
    label: "Sch Kg",
    align: "right",
    width: 70,
    format: (v: number) => v.toFixed(2),
  },
  {
    key: "prodQty",
    label: "Prod Qty",
    align: "right",
    width: 70,
    format: (v: number) => formatIndianNumber(v),
  },  
  {
    key: "usedQty",
    label: "Used Qty (Kg)",
    align: "right",
    width: 90,
    format: (v: number) => v.toFixed(2),
  },
  {
    key: "theoKg",
    label: "Theo Kg",
    align: "right",
    width: 80,
    format: (v: number) => v.toFixed(2),
  },
  {
    key: "variance",
    label: "Variance",
    align: "center",
    width: 90,
    format: (v: number) => <VarianceChip value={v} />,
  },
  {
    key: "variancePer",
    label: "Variance %",
    align: "center",
    width: 90,
    format: (v: number) => <VarianceChip value={v} />,
  },
];

// ── Main Page ──────────────────────────────────────────────────────

export default function RMVariancePage() {
  const now = new Date();
  const [selectedMonth, setSelectedMonth] = useState<number>(now.getMonth() + 1);
  const [selectedYear, setSelectedYear] = useState<number>(now.getFullYear());
  const [plantId, setPlantId] = useState<string>("3");

  const [queryMonth, setQueryMonth] = useState<number | null>(null);
  const [queryYear, setQueryYear] = useState<number | null>(null);
  const [queryPlantId, setQueryPlantId] = useState<number | null>(null);

  const { data, isLoading, isError, error } = useRMVariance(
    queryMonth,
    queryYear,
    queryPlantId
  );

  const handleSearch = () => {
    const pid = parseInt(plantId, 10);
    if (!isNaN(pid) && pid > 0) {
      setQueryMonth(selectedMonth);
      setQueryYear(selectedYear);
      setQueryPlantId(pid);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") handleSearch();
  };

  // Sort entries by date then part no
  const sortedEntries = useMemo(
    () =>
      data?.entries
        ?.slice()
        .sort((a, b) => a.partno.localeCompare(b.partno)) ?? [],
    [data?.entries]
  );

  const totals = data?.totals;

  // Year options: current year ± 5
  const yearOptions = useMemo(() => {
    const current = new Date().getFullYear();
    const years: number[] = [];
    for (let y = current - 5; y <= current + 1; y++) years.push(y);
    return years;
  }, []);

  return (
    <Box
      sx={{
        minHeight: "100%",
        display: "flex",
        flexDirection: "column",
      }}
    >
      {/* ── Header bar ─────────────────────────────────────────── */}
      <Box
        sx={{
          px: 3,
          py: 2,
          bgcolor: "#fff",
          borderBottom: "1px solid",
          borderColor: "divider",
          display: "flex",
          alignItems: "center",
          gap: 2,
          flexWrap: "wrap",
        }}
      >
        <CompareArrowsIcon sx={{ fontSize: 28, color: "#e65100" }} />
        <Typography variant="h5" fontWeight={700} sx={{ flexGrow: 1 }}>
          RM Variance
        </Typography>

        <TextField
          select
          size="small"
          label="Month"
          value={selectedMonth}
          onChange={(e) => setSelectedMonth(Number(e.target.value))}
          onKeyDown={handleKeyDown}
          sx={{ width: 150 }}
        >
          {MONTHS.map((m) => (
            <MenuItem key={m.value} value={m.value}>
              {m.label}
            </MenuItem>
          ))}
        </TextField>

        <TextField
          select
          size="small"
          label="Year"
          value={selectedYear}
          onChange={(e) => setSelectedYear(Number(e.target.value))}
          onKeyDown={handleKeyDown}
          sx={{ width: 110 }}
        >
          {yearOptions.map((y) => (
            <MenuItem key={y} value={y}>
              {y}
            </MenuItem>
          ))}
        </TextField>

        <TextField
          size="small"
          label="Plant ID"
          type="number"
          value={plantId}
          onChange={(e) => setPlantId(e.target.value)}
          onKeyDown={handleKeyDown}
          InputProps={{ inputProps: { min: 1 } }}
          sx={{ width: 100 }}
        />

        <Button
          variant="contained"
          startIcon={<SearchIcon />}
          onClick={handleSearch}
          sx={{ textTransform: "none" }}
        >
          Search
        </Button>
      </Box>

      {/* ── Content ────────────────────────────────────────────── */}
      <Box sx={{ flex: 1, p: 3 }}>
        {isLoading && (
          <Box sx={{ display: "flex", justifyContent: "center", py: 10 }}>
            <CircularProgress />
          </Box>
        )}

        {isError && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {(error as Error)?.message || "Failed to load RM variance data"}
          </Alert>
        )}

        {data && (
          <TableContainer
            component={Paper}
            variant="outlined"
            sx={{
              "& .MuiTableCell-root": {
                px: 1,
                py: 0.5,
              },
              "& .MuiTableCell-head": {
                bgcolor: "#f5f5f5",
                fontWeight: 700,
                fontSize: 11,
                textTransform: "uppercase",
                letterSpacing: "0.03em",
                whiteSpace: "nowrap",
                position: "sticky",
                top: 0,
                zIndex: 1,
              },
              "& .MuiTableCell-body": {
                fontSize: 12,
              },
            }}
          >
            <Table size="small" stickyHeader>
              <TableHead>
                <TableRow>
                  <TableCell sx={{ width: 50, fontWeight: 700 }}>#</TableCell>
                  {columns.map((col) => (
                    <TableCell
                      key={col.key}
                      align={col.align ?? "left"}
                      sx={{ minWidth: col.width }}
                    >
                      {col.label}
                    </TableCell>
                  ))}
                </TableRow>
              </TableHead>
              <TableBody>
                {sortedEntries.map((entry, idx) => (
                  <TableRow
                    key={idx}
                    hover
                    sx={{
                      "&:nth-of-type(even)": {
                        bgcolor: "action.hover",
                      },
                    }}
                  >
                    <TableCell sx={{ color: "text.secondary" }}>
                      {idx + 1}
                    </TableCell>
                    {columns.map((col) => (
                      <TableCell key={col.key} align={col.align ?? "left"}>
                        {col.format
                          ? col.format(entry[col.key], entry)
                          : (entry[col.key] as any) ?? "—"}
                      </TableCell>
                    ))}
                  </TableRow>
                ))}

                {/* ── Totals row ──────────────────────────── */}
                {totals && (
                  <TableRow
                    sx={{
                      "& .MuiTableCell-root": {
                        fontWeight: 700,
                        borderTop: "2px solid",
                        borderColor: "divider",
                        bgcolor: "#fafafa",
                        fontSize: 13,
                      },
                    }}
                  >
                    <TableCell />
                    <TableCell colSpan={3}>
                      <strong>TOTAL</strong>
                    </TableCell>
                    <TableCell align="right">
                      {formatIndianNumber(totals.custReqQty)}
                    </TableCell>
                    <TableCell align="right">
                      {formatIndianNumber(totals.schQty)}
                    </TableCell>
                    <TableCell align="right">
                      {totals.schKg.toFixed(2)}
                    </TableCell>
                    <TableCell align="right">
                      {formatIndianNumber(totals.prodQty)}
                    </TableCell>                    
                    <TableCell align="right">
                      {totals.usedQty.toFixed(2)}
                    </TableCell>
                    <TableCell align="right">
                      {totals.theoKg.toFixed(2)}
                    </TableCell>
                    <TableCell align="center">
                      <VarianceChip value={totals.variance} />
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </TableContainer>
        )}

        {/* Empty state */}
        {!data && !isLoading && !isError && (
          <Box
            sx={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              py: 10,
              color: "text.secondary",
            }}
          >
            <CompareArrowsIcon sx={{ fontSize: 64, mb: 2, opacity: 0.3 }} />
            <Typography variant="h6">
              Select Month, Year & Plant ID, then click Search
            </Typography>
          </Box>
        )}
      </Box>
    </Box>
  );
}
